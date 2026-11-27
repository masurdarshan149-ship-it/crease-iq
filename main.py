from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from cricket_predictor.models import MatchContext, PitchReport, Player, TeamSnapshot
from cricket_predictor.predictor import predict_match_winner
from cricket_predictor.update_service import UPDATE_SERVICE
from cricket_predictor import webapp


# Test copies set CRICKET_HISTORY_PATH so they never write into the real prediction history
HISTORY_PATH = Path(os.environ.get("CRICKET_HISTORY_PATH") or "prediction_history.json")
# Public mode (the online copy, e.g. Hugging Face): no shared files are written. Each visitor's saved predictions live in
# their own browser and travel with the few requests that need them (see _read_history / _write_history and the
# "client_history" field); admin actions (retrain, data updates, settings, drop logging) are switched off.
PUBLIC = os.environ.get("CREASE_PUBLIC") == "1"
# the online copy also shows your photos and team logos (web/img) when this is set: the Render build sets it
PUBLIC_IMAGES = PUBLIC and os.environ.get("CREASE_PUBLIC_IMAGES") == "1"
_REQ = threading.local()  # the current request's copy of the visitor's history (public mode only)
# the largest request body accepted: online only text is sent (pictures are read on the phone), so 3 MB is plenty even
# with 500 saved predictions; on your PC a picture goes to Windows' text reader as a data URL (up to about 11 MB)
MAX_BODY = 3_000_000 if PUBLIC else 25_000_000
NUMBER_FIELDS = ("runs", "wickets", "overs", "target", "par")


def _input_problem(payload: Any) -> str | None:
    """A plain reason when a request can't be used as sent (checked once, for every API route): not an object, a
    score field that isn't a number, a team the app doesn't know, or the same team on both sides."""
    if not isinstance(payload, dict):
        return "That request couldn't be read (send the details as a JSON object)."
    for field in NUMBER_FIELDS:
        v = payload.get(field)
        if v in (None, ""):
            continue
        try:
            num = float(v)
        except (TypeError, ValueError):
            return f"Check what you entered: {field} must be a number."
        if num != num or num in (float("inf"), float("-inf")):
            return f"Check what you entered: {field} must be a number."
    bat, chase = payload.get("batting"), payload.get("chasing")
    if isinstance(bat, str) and isinstance(chase, str) and bat and chase:
        if bat == chase:
            return "Pick two different teams."
        bank = _team_bank(_mode_key(payload.get("mode")))
        unknown = [c for c in (bat, chase) if c not in bank]
        if unknown:
            return f"Unknown team: {', '.join(unknown)}. Pick the teams from the list."
    return None
PUBLIC_BLOCKED = {"/api/settings", "/api/retrain", "/api/update-all", "/api/auto-update", "/api/update-data", "/api/history/restore-backup"}
_RATE: dict = {}
_RATE_LOCK = threading.Lock()


def _rate_ok(ip: str, limit: int = 600, window: float = 60.0) -> bool:
    """Public mode: at most `limit` API calls per minute per visitor, so one person can't swamp the free server."""
    now = time.time()
    with _RATE_LOCK:
        hits = [t for t in _RATE.get(ip, []) if now - t < window]
        if len(hits) >= limit:
            _RATE[ip] = hits
            return False
        hits.append(now)
        _RATE[ip] = hits
        if len(_RATE) > 5000:
            _RATE.clear()
    return True
HISTORY_LIMIT = 500  # enough for a season of predictions in the History tracker
WATCHED_PATHS = [
    Path("main.py"),
    Path("sample_match.json"),
    Path("cricket_predictor"),
]


IPL_2026_TEAMS: dict[str, dict[str, Any]] = {
    "CSK": {
        "name": "Chennai Super Kings",
        "fielding_rating": 73.0,
        "recent_form": 0.62,
        "source_url": "https://www.iplt20.com/index.php/teams/chennai-super-kings",
        "squad": [
            {"name": "MS Dhoni", "role": "wicket_keeper"},
            {"name": "Ruturaj Gaikwad", "role": "batter"},
            {"name": "Dewald Brevis", "role": "batter"},
            {"name": "Ayush Mhatre", "role": "batter"},
            {"name": "Kartik Sharma", "role": "wicket_keeper"},
            {"name": "Sarfaraz Khan", "role": "batter"},
            {"name": "Urvil Patel", "role": "wicket_keeper"},
            {"name": "Anshul Kamboj", "role": "all_rounder"},
            {"name": "Jamie Overton", "role": "all_rounder"},
            {"name": "Ramakrishna Ghosh", "role": "all_rounder"},
            {"name": "Prashant Veer", "role": "all_rounder"},
            {"name": "Matthew William Short", "role": "all_rounder"},
            {"name": "Aman Khan", "role": "all_rounder"},
            {"name": "Zak Foulkes", "role": "all_rounder"},
            {"name": "Shivam Dube", "role": "all_rounder"},
            {"name": "Khaleel Ahmed", "role": "bowler"},
            {"name": "Noor Ahmad", "role": "bowler"},
            {"name": "Mukesh Choudhary", "role": "bowler"},
            {"name": "Nathan Ellis", "role": "bowler"},
            {"name": "Shreyas Gopal", "role": "bowler"},
            {"name": "Gurjapneet Singh", "role": "bowler"},
            {"name": "Akeal Hosein", "role": "bowler"},
            {"name": "Matt Henry", "role": "bowler"},
            {"name": "Rahul Chahar", "role": "bowler"},
        ],
    },
    "DC": {
        "name": "Delhi Capitals",
        "fielding_rating": 72.0,
        "recent_form": 0.64,
        "source_url": "https://www.iplt20.com/teams/delhi-capitals",
        "squad": [
            {"name": "KL Rahul", "role": "wicket_keeper"},
            {"name": "Karun Nair", "role": "batter"},
            {"name": "David Miller", "role": "batter"},
            {"name": "Ben Duckett", "role": "wicket_keeper"},
            {"name": "Pathum Nissanka", "role": "batter"},
            {"name": "Sahil Parakh", "role": "batter"},
            {"name": "Prithvi Shaw", "role": "batter"},
            {"name": "Abishek Porel", "role": "wicket_keeper"},
            {"name": "Tristan Stubbs", "role": "wicket_keeper"},
            {"name": "Axar Patel", "role": "all_rounder"},
            {"name": "Sameer Rizvi", "role": "all_rounder"},
            {"name": "Ashutosh Sharma", "role": "all_rounder"},
            {"name": "Vipraj Nigam", "role": "all_rounder"},
            {"name": "Ajay Mandal", "role": "all_rounder"},
            {"name": "Tripurana Vijay", "role": "all_rounder"},
            {"name": "Madhav Tiwari", "role": "all_rounder"},
            {"name": "Auqib Dar", "role": "all_rounder"},
            {"name": "Nitish Rana", "role": "all_rounder"},
            {"name": "Mitchell Starc", "role": "bowler"},
            {"name": "T. Natarajan", "role": "bowler"},
            {"name": "Mukesh Kumar", "role": "bowler"},
            {"name": "Dushmantha Chameera", "role": "bowler"},
            {"name": "Lungisani Ngidi", "role": "bowler"},
            {"name": "Kyle Jamieson", "role": "bowler"},
            {"name": "Kuldeep Yadav", "role": "bowler"},
        ],
    },
    "GT": {
        "name": "Gujarat Titans",
        "fielding_rating": 75.0,
        "recent_form": 0.72,
        "source_url": "https://www.iplt20.com/teams/gujarat-titans",
        "squad": [
            {"name": "Shubman Gill", "role": "batter"},
            {"name": "Jos Buttler", "role": "wicket_keeper"},
            {"name": "Kumar Kushagra", "role": "wicket_keeper"},
            {"name": "Anuj Rawat", "role": "wicket_keeper"},
            {"name": "Tom Banton", "role": "wicket_keeper"},
            {"name": "Glenn Phillips", "role": "batter"},
            {"name": "Nishant Sindhu", "role": "all_rounder"},
            {"name": "Washington Sundar", "role": "all_rounder"},
            {"name": "Mohd. Arshad Khan", "role": "all_rounder"},
            {"name": "Sai Kishore", "role": "all_rounder"},
            {"name": "Jayant Yadav", "role": "all_rounder"},
            {"name": "Jason Holder", "role": "all_rounder"},
            {"name": "Sai Sudharsan", "role": "all_rounder"},
            {"name": "Shahrukh Khan", "role": "all_rounder"},
            {"name": "Kagiso Rabada", "role": "bowler"},
            {"name": "Mohammed Siraj", "role": "bowler"},
            {"name": "Prasidh Krishna", "role": "bowler"},
            {"name": "Manav Suthar", "role": "bowler"},
            {"name": "Gurnoor Singh Brar", "role": "bowler"},
            {"name": "Ishant Sharma", "role": "bowler"},
            {"name": "Ashok Sharma", "role": "bowler"},
            {"name": "Prithvi Raj Yarra", "role": "bowler"},
            {"name": "Luke Wood", "role": "bowler"},
            {"name": "Rahul Tewatia", "role": "all_rounder"},
            {"name": "Rashid Khan", "role": "bowler"},
        ],
    },
    "KKR": {
        "name": "Kolkata Knight Riders",
        "fielding_rating": 76.0,
        "recent_form": 0.7,
        "source_url": "https://www.iplt20.com/teams/kolkata-knight-riders",
        "squad": [
            {"name": "Ajinkya Rahane", "role": "batter"},
            {"name": "Rinku Singh", "role": "batter"},
            {"name": "Angkrish Raghuvanshi", "role": "batter"},
            {"name": "Manish Pandey", "role": "batter"},
            {"name": "Cameron Green", "role": "batter"},
            {"name": "Finn Allen", "role": "wicket_keeper"},
            {"name": "Tejasvi Singh", "role": "wicket_keeper"},
            {"name": "Rahul Tripathi", "role": "batter"},
            {"name": "Tim Seifert", "role": "wicket_keeper"},
            {"name": "Rovman Powell", "role": "batter"},
            {"name": "Ramandeep Singh", "role": "all_rounder"},
            {"name": "Anukul Roy", "role": "all_rounder"},
            {"name": "Sarthak Ranjan", "role": "all_rounder"},
            {"name": "Daksh Kamra", "role": "all_rounder"},
            {"name": "Rachin Ravindra", "role": "all_rounder"},
            {"name": "Harshit Rana", "role": "bowler"},
            {"name": "Matheesha Pathirana", "role": "bowler"},
            {"name": "Kartik Tyagi", "role": "bowler"},
            {"name": "Prashant Solanki", "role": "bowler"},
            {"name": "Akash Deep", "role": "bowler"},
            {"name": "Vaibhav Arora", "role": "bowler"},
            {"name": "Umran Malik", "role": "bowler"},
            {"name": "Sunil Narine", "role": "bowler"},
            {"name": "Varun Chakaravarthy", "role": "bowler"},
        ],
    },
    "LSG": {
        "name": "Lucknow Super Giants",
        "fielding_rating": 72.0,
        "recent_form": 0.6,
        "source_url": "https://www.iplt20.com/teams/lucknow-super-giants",
        "squad": [
            {"name": "Rishabh Pant", "role": "wicket_keeper"},
            {"name": "Aiden Markram", "role": "batter"},
            {"name": "Himmat Singh", "role": "batter"},
            {"name": "Matthew Breetzke", "role": "batter"},
            {"name": "Mukul Choudhary", "role": "wicket_keeper"},
            {"name": "Akshat Raghuwanshi", "role": "batter"},
            {"name": "Josh Inglis", "role": "wicket_keeper"},
            {"name": "Nicholas Pooran", "role": "wicket_keeper"},
            {"name": "Mitchell Marsh", "role": "all_rounder"},
            {"name": "Abdul Samad", "role": "all_rounder"},
            {"name": "Shahbaz Ahamad", "role": "all_rounder"},
            {"name": "Arshin Kulkarni", "role": "all_rounder"},
            {"name": "Wanindu Hasaranga", "role": "all_rounder"},
            {"name": "Ayush Badoni", "role": "all_rounder"},
            {"name": "Mohammad Shami", "role": "bowler"},
            {"name": "Avesh Khan", "role": "bowler"},
            {"name": "Shamar Joseph", "role": "bowler"},
            {"name": "M. Siddharth", "role": "bowler"},
            {"name": "Digvesh Singh", "role": "bowler"},
            {"name": "Akash Singh", "role": "bowler"},
            {"name": "Prince Yadav", "role": "bowler"},
            {"name": "Arjun Tendulkar", "role": "bowler"},
            {"name": "Anrich Nortje", "role": "bowler"},
            {"name": "Naman Tiwari", "role": "bowler"},
            {"name": "Mayank Yadav", "role": "bowler"},
            {"name": "Mohsin Khan", "role": "bowler"},
        ],
    },
    "MI": {
        "name": "Mumbai Indians",
        "fielding_rating": 77.0,
        "recent_form": 0.74,
        "source_url": "https://www.iplt20.com/teams/mumbai-indians/squad",
        "squad": [
            {"name": "Rohit Sharma", "role": "batter"},
            {"name": "Surya Kumar Yadav", "role": "batter"},
            {"name": "Robin Minz", "role": "wicket_keeper"},
            {"name": "Sherfane Rutherford", "role": "batter"},
            {"name": "Ryan Rickelton", "role": "wicket_keeper"},
            {"name": "Quinton de Kock", "role": "wicket_keeper"},
            {"name": "Danish Malewar", "role": "batter"},
            {"name": "Tilak Varma", "role": "batter"},
            {"name": "Hardik Pandya", "role": "all_rounder"},
            {"name": "Naman Dhir", "role": "all_rounder"},
            {"name": "Mitchell Santner", "role": "all_rounder"},
            {"name": "Raj Angad Bawa", "role": "all_rounder"},
            {"name": "Atharva Ankolekar", "role": "all_rounder"},
            {"name": "Mayank Rawat", "role": "all_rounder"},
            {"name": "Corbin Bosch", "role": "all_rounder"},
            {"name": "Will Jacks", "role": "all_rounder"},
            {"name": "Shardul Thakur", "role": "all_rounder"},
            {"name": "Trent Boult", "role": "bowler"},
            {"name": "Mayank Markande", "role": "bowler"},
            {"name": "Deepak Chahar", "role": "bowler"},
            {"name": "Ashwani Kumar", "role": "bowler"},
            {"name": "Raghu Sharma", "role": "bowler"},
            {"name": "Mohammad Izhar", "role": "bowler"},
            {"name": "Allah Ghazanfar", "role": "bowler"},
            {"name": "Jasprit Bumrah", "role": "bowler"},
        ],
    },
    "PBKS": {
        "name": "Punjab Kings",
        "fielding_rating": 72.0,
        "recent_form": 0.68,
        "source_url": "https://www.iplt20.com/index.php/teams/punjab-kings",
        "squad": [
            {"name": "Shreyas Iyer", "role": "batter"},
            {"name": "Nehal Wadhera", "role": "batter"},
            {"name": "Vishnu Vinod", "role": "wicket_keeper"},
            {"name": "Harnoor Pannu", "role": "batter"},
            {"name": "Pyla Avinash", "role": "batter"},
            {"name": "Prabhsimran Singh", "role": "wicket_keeper"},
            {"name": "Shashank Singh", "role": "batter"},
            {"name": "Marcus Stoinis", "role": "all_rounder"},
            {"name": "Harpreet Brar", "role": "all_rounder"},
            {"name": "Marco Jansen", "role": "all_rounder"},
            {"name": "Azmatullah Omarzai", "role": "all_rounder"},
            {"name": "Priyansh Arya", "role": "all_rounder"},
            {"name": "Musheer Khan", "role": "all_rounder"},
            {"name": "Suryansh Shedge", "role": "all_rounder"},
            {"name": "Mitch Owen", "role": "all_rounder"},
            {"name": "Cooper Connolly", "role": "all_rounder"},
            {"name": "Ben Dwarshuis", "role": "all_rounder"},
            {"name": "Arshdeep Singh", "role": "bowler"},
            {"name": "Yuzvendra Chahal", "role": "bowler"},
            {"name": "Vyshak Vijaykumar", "role": "bowler"},
            {"name": "Yash Thakur", "role": "bowler"},
            {"name": "Xavier Bartlett", "role": "bowler"},
            {"name": "Pravin Dubey", "role": "bowler"},
            {"name": "Vishal Nishad", "role": "bowler"},
            {"name": "Lockie Ferguson", "role": "bowler"},
        ],
    },
    "RR": {
        "name": "Rajasthan Royals",
        "fielding_rating": 74.0,
        "recent_form": 0.58,
        "source_url": "https://www.iplt20.com/teams/rajasthan-royals",
        "squad": [
            {"name": "Sanju Samson", "role": "wicket_keeper"},
            {"name": "Riyan Parag", "role": "batter"},
            {"name": "Shubham Dubey", "role": "batter"},
            {"name": "Vaibhav Suryavanshi", "role": "batter"},
            {"name": "Donovan Ferreira", "role": "wicket_keeper"},
            {"name": "Lhuan-dre Pretorius", "role": "batter"},
            {"name": "Ravi Singh", "role": "wicket_keeper"},
            {"name": "Aman Rao Perala", "role": "batter"},
            {"name": "Shimron Hetmyer", "role": "batter"},
            {"name": "Yashasvi Jaiswal", "role": "batter"},
            {"name": "Dhruv Jurel", "role": "wicket_keeper"},
            {"name": "Yudhvir Singh Charak", "role": "all_rounder"},
            {"name": "Ravindra Jadeja", "role": "all_rounder"},
            {"name": "Sam Curran", "role": "all_rounder"},
            {"name": "Jofra Archer", "role": "bowler"},
            {"name": "Tushar Deshpande", "role": "bowler"},
            {"name": "Kwena Maphaka", "role": "bowler"},
            {"name": "Ravi Bishnoi", "role": "bowler"},
            {"name": "Sushant Mishra", "role": "bowler"},
            {"name": "Yash Raj Punja", "role": "bowler"},
            {"name": "Vignesh Puthur", "role": "bowler"},
            {"name": "Brijesh Sharma", "role": "bowler"},
            {"name": "Adam Milne", "role": "bowler"},
            {"name": "Kuldeep Sen", "role": "bowler"},
            {"name": "Sandeep Sharma", "role": "bowler"},
            {"name": "Nandre Burger", "role": "bowler"},
        ],
    },
    "RCB": {
        "name": "Royal Challengers Bengaluru",
        "fielding_rating": 75.0,
        "recent_form": 0.76,
        "source_url": "https://www.iplt20.com/teams/royal-challengers-bengaluru",
        "squad": [
            {"name": "Rajat Patidar", "role": "batter"},
            {"name": "Devdutt Padikkal", "role": "batter"},
            {"name": "Virat Kohli", "role": "batter"},
            {"name": "Phil Salt", "role": "wicket_keeper"},
            {"name": "Jitesh Sharma", "role": "wicket_keeper"},
            {"name": "Jordan Cox", "role": "wicket_keeper"},
            {"name": "Krunal Pandya", "role": "all_rounder"},
            {"name": "Swapnil Singh", "role": "all_rounder"},
            {"name": "Tim David", "role": "all_rounder"},
            {"name": "Romario Shepherd", "role": "all_rounder"},
            {"name": "Jacob Bethell", "role": "all_rounder"},
            {"name": "Venkatesh Iyer", "role": "all_rounder"},
            {"name": "Satvik Deswal", "role": "all_rounder"},
            {"name": "Mangesh Yadav", "role": "all_rounder"},
            {"name": "Vicky Ostwal", "role": "all_rounder"},
            {"name": "Vihaan Malhotra", "role": "all_rounder"},
            {"name": "Kanishk Chouhan", "role": "all_rounder"},
            {"name": "Josh Hazlewood", "role": "bowler"},
            {"name": "Rasikh Dar", "role": "bowler"},
            {"name": "Suyash Sharma", "role": "bowler"},
            {"name": "Bhuvneshwar Kumar", "role": "bowler"},
            {"name": "Yash Dayal", "role": "bowler"},
            {"name": "Nuwan Thushara", "role": "bowler"},
            {"name": "Abhinandan Singh", "role": "bowler"},
            {"name": "Jacob Duffy", "role": "bowler"},
        ],
    },
    "SRH": {
        "name": "Sunrisers Hyderabad",
        "fielding_rating": 74.0,
        "recent_form": 0.69,
        "source_url": "https://www.iplt20.com/teams/sunrisers-hyderabad/squad/2026",
        "squad": [
            {"name": "Ishan Kishan", "role": "wicket_keeper"},
            {"name": "Aniket Verma", "role": "batter"},
            {"name": "Smaran Ravichandran", "role": "batter"},
            {"name": "Salil Arora", "role": "wicket_keeper"},
            {"name": "Heinrich Klaasen", "role": "wicket_keeper"},
            {"name": "Travis Head", "role": "batter"},
            {"name": "Harshal Patel", "role": "all_rounder"},
            {"name": "Kamindu Mendis", "role": "all_rounder"},
            {"name": "Harsh Dubey", "role": "all_rounder"},
            {"name": "Brydon Carse", "role": "all_rounder"},
            {"name": "Liam Livingstone", "role": "all_rounder"},
            {"name": "Shivang Kumar", "role": "all_rounder"},
            {"name": "Krains Fuletra", "role": "all_rounder"},
            {"name": "Jack Edwards", "role": "all_rounder"},
            {"name": "Abhishek Sharma", "role": "all_rounder"},
            {"name": "Nitish Kumar Reddy", "role": "all_rounder"},
            {"name": "Pat Cummins", "role": "bowler"},
            {"name": "Zeeshan Ansari", "role": "bowler"},
            {"name": "Jaydev Unadkat", "role": "bowler"},
            {"name": "Eshan Malinga", "role": "bowler"},
            {"name": "Sakib Hussain", "role": "bowler"},
            {"name": "Onkar Tarmale", "role": "bowler"},
            {"name": "Amit Kumar", "role": "bowler"},
            {"name": "Praful Hinge", "role": "bowler"},
            {"name": "Shivam Mavi", "role": "bowler"},
        ],
    },
}

INTERNATIONAL_TEAMS: dict[str, dict[str, Any]] = {
    "IND": {
        "name": "India",
        "batting_rating": 82.0,
        "bowling_rating": 81.0,
        "fielding_rating": 80.0,
        "recent_form": 0.78,
        "source_url": "https://www.icc-cricket.com/",
        "squad": [
            # Openers / Top-order
            {"name": "Rohit Sharma", "role": "batter"},
            {"name": "Shubman Gill", "role": "batter"},
            {"name": "Virat Kohli", "role": "batter"},
            {"name": "Yashasvi Jaiswal", "role": "batter"},
            {"name": "Ruturaj Gaikwad", "role": "batter"},
            {"name": "Abhishek Sharma", "role": "batter"},
            # Middle order
            {"name": "Shreyas Iyer", "role": "batter"},
            {"name": "Suryakumar Yadav", "role": "batter"},
            {"name": "Tilak Varma", "role": "batter"},
            {"name": "Nitish Kumar Reddy", "role": "all_rounder"},
            # Wicketkeepers
            {"name": "Rishabh Pant", "role": "wicket_keeper"},
            {"name": "KL Rahul", "role": "wicket_keeper"},
            {"name": "Sanju Samson", "role": "wicket_keeper"},
            {"name": "Ishan Kishan", "role": "wicket_keeper"},
            {"name": "Dhruv Jurel", "role": "wicket_keeper"},
            # All-rounders
            {"name": "Hardik Pandya", "role": "all_rounder"},
            {"name": "Ravindra Jadeja", "role": "all_rounder"},
            {"name": "Axar Patel", "role": "all_rounder"},
            {"name": "Shivam Dube", "role": "all_rounder"},
            {"name": "Washington Sundar", "role": "all_rounder"},
            {"name": "Venkatesh Iyer", "role": "all_rounder"},
            {"name": "Shardul Thakur", "role": "all_rounder"},
            {"name": "Krunal Pandya", "role": "all_rounder"},
            # Spinners
            {"name": "Kuldeep Yadav", "role": "bowler"},
            {"name": "Varun Chakaravarthy", "role": "bowler"},
            {"name": "Ravi Bishnoi", "role": "bowler"},
            {"name": "Yuzvendra Chahal", "role": "bowler"},
            {"name": "Ravichandran Ashwin", "role": "bowler"},
            # Pacers
            {"name": "Jasprit Bumrah", "role": "bowler"},
            {"name": "Mohammed Shami", "role": "bowler"},
            {"name": "Mohammed Siraj", "role": "bowler"},
            {"name": "Arshdeep Singh", "role": "bowler"},
            {"name": "Deepak Chahar", "role": "bowler"},
            {"name": "Prasidh Krishna", "role": "bowler"},
            {"name": "Avesh Khan", "role": "bowler"},
            {"name": "Harshit Rana", "role": "bowler"},
            {"name": "Mukesh Kumar", "role": "bowler"},
            {"name": "T Natarajan", "role": "bowler"},
            {"name": "Akash Deep", "role": "bowler"},
            {"name": "Yash Dayal", "role": "bowler"},
        ],
    },
    "AUS": {
        "name": "Australia",
        "batting_rating": 80.0,
        "bowling_rating": 80.0,
        "fielding_rating": 81.0,
        "recent_form": 0.76,
        "source_url": "https://www.icc-cricket.com/",
        "squad": [
            # Top order
            {"name": "Travis Head", "role": "batter"},
            {"name": "Usman Khawaja", "role": "batter"},
            {"name": "Steve Smith", "role": "batter"},
            {"name": "Marnus Labuschagne", "role": "batter"},
            {"name": "Jake Fraser-McGurk", "role": "batter"},
            {"name": "Matt Short", "role": "batter"},
            {"name": "David Warner", "role": "batter"},
            # Wicketkeepers
            {"name": "Josh Inglis", "role": "wicket_keeper"},
            {"name": "Alex Carey", "role": "wicket_keeper"},
            {"name": "Matthew Wade", "role": "wicket_keeper"},
            {"name": "Ben McDermott", "role": "wicket_keeper"},
            # All-rounders
            {"name": "Glenn Maxwell", "role": "all_rounder"},
            {"name": "Cameron Green", "role": "all_rounder"},
            {"name": "Marcus Stoinis", "role": "all_rounder"},
            {"name": "Aaron Hardie", "role": "all_rounder"},
            {"name": "Ashton Agar", "role": "all_rounder"},
            {"name": "Matthew Short", "role": "all_rounder"},
            {"name": "Tim David", "role": "all_rounder"},
            # Bowlers
            {"name": "Pat Cummins", "role": "bowler"},
            {"name": "Mitchell Starc", "role": "bowler"},
            {"name": "Josh Hazlewood", "role": "bowler"},
            {"name": "Adam Zampa", "role": "bowler"},
            {"name": "Nathan Ellis", "role": "bowler"},
            {"name": "Sean Abbott", "role": "bowler"},
            {"name": "Spencer Johnson", "role": "bowler"},
            {"name": "Xavier Bartlett", "role": "bowler"},
            {"name": "Lance Morris", "role": "bowler"},
            {"name": "Nathan Coulter-Nile", "role": "bowler"},
            {"name": "Riley Meredith", "role": "bowler"},
            {"name": "Andrew Tye", "role": "bowler"},
            {"name": "Todd Murphy", "role": "bowler"},
            {"name": "Matthew Kuhnemann", "role": "bowler"},
        ],
    },
    "ENG": {
        "name": "England",
        "batting_rating": 78.0,
        "bowling_rating": 76.0,
        "fielding_rating": 77.0,
        "recent_form": 0.70,
        "source_url": "https://www.icc-cricket.com/",
        "squad": [
            # Top order
            {"name": "Jos Buttler", "role": "wicket_keeper"},
            {"name": "Phil Salt", "role": "wicket_keeper"},
            {"name": "Zak Crawley", "role": "batter"},
            {"name": "Ben Duckett", "role": "batter"},
            {"name": "Joe Root", "role": "batter"},
            {"name": "Harry Brook", "role": "batter"},
            {"name": "Dawid Malan", "role": "batter"},
            {"name": "Will Jacks", "role": "batter"},
            {"name": "Dan Lawrence", "role": "batter"},
            {"name": "Ben Stokes", "role": "all_rounder"},
            # All-rounders
            {"name": "Liam Livingstone", "role": "all_rounder"},
            {"name": "Jacob Bethell", "role": "all_rounder"},
            {"name": "Sam Curran", "role": "all_rounder"},
            {"name": "Chris Woakes", "role": "all_rounder"},
            {"name": "Moeen Ali", "role": "all_rounder"},
            {"name": "David Willey", "role": "all_rounder"},
            # Bowlers
            {"name": "Jofra Archer", "role": "bowler"},
            {"name": "Adil Rashid", "role": "bowler"},
            {"name": "Mark Wood", "role": "bowler"},
            {"name": "Gus Atkinson", "role": "bowler"},
            {"name": "Reece Topley", "role": "bowler"},
            {"name": "Brydon Carse", "role": "bowler"},
            {"name": "Saqib Mahmood", "role": "bowler"},
            {"name": "Tom Hartley", "role": "bowler"},
            {"name": "Shoaib Bashir", "role": "bowler"},
            {"name": "Matthew Potts", "role": "bowler"},
            {"name": "Ollie Robinson", "role": "bowler"},
            {"name": "Richard Gleeson", "role": "bowler"},
        ],
    },
    "PAK": {
        "name": "Pakistan",
        "batting_rating": 77.0,
        "bowling_rating": 78.0,
        "fielding_rating": 75.0,
        "recent_form": 0.68,
        "source_url": "https://www.icc-cricket.com/",
        "squad": [
            # Top order
            {"name": "Babar Azam", "role": "batter"},
            {"name": "Fakhar Zaman", "role": "batter"},
            {"name": "Saim Ayub", "role": "batter"},
            {"name": "Abdullah Shafique", "role": "batter"},
            {"name": "Imam-ul-Haq", "role": "batter"},
            {"name": "Kamran Ghulam", "role": "batter"},
            {"name": "Tayyab Tahir", "role": "batter"},
            # Wicketkeepers
            {"name": "Mohammad Rizwan", "role": "wicket_keeper"},
            {"name": "Mohammad Haris", "role": "wicket_keeper"},
            # Middle order / All-rounders
            {"name": "Saud Shakeel", "role": "batter"},
            {"name": "Salman Agha", "role": "all_rounder"},
            {"name": "Khushdil Shah", "role": "all_rounder"},
            {"name": "Shadab Khan", "role": "all_rounder"},
            {"name": "Imad Wasim", "role": "all_rounder"},
            {"name": "Mohammad Nawaz", "role": "all_rounder"},
            {"name": "Aamir Jamal", "role": "all_rounder"},
            {"name": "Faheem Ashraf", "role": "all_rounder"},
            # Bowlers
            {"name": "Shaheen Afridi", "role": "bowler"},
            {"name": "Haris Rauf", "role": "bowler"},
            {"name": "Naseem Shah", "role": "bowler"},
            {"name": "Abrar Ahmed", "role": "bowler"},
            {"name": "Mohammad Wasim Jr", "role": "bowler"},
            {"name": "Usman Khan", "role": "bowler"},
            {"name": "Zaman Khan", "role": "bowler"},
            {"name": "Hassan Ali", "role": "bowler"},
            {"name": "Mir Hamza", "role": "bowler"},
            {"name": "Mohammad Amir", "role": "bowler"},
        ],
    },
    "NZ": {
        "name": "New Zealand",
        "batting_rating": 76.0,
        "bowling_rating": 77.0,
        "fielding_rating": 79.0,
        "recent_form": 0.72,
        "source_url": "https://www.icc-cricket.com/",
        "squad": [
            # Top order
            {"name": "Kane Williamson", "role": "batter"},
            {"name": "Finn Allen", "role": "wicket_keeper"},
            {"name": "Devon Conway", "role": "wicket_keeper"},
            {"name": "Tom Latham", "role": "wicket_keeper"},
            {"name": "Tom Blundell", "role": "wicket_keeper"},
            {"name": "Tim Seifert", "role": "wicket_keeper"},
            {"name": "Will Young", "role": "batter"},
            {"name": "Henry Nicholls", "role": "batter"},
            {"name": "Glenn Phillips", "role": "batter"},
            {"name": "Mark Chapman", "role": "batter"},
            # All-rounders
            {"name": "Rachin Ravindra", "role": "all_rounder"},
            {"name": "Daryl Mitchell", "role": "all_rounder"},
            {"name": "Michael Bracewell", "role": "all_rounder"},
            {"name": "Mitchell Santner", "role": "all_rounder"},
            {"name": "James Neesham", "role": "all_rounder"},
            {"name": "Cole McConchie", "role": "all_rounder"},
            {"name": "Scott Kuggeleijn", "role": "all_rounder"},
            # Bowlers
            {"name": "Trent Boult", "role": "bowler"},
            {"name": "Tim Southee", "role": "bowler"},
            {"name": "Matt Henry", "role": "bowler"},
            {"name": "Kyle Jamieson", "role": "bowler"},
            {"name": "Lockie Ferguson", "role": "bowler"},
            {"name": "Adam Milne", "role": "bowler"},
            {"name": "Blair Tickner", "role": "bowler"},
            {"name": "Ben Sears", "role": "bowler"},
            {"name": "Jacob Duffy", "role": "bowler"},
            {"name": "Ish Sodhi", "role": "bowler"},
            {"name": "William O'Rourke", "role": "bowler"},
        ],
    },
    "SA": {
        "name": "South Africa",
        "batting_rating": 78.0,
        "bowling_rating": 80.0,
        "fielding_rating": 81.0,
        "recent_form": 0.75,
        "source_url": "https://www.icc-cricket.com/",
        "squad": [
            # Top order
            {"name": "Temba Bavuma", "role": "batter"},
            {"name": "Reeza Hendricks", "role": "batter"},
            {"name": "Tony de Zorzi", "role": "batter"},
            {"name": "Aiden Markram", "role": "batter"},
            {"name": "Rassie van der Dussen", "role": "batter"},
            {"name": "David Miller", "role": "batter"},
            {"name": "Matthew Breetzke", "role": "batter"},
            # Wicketkeepers
            {"name": "Quinton de Kock", "role": "wicket_keeper"},
            {"name": "Heinrich Klaasen", "role": "wicket_keeper"},
            {"name": "Ryan Rickelton", "role": "wicket_keeper"},
            # All-rounders
            {"name": "Tristan Stubbs", "role": "all_rounder"},
            {"name": "Marco Jansen", "role": "all_rounder"},
            {"name": "Wiaan Mulder", "role": "all_rounder"},
            {"name": "Andile Phehlukwayo", "role": "all_rounder"},
            {"name": "Dwaine Pretorius", "role": "all_rounder"},
            # Bowlers
            {"name": "Keshav Maharaj", "role": "bowler"},
            {"name": "Kagiso Rabada", "role": "bowler"},
            {"name": "Anrich Nortje", "role": "bowler"},
            {"name": "Lungi Ngidi", "role": "bowler"},
            {"name": "Tabraiz Shamsi", "role": "bowler"},
            {"name": "Gerald Coetzee", "role": "bowler"},
            {"name": "Ottneil Baartman", "role": "bowler"},
            {"name": "Nandre Burger", "role": "bowler"},
            {"name": "Lizaad Williams", "role": "bowler"},
            {"name": "Glenton Stuurman", "role": "bowler"},
        ],
    },
    "SL": {
        "name": "Sri Lanka",
        "batting_rating": 74.0,
        "bowling_rating": 75.0,
        "fielding_rating": 72.0,
        "recent_form": 0.64,
        "source_url": "https://www.icc-cricket.com/",
        "squad": [
            # Top order
            {"name": "Pathum Nissanka", "role": "batter"},
            {"name": "Avishka Fernando", "role": "batter"},
            {"name": "Oshada Fernando", "role": "batter"},
            {"name": "Charith Asalanka", "role": "batter"},
            {"name": "Dinesh Chandimal", "role": "batter"},
            {"name": "Angelo Mathews", "role": "all_rounder"},
            {"name": "Janith Liyanage", "role": "batter"},
            # Wicketkeepers
            {"name": "Kusal Mendis", "role": "wicket_keeper"},
            {"name": "Niroshan Dickwella", "role": "wicket_keeper"},
            {"name": "Sadeera Samarawickrama", "role": "wicket_keeper"},
            # All-rounders
            {"name": "Kamindu Mendis", "role": "all_rounder"},
            {"name": "Dasun Shanaka", "role": "all_rounder"},
            {"name": "Wanindu Hasaranga", "role": "all_rounder"},
            {"name": "Dhananjaya de Silva", "role": "all_rounder"},
            {"name": "Chamika Karunaratne", "role": "all_rounder"},
            {"name": "Dunith Wellalage", "role": "all_rounder"},
            # Bowlers
            {"name": "Maheesh Theekshana", "role": "bowler"},
            {"name": "Nuwan Thushara", "role": "bowler"},
            {"name": "Asitha Fernando", "role": "bowler"},
            {"name": "Lahiru Kumara", "role": "bowler"},
            {"name": "Matheesha Pathirana", "role": "bowler"},
            {"name": "Jeffrey Vandersay", "role": "bowler"},
            {"name": "Pramod Madushan", "role": "bowler"},
            {"name": "Vishwa Fernando", "role": "bowler"},
            {"name": "Kasun Rajitha", "role": "bowler"},
            {"name": "Dilshan Madushanka", "role": "bowler"},
        ],
    },
    "WI": {
        "name": "West Indies",
        "batting_rating": 76.0,
        "bowling_rating": 74.0,
        "fielding_rating": 75.0,
        "recent_form": 0.66,
        "source_url": "https://www.icc-cricket.com/",
        "squad": [
            # Top order
            {"name": "Kyle Mayers", "role": "all_rounder"},
            {"name": "Brandon King", "role": "batter"},
            {"name": "Johnson Charles", "role": "batter"},
            {"name": "Alick Athanaze", "role": "batter"},
            {"name": "Keacy Carty", "role": "batter"},
            {"name": "Rovman Powell", "role": "batter"},
            {"name": "Shimron Hetmyer", "role": "batter"},
            {"name": "Justin Greaves", "role": "batter"},
            # Wicketkeepers
            {"name": "Nicholas Pooran", "role": "wicket_keeper"},
            {"name": "Shai Hope", "role": "wicket_keeper"},
            {"name": "Jewel Andrew", "role": "wicket_keeper"},
            # All-rounders
            {"name": "Andre Russell", "role": "all_rounder"},
            {"name": "Jason Holder", "role": "all_rounder"},
            {"name": "Romario Shepherd", "role": "all_rounder"},
            {"name": "Fabian Allen", "role": "all_rounder"},
            {"name": "Odean Smith", "role": "all_rounder"},
            {"name": "Yannic Cariah", "role": "all_rounder"},
            # Bowlers
            {"name": "Alzarri Joseph", "role": "bowler"},
            {"name": "Shamar Joseph", "role": "bowler"},
            {"name": "Jayden Seales", "role": "bowler"},
            {"name": "Kemar Roach", "role": "bowler"},
            {"name": "Akeal Hosein", "role": "bowler"},
            {"name": "Gudakesh Motie", "role": "bowler"},
            {"name": "Oshane Thomas", "role": "bowler"},
            {"name": "Anderson Phillip", "role": "bowler"},
        ],
    },
    "BAN": {
        "name": "Bangladesh",
        "batting_rating": 68.0,
        "bowling_rating": 70.0,
        "fielding_rating": 67.0,
        "recent_form": 0.57,
        "source_url": "https://www.icc-cricket.com/",
        "squad": [
            # Top order
            {"name": "Tanzid Hasan", "role": "batter"},
            {"name": "Soumya Sarkar", "role": "batter"},
            {"name": "Najmul Hossain Shanto", "role": "batter"},
            {"name": "Mominul Haque", "role": "batter"},
            {"name": "Towhid Hridoy", "role": "batter"},
            {"name": "Naim Sheikh", "role": "batter"},
            {"name": "Anamul Haque", "role": "batter"},
            {"name": "Afif Hossain", "role": "all_rounder"},
            # Wicketkeepers
            {"name": "Litton Das", "role": "wicket_keeper"},
            {"name": "Mushfiqur Rahim", "role": "wicket_keeper"},
            {"name": "Nurul Hasan", "role": "wicket_keeper"},
            # All-rounders
            {"name": "Shakib Al Hasan", "role": "all_rounder"},
            {"name": "Mahmudullah", "role": "all_rounder"},
            {"name": "Mehidy Hasan Miraz", "role": "all_rounder"},
            {"name": "Rishad Hossain", "role": "all_rounder"},
            {"name": "Mosaddek Hossain", "role": "all_rounder"},
            {"name": "Mahedi Hasan", "role": "all_rounder"},
            {"name": "Nasum Ahmed", "role": "all_rounder"},
            # Bowlers
            {"name": "Taskin Ahmed", "role": "bowler"},
            {"name": "Mustafizur Rahman", "role": "bowler"},
            {"name": "Shoriful Islam", "role": "bowler"},
            {"name": "Hasan Mahmud", "role": "bowler"},
            {"name": "Ebadot Hossain", "role": "bowler"},
            {"name": "Khaled Ahmed", "role": "bowler"},
            {"name": "Nayeem Hasan", "role": "bowler"},
            {"name": "Tanzim Hasan Sakib", "role": "bowler"},
        ],
    },
    "AFG": {
        "name": "Afghanistan",
        "batting_rating": 70.0,
        "bowling_rating": 77.0,
        "fielding_rating": 70.0,
        "recent_form": 0.70,
        "source_url": "https://www.icc-cricket.com/",
        "squad": [
            # Top order
            {"name": "Rahmanullah Gurbaz", "role": "wicket_keeper"},
            {"name": "Ibrahim Zadran", "role": "batter"},
            {"name": "Hazratullah Zazai", "role": "batter"},
            {"name": "Rahmat Shah", "role": "batter"},
            {"name": "Darwish Rasooli", "role": "batter"},
            {"name": "Sediqullah Atal", "role": "batter"},
            {"name": "Riaz Hassan", "role": "batter"},
            # Middle order / wicketkeepers
            {"name": "Najibullah Zadran", "role": "batter"},
            {"name": "Ikram Ali Khil", "role": "wicket_keeper"},
            # All-rounders
            {"name": "Mohammad Nabi", "role": "all_rounder"},
            {"name": "Gulbadin Naib", "role": "all_rounder"},
            {"name": "Azmatullah Omarzai", "role": "all_rounder"},
            {"name": "Mohammad Ishaq", "role": "all_rounder"},
            {"name": "Karim Janat", "role": "all_rounder"},
            # Bowlers
            {"name": "Rashid Khan", "role": "bowler"},
            {"name": "Noor Ahmad", "role": "bowler"},
            {"name": "Mujeeb Ur Rahman", "role": "bowler"},
            {"name": "Allah Ghazanfar", "role": "bowler"},
            {"name": "Fazalhaq Farooqi", "role": "bowler"},
            {"name": "Naveen-ul-Haq", "role": "bowler"},
            {"name": "Qais Ahmad", "role": "bowler"},
            {"name": "Nijat Masood", "role": "bowler"},
            {"name": "Bilal Sami", "role": "bowler"},
            {"name": "Fareed Ahmad", "role": "bowler"},
        ],
    },
    "ZIM": {
        "name": "Zimbabwe",
        "batting_rating": 60.0,
        "bowling_rating": 62.0,
        "fielding_rating": 61.0,
        "recent_form": 0.50,
        "source_url": "https://www.icc-cricket.com/",
        "squad": [
            {"name": "Craig Ervine", "role": "batter"},
            {"name": "Tadiwanashe Marumani", "role": "batter"},
            {"name": "Innocent Kaia", "role": "batter"},
            {"name": "Sean Williams", "role": "all_rounder"},
            {"name": "Sikandar Raza", "role": "all_rounder"},
            {"name": "Regis Chakabva", "role": "wicket_keeper"},
            {"name": "Clive Madande", "role": "wicket_keeper"},
            {"name": "Ryan Burl", "role": "all_rounder"},
            {"name": "Wesley Madhevere", "role": "all_rounder"},
            {"name": "Tony Munyonga", "role": "batter"},
            {"name": "Milton Shumba", "role": "batter"},
            {"name": "Brian Bennett", "role": "all_rounder"},
            {"name": "Blessing Muzarabani", "role": "bowler"},
            {"name": "Tendai Chatara", "role": "bowler"},
            {"name": "Victor Nyauchi", "role": "bowler"},
            {"name": "Tanaka Chivanga", "role": "bowler"},
            {"name": "Wellington Masakadza", "role": "bowler"},
            {"name": "Trevor Gwandu", "role": "bowler"},
            {"name": "Donald Tiripano", "role": "bowler"},
        ],
    },
    "IRE": {
        "name": "Ireland",
        "batting_rating": 58.0,
        "bowling_rating": 60.0,
        "fielding_rating": 60.0,
        "recent_form": 0.48,
        "source_url": "https://www.icc-cricket.com/",
        "squad": [
            {"name": "Paul Stirling", "role": "batter"},
            {"name": "Andrew Balbirnie", "role": "batter"},
            {"name": "Lorcan Tucker", "role": "wicket_keeper"},
            {"name": "Stephen Doheny", "role": "wicket_keeper"},
            {"name": "Harry Tector", "role": "batter"},
            {"name": "Curtis Campher", "role": "all_rounder"},
            {"name": "Gareth Delany", "role": "all_rounder"},
            {"name": "George Dockrell", "role": "all_rounder"},
            {"name": "Simi Singh", "role": "all_rounder"},
            {"name": "Mark Adair", "role": "all_rounder"},
            {"name": "Andy McBrine", "role": "all_rounder"},
            {"name": "Ross Adair", "role": "batter"},
            {"name": "Josh Little", "role": "bowler"},
            {"name": "Barry McCarthy", "role": "bowler"},
            {"name": "Craig Young", "role": "bowler"},
            {"name": "Graham Hume", "role": "bowler"},
            {"name": "Ben White", "role": "bowler"},
            {"name": "Fionn Hand", "role": "bowler"},
        ],
    },
    "SCO": {
        "name": "Scotland",
        "batting_rating": 55.0,
        "bowling_rating": 57.0,
        "fielding_rating": 58.0,
        "recent_form": 0.45,
        "source_url": "https://www.icc-cricket.com/",
        "squad": [
            {"name": "George Munsey", "role": "batter"},
            {"name": "Matthew Cross", "role": "wicket_keeper"},
            {"name": "Richie Berrington", "role": "all_rounder"},
            {"name": "Calum MacLeod", "role": "batter"},
            {"name": "Michael Jones", "role": "batter"},
            {"name": "Brandon McMullen", "role": "all_rounder"},
            {"name": "Chris Greaves", "role": "all_rounder"},
            {"name": "Michael Leask", "role": "all_rounder"},
            {"name": "Mark Watt", "role": "bowler"},
            {"name": "Brad Wheal", "role": "bowler"},
            {"name": "Safyaan Sharif", "role": "bowler"},
            {"name": "Charlie Tear", "role": "batter"},
            {"name": "Jack Jarvis", "role": "bowler"},
            {"name": "Hamish Gardiner", "role": "batter"},
        ],
    },
    "NED": {
        "name": "Netherlands",
        "batting_rating": 56.0,
        "bowling_rating": 58.0,
        "fielding_rating": 59.0,
        "recent_form": 0.46,
        "source_url": "https://www.icc-cricket.com/",
        "squad": [
            {"name": "Max O'Dowd", "role": "batter"},
            {"name": "Vikramjit Singh", "role": "batter"},
            {"name": "Bas de Leede", "role": "all_rounder"},
            {"name": "Scott Edwards", "role": "wicket_keeper"},
            {"name": "Tom Cooper", "role": "batter"},
            {"name": "Teja Nidamanuru", "role": "batter"},
            {"name": "Saqib Zulfiqar", "role": "bowler"},
            {"name": "Tim Pringle", "role": "all_rounder"},
            {"name": "Aryan Dutt", "role": "all_rounder"},
            {"name": "Roelof van der Merwe", "role": "all_rounder"},
            {"name": "Logan van Beek", "role": "all_rounder"},
            {"name": "Vivian Kingma", "role": "bowler"},
            {"name": "Sijde van Tilburg", "role": "bowler"},
            {"name": "Paul van Meekeren", "role": "bowler"},
            {"name": "Shane Snater", "role": "bowler"},
        ],
    },
}

IPL_VENUES: dict[str, dict[str, Any]] = {
    "AMD": {
        "name": "Narendra Modi Stadium",
        "city": "Ahmedabad",
        "country": "India",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "medium",
        "spin_level": "low",
        "straight_boundary_m": 74,
        "square_boundary_m": 63,
        "average_first_innings_score_t20": 178,
        "average_first_innings_score_odi": 286,
        "highest_t20": 243,
        "lowest_defended_t20": 162,
        "typical_winning_score_t20": 185,
        "highest_odi": 365,
    },
    "BLR": {
        "name": "M Chinnaswamy Stadium",
        "city": "Bengaluru",
        "country": "India",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "low",
        "spin_level": "low",
        "straight_boundary_m": 68,
        "square_boundary_m": 61,
        "average_first_innings_score_t20": 183,
        "average_first_innings_score_odi": 295,
        "highest_t20": 287,
        "lowest_defended_t20": 170,
        "typical_winning_score_t20": 195,
        "highest_odi": 383,
    },
    "CHE": {
        "name": "MA Chidambaram Stadium",
        "city": "Chennai",
        "country": "India",
        "surface": "spin",
        "batting_level": "medium",
        "pace_level": "low",
        "spin_level": "high",
        "straight_boundary_m": 74,
        "square_boundary_m": 68,
        "average_first_innings_score_t20": 164,
        "average_first_innings_score_odi": 255,
        "highest_t20": 246,
        "lowest_defended_t20": 150,
        "typical_winning_score_t20": 170,
        "highest_odi": 337,
    },
    "DEL": {
        "name": "Arun Jaitley Stadium",
        "city": "Delhi",
        "country": "India",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "medium",
        "spin_level": "low",
        "straight_boundary_m": 67,
        "square_boundary_m": 60,
        "average_first_innings_score_t20": 177,
        "average_first_innings_score_odi": 272,
        "highest_t20": 266,
        "lowest_defended_t20": 156,
        "typical_winning_score_t20": 182,
        "highest_odi": 428,
    },
    "HYD": {
        "name": "Rajiv Gandhi International Stadium",
        "city": "Hyderabad",
        "country": "India",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "medium",
        "spin_level": "low",
        "straight_boundary_m": 76,
        "square_boundary_m": 69,
        "average_first_innings_score_t20": 176,
        "average_first_innings_score_odi": 289,
        "highest_t20": 286,
        "lowest_defended_t20": 160,
        "typical_winning_score_t20": 184,
        "highest_odi": 350,
    },
    "JAI": {
        "name": "Sawai Mansingh Stadium",
        "city": "Jaipur",
        "country": "India",
        "surface": "balanced",
        "batting_level": "medium",
        "pace_level": "medium",
        "spin_level": "medium",
        "straight_boundary_m": 75,
        "square_boundary_m": 68,
        "average_first_innings_score_t20": 171,
        "average_first_innings_score_odi": 272,
        "highest_t20": 217,
        "lowest_defended_t20": 145,
        "typical_winning_score_t20": 176,
        "highest_odi": 362,
    },
    "KOL": {
        "name": "Eden Gardens",
        "city": "Kolkata",
        "country": "India",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "medium",
        "spin_level": "low",
        "straight_boundary_m": 76,
        "square_boundary_m": 66,
        "average_first_innings_score_t20": 175,
        "average_first_innings_score_odi": 281,
        "highest_t20": 262,
        "lowest_defended_t20": 154,
        "typical_winning_score_t20": 182,
        "highest_odi": 404,
    },
    "LKO": {
        "name": "Ekana Cricket Stadium",
        "city": "Lucknow",
        "country": "India",
        "surface": "slow",
        "batting_level": "low",
        "pace_level": "medium",
        "spin_level": "high",
        "straight_boundary_m": 78,
        "square_boundary_m": 70,
        "average_first_innings_score_t20": 160,
        "average_first_innings_score_odi": 250,
        "highest_t20": 235,
        "lowest_defended_t20": 138,
        "typical_winning_score_t20": 166,
        "highest_odi": 311,
    },
    "MOH": {
        "name": "Maharaja Yadavindra Singh Stadium",
        "city": "Mullanpur",
        "country": "India",
        "surface": "balanced",
        "batting_level": "medium",
        "pace_level": "medium",
        "spin_level": "medium",
        "straight_boundary_m": 78,
        "square_boundary_m": 70,
        "average_first_innings_score_t20": 168,
        "average_first_innings_score_odi": 268,
        "highest_t20": 219,
        "lowest_defended_t20": 143,
        "typical_winning_score_t20": 174,
        "highest_odi": 0,
    },
    "MUM": {
        "name": "Wankhede Stadium",
        "city": "Mumbai",
        "country": "India",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "medium",
        "spin_level": "low",
        "straight_boundary_m": 70,
        "square_boundary_m": 64,
        "average_first_innings_score_t20": 182,
        "average_first_innings_score_odi": 287,
        "highest_t20": 235,
        "lowest_defended_t20": 143,
        "typical_winning_score_t20": 190,
        "highest_odi": 438,
    },
    "GUW": {
        "name": "Barsapara Cricket Stadium",
        "city": "Guwahati",
        "country": "India",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "medium",
        "spin_level": "low",
        "straight_boundary_m": 74,
        "square_boundary_m": 65,
        "average_first_innings_score_t20": 180,
        "average_first_innings_score_odi": 290,
        "highest_t20": 237,
        "lowest_defended_t20": 160,
        "typical_winning_score_t20": 188,
        "highest_odi": 373,
    },
}

INTERNATIONAL_VENUES: dict[str, dict[str, Any]] = {
    "LORDS": {
        "name": "Lord's",
        "city": "London",
        "country": "England",
        "surface": "balanced",
        "batting_level": "medium",
        "pace_level": "medium",
        "spin_level": "medium",
        "straight_boundary_m": 73,
        "square_boundary_m": 63,
        "average_first_innings_score_t20": 166,
        "average_first_innings_score_odi": 255,
        "average_first_innings_score_test": 302,
        "highest_t20": 193,
        "highest_odi": 334,
        "highest_test": 729,
        "lowest_defended_t20": 129,
        "typical_winning_score_t20": 170,
    },
    "OVAL": {
        "name": "The Oval",
        "city": "London",
        "country": "England",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "medium",
        "spin_level": "low",
        "straight_boundary_m": 73,
        "square_boundary_m": 66,
        "average_first_innings_score_t20": 171,
        "average_first_innings_score_odi": 270,
        "average_first_innings_score_test": 325,
        "highest_t20": 211,
        "highest_odi": 398,
        "highest_test": 903,
        "lowest_defended_t20": 146,
        "typical_winning_score_t20": 176,
    },
    "MCG": {
        "name": "Melbourne Cricket Ground",
        "city": "Melbourne",
        "country": "Australia",
        "surface": "balanced",
        "batting_level": "medium",
        "pace_level": "medium",
        "spin_level": "low",
        "straight_boundary_m": 84,
        "square_boundary_m": 72,
        "average_first_innings_score_t20": 158,
        "average_first_innings_score_odi": 242,
        "average_first_innings_score_test": 312,
        "highest_t20": 222,
        "highest_odi": 355,
        "highest_test": 604,
        "lowest_defended_t20": 127,
        "typical_winning_score_t20": 165,
    },
    "SCG": {
        "name": "Sydney Cricket Ground",
        "city": "Sydney",
        "country": "Australia",
        "surface": "balanced",
        "batting_level": "medium",
        "pace_level": "medium",
        "spin_level": "medium",
        "straight_boundary_m": 74,
        "square_boundary_m": 66,
        "average_first_innings_score_t20": 162,
        "average_first_innings_score_odi": 257,
        "average_first_innings_score_test": 308,
        "highest_t20": 221,
        "highest_odi": 408,
        "highest_test": 705,
        "lowest_defended_t20": 134,
        "typical_winning_score_t20": 168,
    },
    "ADE": {
        "name": "Adelaide Oval",
        "city": "Adelaide",
        "country": "Australia",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "low",
        "spin_level": "low",
        "straight_boundary_m": 76,
        "square_boundary_m": 66,
        "average_first_innings_score_t20": 173,
        "average_first_innings_score_odi": 281,
        "average_first_innings_score_test": 340,
        "highest_t20": 233,
        "highest_odi": 369,
        "highest_test": 674,
        "lowest_defended_t20": 153,
        "typical_winning_score_t20": 178,
    },
    "DUB": {
        "name": "Dubai International Cricket Stadium",
        "city": "Dubai",
        "country": "United Arab Emirates",
        "surface": "balanced",
        "batting_level": "medium",
        "pace_level": "medium",
        "spin_level": "medium",
        "straight_boundary_m": 78,
        "square_boundary_m": 69,
        "average_first_innings_score_t20": 152,
        "average_first_innings_score_odi": 228,
        "average_first_innings_score_test": 295,
        "highest_t20": 212,
        "highest_odi": 355,
        "highest_test": 589,
        "lowest_defended_t20": 135,
        "typical_winning_score_t20": 160,
    },
    "SHA": {
        "name": "Sharjah Cricket Stadium",
        "city": "Sharjah",
        "country": "United Arab Emirates",
        "surface": "slow",
        "batting_level": "medium",
        "pace_level": "low",
        "spin_level": "high",
        "straight_boundary_m": 68,
        "square_boundary_m": 62,
        "average_first_innings_score_t20": 154,
        "average_first_innings_score_odi": 236,
        "average_first_innings_score_test": 270,
        "highest_t20": 215,
        "highest_odi": 364,
        "highest_test": 511,
        "lowest_defended_t20": 132,
        "typical_winning_score_t20": 162,
    },
    "WAN": {
        "name": "Wanderers Stadium",
        "city": "Johannesburg",
        "country": "South Africa",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "medium",
        "spin_level": "low",
        "straight_boundary_m": 78,
        "square_boundary_m": 68,
        "average_first_innings_score_t20": 171,
        "average_first_innings_score_odi": 286,
        "average_first_innings_score_test": 342,
        "highest_t20": 260,
        "highest_odi": 439,
        "highest_test": 652,
        "lowest_defended_t20": 145,
        "typical_winning_score_t20": 180,
    },
    "NEW": {
        "name": "Newlands",
        "city": "Cape Town",
        "country": "South Africa",
        "surface": "balanced",
        "batting_level": "medium",
        "pace_level": "medium",
        "spin_level": "medium",
        "straight_boundary_m": 75,
        "square_boundary_m": 67,
        "average_first_innings_score_t20": 161,
        "average_first_innings_score_odi": 248,
        "average_first_innings_score_test": 290,
        "highest_t20": 210,
        "highest_odi": 367,
        "highest_test": 619,
        "lowest_defended_t20": 129,
        "typical_winning_score_t20": 168,
    },
    "SSP": {
        "name": "SuperSport Park",
        "city": "Centurion",
        "country": "South Africa",
        "surface": "pace",
        "batting_level": "medium",
        "pace_level": "high",
        "spin_level": "low",
        "straight_boundary_m": 76,
        "square_boundary_m": 69,
        "average_first_innings_score_t20": 168,
        "average_first_innings_score_odi": 275,
        "average_first_innings_score_test": 318,
        "highest_t20": 219,
        "highest_odi": 418,
        "highest_test": 620,
        "lowest_defended_t20": 140,
        "typical_winning_score_t20": 176,
    },
    "EDP": {
        "name": "Eden Park",
        "city": "Auckland",
        "country": "New Zealand",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "low",
        "spin_level": "low",
        "straight_boundary_m": 70,
        "square_boundary_m": 58,
        "average_first_innings_score_t20": 176,
        "average_first_innings_score_odi": 272,
        "average_first_innings_score_test": 304,
        "highest_t20": 245,
        "highest_odi": 340,
        "highest_test": 671,
        "lowest_defended_t20": 150,
        "typical_winning_score_t20": 182,
    },
    "HAG": {
        "name": "Hagley Oval",
        "city": "Christchurch",
        "country": "New Zealand",
        "surface": "pace",
        "batting_level": "medium",
        "pace_level": "high",
        "spin_level": "low",
        "straight_boundary_m": 74,
        "square_boundary_m": 64,
        "average_first_innings_score_t20": 162,
        "average_first_innings_score_odi": 258,
        "average_first_innings_score_test": 292,
        "highest_t20": 214,
        "highest_odi": 341,
        "highest_test": 578,
        "lowest_defended_t20": 138,
        "typical_winning_score_t20": 168,
    },
    "GAL": {
        "name": "Galle International Stadium",
        "city": "Galle",
        "country": "Sri Lanka",
        "surface": "spin",
        "batting_level": "low",
        "pace_level": "low",
        "spin_level": "high",
        "straight_boundary_m": 72,
        "square_boundary_m": 64,
        "average_first_innings_score_t20": 149,
        "average_first_innings_score_odi": 228,
        "average_first_innings_score_test": 242,
        "highest_t20": 209,
        "highest_odi": 294,
        "highest_test": 713,
        "lowest_defended_t20": 125,
        "typical_winning_score_t20": 156,
    },
    "RPS": {
        "name": "R. Premadasa Stadium",
        "city": "Colombo",
        "country": "Sri Lanka",
        "surface": "spin",
        "batting_level": "medium",
        "pace_level": "low",
        "spin_level": "high",
        "straight_boundary_m": 68,
        "square_boundary_m": 61,
        "average_first_innings_score_t20": 158,
        "average_first_innings_score_odi": 244,
        "average_first_innings_score_test": 268,
        "highest_t20": 231,
        "highest_odi": 443,
        "highest_test": 952,
        "lowest_defended_t20": 130,
        "typical_winning_score_t20": 165,
    },
    "KEN": {
        "name": "Kensington Oval",
        "city": "Bridgetown",
        "country": "Barbados",
        "surface": "pace",
        "batting_level": "medium",
        "pace_level": "high",
        "spin_level": "low",
        "straight_boundary_m": 73,
        "square_boundary_m": 65,
        "average_first_innings_score_t20": 163,
        "average_first_innings_score_odi": 258,
        "average_first_innings_score_test": 295,
        "highest_t20": 212,
        "highest_odi": 325,
        "highest_test": 749,
        "lowest_defended_t20": 136,
        "typical_winning_score_t20": 170,
    },
    "MIR": {
        "name": "Shere Bangla National Stadium",
        "city": "Dhaka",
        "country": "Bangladesh",
        "surface": "slow",
        "batting_level": "low",
        "pace_level": "low",
        "spin_level": "high",
        "straight_boundary_m": 73,
        "square_boundary_m": 65,
        "average_first_innings_score_t20": 145,
        "average_first_innings_score_odi": 233,
        "average_first_innings_score_test": 258,
        "highest_t20": 211,
        "highest_odi": 370,
        "highest_test": 638,
        "lowest_defended_t20": 120,
        "typical_winning_score_t20": 154,
    },
    # ── India ──────────────────────────────────────────────────────────────
    "WANK": {
        "name": "Wankhede Stadium",
        "city": "Mumbai",
        "country": "India",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "low",
        "spin_level": "medium",
        "straight_boundary_m": 68,
        "square_boundary_m": 60,
        "average_first_innings_score_t20": 172,
        "average_first_innings_score_odi": 268,
        "average_first_innings_score_test": 310,
        "highest_t20": 235,
        "highest_odi": 418,
        "highest_test": 554,
        "lowest_defended_t20": 148,
        "typical_winning_score_t20": 179,
    },
    "EG": {
        "name": "Eden Gardens",
        "city": "Kolkata",
        "country": "India",
        "surface": "spin",
        "batting_level": "medium",
        "pace_level": "low",
        "spin_level": "high",
        "straight_boundary_m": 70,
        "square_boundary_m": 65,
        "average_first_innings_score_t20": 158,
        "average_first_innings_score_odi": 248,
        "average_first_innings_score_test": 285,
        "highest_t20": 208,
        "highest_odi": 338,
        "highest_test": 657,
        "lowest_defended_t20": 132,
        "typical_winning_score_t20": 165,
    },
    "NMS": {
        "name": "Narendra Modi Stadium",
        "city": "Ahmedabad",
        "country": "India",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "low",
        "spin_level": "medium",
        "straight_boundary_m": 82,
        "square_boundary_m": 72,
        "average_first_innings_score_t20": 163,
        "average_first_innings_score_odi": 258,
        "average_first_innings_score_test": 305,
        "highest_t20": 224,
        "highest_odi": 356,
        "highest_test": 600,
        "lowest_defended_t20": 140,
        "typical_winning_score_t20": 171,
    },
    "MCB": {
        "name": "M. Chinnaswamy Stadium",
        "city": "Bengaluru",
        "country": "India",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "low",
        "spin_level": "medium",
        "straight_boundary_m": 70,
        "square_boundary_m": 61,
        "average_first_innings_score_t20": 176,
        "average_first_innings_score_odi": 272,
        "average_first_innings_score_test": 318,
        "highest_t20": 263,
        "highest_odi": 383,
        "highest_test": 541,
        "lowest_defended_t20": 152,
        "typical_winning_score_t20": 183,
    },
    "CHE": {
        "name": "MA Chidambaram Stadium",
        "city": "Chennai",
        "country": "India",
        "surface": "spin",
        "batting_level": "low",
        "pace_level": "low",
        "spin_level": "high",
        "straight_boundary_m": 68,
        "square_boundary_m": 62,
        "average_first_innings_score_t20": 153,
        "average_first_innings_score_odi": 236,
        "average_first_innings_score_test": 268,
        "highest_t20": 208,
        "highest_odi": 316,
        "highest_test": 630,
        "lowest_defended_t20": 126,
        "typical_winning_score_t20": 160,
    },
    "KOTLA": {
        "name": "Arun Jaitley Stadium",
        "city": "Delhi",
        "country": "India",
        "surface": "balanced",
        "batting_level": "medium",
        "pace_level": "medium",
        "spin_level": "medium",
        "straight_boundary_m": 71,
        "square_boundary_m": 64,
        "average_first_innings_score_t20": 164,
        "average_first_innings_score_odi": 260,
        "average_first_innings_score_test": 298,
        "highest_t20": 224,
        "highest_odi": 338,
        "highest_test": 547,
        "lowest_defended_t20": 138,
        "typical_winning_score_t20": 171,
    },
    "RGIS": {
        "name": "Rajiv Gandhi Intl. Stadium",
        "city": "Hyderabad",
        "country": "India",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "low",
        "spin_level": "medium",
        "straight_boundary_m": 72,
        "square_boundary_m": 64,
        "average_first_innings_score_t20": 168,
        "average_first_innings_score_odi": 268,
        "average_first_innings_score_test": 312,
        "highest_t20": 217,
        "highest_odi": 350,
        "highest_test": 506,
        "lowest_defended_t20": 142,
        "typical_winning_score_t20": 175,
    },
    "MOHALI": {
        "name": "PCA Stadium",
        "city": "Mohali",
        "country": "India",
        "surface": "pace",
        "batting_level": "medium",
        "pace_level": "high",
        "spin_level": "low",
        "straight_boundary_m": 74,
        "square_boundary_m": 66,
        "average_first_innings_score_t20": 162,
        "average_first_innings_score_odi": 262,
        "average_first_innings_score_test": 308,
        "highest_t20": 211,
        "highest_odi": 356,
        "highest_test": 469,
        "lowest_defended_t20": 136,
        "typical_winning_score_t20": 168,
    },
    # ── England ────────────────────────────────────────────────────────────
    "MANC": {
        "name": "Old Trafford",
        "city": "Manchester",
        "country": "England",
        "surface": "balanced",
        "batting_level": "medium",
        "pace_level": "medium",
        "spin_level": "medium",
        "straight_boundary_m": 74,
        "square_boundary_m": 64,
        "average_first_innings_score_t20": 163,
        "average_first_innings_score_odi": 252,
        "average_first_innings_score_test": 292,
        "highest_t20": 198,
        "highest_odi": 363,
        "highest_test": 627,
        "lowest_defended_t20": 138,
        "typical_winning_score_t20": 169,
    },
    "HEADS": {
        "name": "Headingley",
        "city": "Leeds",
        "country": "England",
        "surface": "pace",
        "batting_level": "medium",
        "pace_level": "high",
        "spin_level": "low",
        "straight_boundary_m": 72,
        "square_boundary_m": 62,
        "average_first_innings_score_t20": 158,
        "average_first_innings_score_odi": 245,
        "average_first_innings_score_test": 280,
        "highest_t20": 193,
        "highest_odi": 332,
        "highest_test": 580,
        "lowest_defended_t20": 132,
        "typical_winning_score_t20": 164,
    },
    "EDGAR": {
        "name": "Edgbaston",
        "city": "Birmingham",
        "country": "England",
        "surface": "balanced",
        "batting_level": "medium",
        "pace_level": "medium",
        "spin_level": "medium",
        "straight_boundary_m": 74,
        "square_boundary_m": 65,
        "average_first_innings_score_t20": 167,
        "average_first_innings_score_odi": 264,
        "average_first_innings_score_test": 302,
        "highest_t20": 202,
        "highest_odi": 366,
        "highest_test": 601,
        "lowest_defended_t20": 142,
        "typical_winning_score_t20": 174,
    },
    "TRENT": {
        "name": "Trent Bridge",
        "city": "Nottingham",
        "country": "England",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "medium",
        "spin_level": "low",
        "straight_boundary_m": 74,
        "square_boundary_m": 66,
        "average_first_innings_score_t20": 172,
        "average_first_innings_score_odi": 278,
        "average_first_innings_score_test": 325,
        "highest_t20": 229,
        "highest_odi": 444,
        "highest_test": 658,
        "lowest_defended_t20": 148,
        "typical_winning_score_t20": 179,
    },
    "SOTON": {
        "name": "Ageas Bowl",
        "city": "Southampton",
        "country": "England",
        "surface": "balanced",
        "batting_level": "medium",
        "pace_level": "medium",
        "spin_level": "medium",
        "straight_boundary_m": 72,
        "square_boundary_m": 63,
        "average_first_innings_score_t20": 158,
        "average_first_innings_score_odi": 248,
        "average_first_innings_score_test": 285,
        "highest_t20": 200,
        "highest_odi": 330,
        "highest_test": 583,
        "lowest_defended_t20": 134,
        "typical_winning_score_t20": 164,
    },
    # ── Australia ──────────────────────────────────────────────────────────
    "GABBA": {
        "name": "The Gabba",
        "city": "Brisbane",
        "country": "Australia",
        "surface": "pace",
        "batting_level": "medium",
        "pace_level": "high",
        "spin_level": "low",
        "straight_boundary_m": 76,
        "square_boundary_m": 66,
        "average_first_innings_score_t20": 163,
        "average_first_innings_score_odi": 258,
        "average_first_innings_score_test": 308,
        "highest_t20": 209,
        "highest_odi": 344,
        "highest_test": 645,
        "lowest_defended_t20": 138,
        "typical_winning_score_t20": 170,
    },
    "OPTUS": {
        "name": "Optus Stadium",
        "city": "Perth",
        "country": "Australia",
        "surface": "pace",
        "batting_level": "medium",
        "pace_level": "high",
        "spin_level": "low",
        "straight_boundary_m": 78,
        "square_boundary_m": 70,
        "average_first_innings_score_t20": 160,
        "average_first_innings_score_odi": 252,
        "average_first_innings_score_test": 318,
        "highest_t20": 218,
        "highest_odi": 338,
        "highest_test": 620,
        "lowest_defended_t20": 135,
        "typical_winning_score_t20": 167,
    },
    "HOBART": {
        "name": "Bellerive Oval",
        "city": "Hobart",
        "country": "Australia",
        "surface": "pace",
        "batting_level": "medium",
        "pace_level": "high",
        "spin_level": "low",
        "straight_boundary_m": 68,
        "square_boundary_m": 58,
        "average_first_innings_score_t20": 168,
        "average_first_innings_score_odi": 262,
        "average_first_innings_score_test": 300,
        "highest_t20": 223,
        "highest_odi": 346,
        "highest_test": 564,
        "lowest_defended_t20": 144,
        "typical_winning_score_t20": 175,
    },
    # ── Pakistan ───────────────────────────────────────────────────────────
    "NSTK": {
        "name": "National Stadium",
        "city": "Karachi",
        "country": "Pakistan",
        "surface": "spin",
        "batting_level": "medium",
        "pace_level": "low",
        "spin_level": "high",
        "straight_boundary_m": 70,
        "square_boundary_m": 62,
        "average_first_innings_score_t20": 158,
        "average_first_innings_score_odi": 250,
        "average_first_innings_score_test": 298,
        "highest_t20": 211,
        "highest_odi": 338,
        "highest_test": 665,
        "lowest_defended_t20": 132,
        "typical_winning_score_t20": 165,
    },
    "GSTL": {
        "name": "Gaddafi Stadium",
        "city": "Lahore",
        "country": "Pakistan",
        "surface": "balanced",
        "batting_level": "medium",
        "pace_level": "medium",
        "spin_level": "medium",
        "straight_boundary_m": 72,
        "square_boundary_m": 64,
        "average_first_innings_score_t20": 165,
        "average_first_innings_score_odi": 265,
        "average_first_innings_score_test": 312,
        "highest_t20": 219,
        "highest_odi": 356,
        "highest_test": 628,
        "lowest_defended_t20": 140,
        "typical_winning_score_t20": 172,
    },
    "RAWR": {
        "name": "Rawalpindi Cricket Stadium",
        "city": "Rawalpindi",
        "country": "Pakistan",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "low",
        "spin_level": "low",
        "straight_boundary_m": 74,
        "square_boundary_m": 66,
        "average_first_innings_score_t20": 168,
        "average_first_innings_score_odi": 275,
        "average_first_innings_score_test": 338,
        "highest_t20": 228,
        "highest_odi": 374,
        "highest_test": 579,
        "lowest_defended_t20": 145,
        "typical_winning_score_t20": 176,
    },
    "MULT": {
        "name": "Multan Cricket Stadium",
        "city": "Multan",
        "country": "Pakistan",
        "surface": "spin",
        "batting_level": "low",
        "pace_level": "low",
        "spin_level": "high",
        "straight_boundary_m": 70,
        "square_boundary_m": 63,
        "average_first_innings_score_t20": 152,
        "average_first_innings_score_odi": 240,
        "average_first_innings_score_test": 272,
        "highest_t20": 198,
        "highest_odi": 328,
        "highest_test": 510,
        "lowest_defended_t20": 126,
        "typical_winning_score_t20": 159,
    },
    # ── West Indies ────────────────────────────────────────────────────────
    "QPO": {
        "name": "Queen's Park Oval",
        "city": "Port of Spain",
        "country": "Trinidad",
        "surface": "balanced",
        "batting_level": "medium",
        "pace_level": "medium",
        "spin_level": "medium",
        "straight_boundary_m": 72,
        "square_boundary_m": 64,
        "average_first_innings_score_t20": 160,
        "average_first_innings_score_odi": 252,
        "average_first_innings_score_test": 290,
        "highest_t20": 205,
        "highest_odi": 328,
        "highest_test": 681,
        "lowest_defended_t20": 135,
        "typical_winning_score_t20": 167,
    },
    "SABP": {
        "name": "Sabina Park",
        "city": "Kingston",
        "country": "Jamaica",
        "surface": "pace",
        "batting_level": "medium",
        "pace_level": "high",
        "spin_level": "low",
        "straight_boundary_m": 72,
        "square_boundary_m": 64,
        "average_first_innings_score_t20": 158,
        "average_first_innings_score_odi": 252,
        "average_first_innings_score_test": 288,
        "highest_t20": 207,
        "highest_odi": 333,
        "highest_test": 849,
        "lowest_defended_t20": 132,
        "typical_winning_score_t20": 164,
    },
    "SVRS": {
        "name": "Sir Vivian Richards Stadium",
        "city": "Antigua",
        "country": "Antigua",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "low",
        "spin_level": "low",
        "straight_boundary_m": 75,
        "square_boundary_m": 65,
        "average_first_innings_score_t20": 168,
        "average_first_innings_score_odi": 268,
        "average_first_innings_score_test": 318,
        "highest_t20": 218,
        "highest_odi": 347,
        "highest_test": 593,
        "lowest_defended_t20": 143,
        "typical_winning_score_t20": 175,
    },
    "PROV": {
        "name": "Providence Stadium",
        "city": "Georgetown",
        "country": "Guyana",
        "surface": "slow",
        "batting_level": "medium",
        "pace_level": "low",
        "spin_level": "medium",
        "straight_boundary_m": 72,
        "square_boundary_m": 63,
        "average_first_innings_score_t20": 152,
        "average_first_innings_score_odi": 242,
        "average_first_innings_score_test": 275,
        "highest_t20": 196,
        "highest_odi": 316,
        "highest_test": 428,
        "lowest_defended_t20": 128,
        "typical_winning_score_t20": 159,
    },
    "GRND": {
        "name": "National Cricket Stadium",
        "city": "Grenada",
        "country": "Grenada",
        "surface": "balanced",
        "batting_level": "medium",
        "pace_level": "medium",
        "spin_level": "medium",
        "straight_boundary_m": 70,
        "square_boundary_m": 62,
        "average_first_innings_score_t20": 155,
        "average_first_innings_score_odi": 240,
        "average_first_innings_score_test": 278,
        "highest_t20": 200,
        "highest_odi": 310,
        "highest_test": 482,
        "lowest_defended_t20": 130,
        "typical_winning_score_t20": 162,
    },
    # ── New Zealand ────────────────────────────────────────────────────────
    "BASIN": {
        "name": "Basin Reserve",
        "city": "Wellington",
        "country": "New Zealand",
        "surface": "pace",
        "batting_level": "medium",
        "pace_level": "high",
        "spin_level": "low",
        "straight_boundary_m": 76,
        "square_boundary_m": 66,
        "average_first_innings_score_t20": 158,
        "average_first_innings_score_odi": 248,
        "average_first_innings_score_test": 272,
        "highest_t20": 200,
        "highest_odi": 318,
        "highest_test": 671,
        "lowest_defended_t20": 132,
        "typical_winning_score_t20": 164,
    },
    "SEDON": {
        "name": "Seddon Park",
        "city": "Hamilton",
        "country": "New Zealand",
        "surface": "batting",
        "batting_level": "high",
        "pace_level": "medium",
        "spin_level": "low",
        "straight_boundary_m": 74,
        "square_boundary_m": 65,
        "average_first_innings_score_t20": 170,
        "average_first_innings_score_odi": 268,
        "average_first_innings_score_test": 308,
        "highest_t20": 219,
        "highest_odi": 340,
        "highest_test": 715,
        "lowest_defended_t20": 146,
        "typical_winning_score_t20": 177,
    },
    "UNIO": {
        "name": "University Oval",
        "city": "Dunedin",
        "country": "New Zealand",
        "surface": "pace",
        "batting_level": "low",
        "pace_level": "high",
        "spin_level": "low",
        "straight_boundary_m": 72,
        "square_boundary_m": 62,
        "average_first_innings_score_t20": 152,
        "average_first_innings_score_odi": 238,
        "average_first_innings_score_test": 265,
        "highest_t20": 196,
        "highest_odi": 305,
        "highest_test": 560,
        "lowest_defended_t20": 125,
        "typical_winning_score_t20": 158,
    },
    # ── Sri Lanka ──────────────────────────────────────────────────────────
    "SSC": {
        "name": "Sinhalese Sports Club",
        "city": "Colombo",
        "country": "Sri Lanka",
        "surface": "spin",
        "batting_level": "medium",
        "pace_level": "low",
        "spin_level": "high",
        "straight_boundary_m": 72,
        "square_boundary_m": 64,
        "average_first_innings_score_t20": 155,
        "average_first_innings_score_odi": 240,
        "average_first_innings_score_test": 262,
        "highest_t20": 200,
        "highest_odi": 321,
        "highest_test": 952,
        "lowest_defended_t20": 128,
        "typical_winning_score_t20": 162,
    },
    "PLK": {
        "name": "Pallekele International Cricket Stadium",
        "city": "Kandy",
        "country": "Sri Lanka",
        "surface": "balanced",
        "batting_level": "medium",
        "pace_level": "medium",
        "spin_level": "medium",
        "straight_boundary_m": 74,
        "square_boundary_m": 66,
        "average_first_innings_score_t20": 158,
        "average_first_innings_score_odi": 252,
        "average_first_innings_score_test": 288,
        "highest_t20": 218,
        "highest_odi": 349,
        "highest_test": 506,
        "lowest_defended_t20": 132,
        "typical_winning_score_t20": 165,
    },
    # ── Bangladesh ─────────────────────────────────────────────────────────
    "ZAHUR": {
        "name": "Zahur Ahmed Chowdhury Stadium",
        "city": "Chittagong",
        "country": "Bangladesh",
        "surface": "slow",
        "batting_level": "low",
        "pace_level": "low",
        "spin_level": "high",
        "straight_boundary_m": 70,
        "square_boundary_m": 62,
        "average_first_innings_score_t20": 140,
        "average_first_innings_score_odi": 225,
        "average_first_innings_score_test": 252,
        "highest_t20": 196,
        "highest_odi": 320,
        "highest_test": 638,
        "lowest_defended_t20": 118,
        "typical_winning_score_t20": 148,
    },
    # ── Zimbabwe ───────────────────────────────────────────────────────────
    "HARE": {
        "name": "Harare Sports Club",
        "city": "Harare",
        "country": "Zimbabwe",
        "surface": "batting",
        "batting_level": "medium",
        "pace_level": "low",
        "spin_level": "medium",
        "straight_boundary_m": 68,
        "square_boundary_m": 60,
        "average_first_innings_score_t20": 158,
        "average_first_innings_score_odi": 248,
        "average_first_innings_score_test": 298,
        "highest_t20": 205,
        "highest_odi": 335,
        "highest_test": 547,
        "lowest_defended_t20": 132,
        "typical_winning_score_t20": 165,
    },
    # ── UAE ────────────────────────────────────────────────────────────────
    "ABU": {
        "name": "Sheikh Zayed Stadium",
        "city": "Abu Dhabi",
        "country": "United Arab Emirates",
        "surface": "slow",
        "batting_level": "medium",
        "pace_level": "low",
        "spin_level": "high",
        "straight_boundary_m": 76,
        "square_boundary_m": 68,
        "average_first_innings_score_t20": 148,
        "average_first_innings_score_odi": 232,
        "average_first_innings_score_test": 278,
        "highest_t20": 198,
        "highest_odi": 282,
        "highest_test": 547,
        "lowest_defended_t20": 124,
        "typical_winning_score_t20": 156,
    },
}


def _load_players(raw_players: list[dict[str, Any]]) -> list[Player]:
    return [Player(**player) for player in raw_players]


def _load_team(raw_team: dict[str, Any]) -> TeamSnapshot:
    data = dict(raw_team)
    data["players"] = _load_players(data.get("players", []))
    return TeamSnapshot(**data)


def load_match_context(path: Path) -> MatchContext:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return MatchContext(
        format=raw["format"],
        batting_first_team=_load_team(raw["batting_first_team"]),
        chasing_team=_load_team(raw["chasing_team"]),
        first_innings_score=raw["first_innings_score"],
        wickets_lost=raw["wickets_lost"],
        overs_faced=raw["overs_faced"],
        pitch_report=PitchReport(**raw["pitch_report"]),
    )


def _to_float(form: dict[str, list[str]], key: str, default: float = 0.0) -> float:
    value = form.get(key, [str(default)])[0].strip()
    try:
        return float(value)
    except ValueError:
        return default


def _to_int(form: dict[str, list[str]], key: str, default: int = 0) -> int:
    value = form.get(key, [str(default)])[0].strip()
    try:
        return int(float(value))
    except ValueError:
        return default


def _to_bool(form: dict[str, list[str]], key: str) -> bool:
    return form.get(key, ["off"])[0].lower() in {"on", "true", "1", "yes"}


def _choice(form: dict[str, list[str]], key: str, default: str) -> str:
    return form.get(key, [default])[0].strip().lower() or default


def _pitch_template(surface: str) -> tuple[float, float, float, float]:
    presets = {
        "balanced": (165.0, 0.15, 0.2, 0.15),
        "batting": (182.0, 0.45, 0.05, 0.05),
        "pace": (155.0, -0.05, 0.45, 0.05),
        "spin": (150.0, -0.1, 0.05, 0.45),
        "slow": (148.0, -0.12, 0.1, 0.3),
    }
    return presets.get(surface, presets["balanced"])


def _venue_recent_average(venue: dict[str, Any], match_format: str) -> dict[str, Any] | None:
    """Recent average from Cricsheet (same definition the ML model was trained on)."""
    if match_format not in {"t20", "odi"} or not venue.get("name"):
        return None
    is_ipl_venue = venue.get("_kind") == "club" or any(preset is venue for preset in IPL_VENUES.values())
    team_type = "club" if is_ipl_venue and match_format == "t20" else "international"
    try:
        from cricket_predictor import ml_model

        return ml_model.venue_average(str(venue["name"]), str(venue.get("city", "")), match_format, team_type, key=venue.get("_key"))
    except Exception:
        return None


def _venue_average_score(venue: dict[str, Any], match_format: str) -> float:
    recent = _venue_recent_average(venue, match_format)
    if recent and recent.get("avg"):
        return float(recent["avg"])
    # Fallback: hand-entered preset values
    if match_format == "odi":
        return float(venue.get("average_first_innings_score_odi", 255.0))
    if match_format == "test":
        return float(venue.get("average_first_innings_score_test", 300.0))
    return float(venue.get("average_first_innings_score_t20", 165.0))


def _pitch_adjustment(level: str) -> float:
    return {
        "low": -0.15,
        "medium": 0.0,
        "high": 0.15,
    }.get(level, 0.0)


def _mode_key(value: str | None) -> str:
    return "international" if (value or "").strip().lower() == "international" else "ipl"


_TEAM_BANK_CACHE: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}


# ---- players you added to a squad (Update squad in the XI box): new players the match data doesn't have yet
def _squad_adds_path() -> Path:
    hist = os.environ.get("CRICKET_HISTORY_PATH")
    if hist:  # a test copy keeps its own
        return Path(hist).with_name(Path(hist).stem + "_squad_additions.json")
    return Path(__file__).resolve().parent / "data" / "squad_additions.json"


def _squad_additions() -> dict[str, dict[str, list[str]]]:
    try:
        return json.loads(_squad_adds_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_squad_additions(data: dict[str, dict[str, list[str]]]) -> None:
    path = _squad_adds_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(path)
    _TEAM_BANK_CACHE.clear()


def _team_bank(mode: str) -> dict[str, dict[str, Any]]:
    """Team presets with squads refreshed from the match data (recent players first).

    Falls back to the hand-entered squads if the data files aren't available.
    """
    mode = _mode_key(mode)
    presets = INTERNATIONAL_TEAMS if mode == "international" else IPL_2026_TEAMS
    try:
        from cricket_predictor import ml_model, squads

        loaded = ml_model.load_store()
    except Exception:
        return presets
    if not loaded:
        return presets
    cache_key = (mode, id(loaded["store"]))
    if cache_key in _TEAM_BANK_CACHE:
        return _TEAM_BANK_CACHE[cache_key]
    merged: dict[str, dict[str, Any]] = {}
    for code, preset in presets.items():
        try:
            built = squads.build(preset, is_club=(mode == "ipl"))
        except Exception:
            built = None
        merged[code] = {**preset, "squad": built["squad"], "_latest_xi": built["latest_xi"], "_window": built["window"]} if built else preset
    added = _squad_additions().get(mode, {})  # players you added (Update squad): kept on top of the data's squad
    for code, names in added.items():
        if code in merged:
            have = {p["name"] for p in merged[code]["squad"]}
            extra = [{"name": n, "role": "batter", "recent": True, "games": 0, "last": None, "added": True} for n in names if n not in have]
            merged[code] = {**merged[code], "squad": extra + list(merged[code]["squad"])}
    for stale in [k for k in _TEAM_BANK_CACHE if k[0] == mode]:
        del _TEAM_BANK_CACHE[stale]
    _TEAM_BANK_CACHE[cache_key] = merged
    return merged


def _default_team_codes(mode: str) -> tuple[str, str]:
    return ("IND", "AUS") if _mode_key(mode) == "international" else ("MI", "RCB")


_VENUE_BANK_CACHE: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}


def _venue_bank(mode: str) -> dict[str, dict[str, Any]]:
    """Hand-entered venues (with pitch details) plus every other ground found in the match data.

    International mode lists every ground that has hosted a men's T20I or ODI; IPL mode every IPL ground.
    """
    mode = _mode_key(mode)
    presets = INTERNATIONAL_VENUES if mode == "international" else IPL_VENUES
    kind = "international" if mode == "international" else "club"
    try:
        from cricket_predictor import ml_model

        catalog = ml_model.venue_catalog(kind)
    except Exception:
        return presets
    if not catalog:
        return presets
    cache_key = (mode, id(catalog))
    if cache_key in _VENUE_BANK_CACHE:
        return _VENUE_BANK_CACHE[cache_key]

    from cricket_predictor.venue_countries import country_for

    merged: dict[str, dict[str, Any]] = {}
    covered: set[str] = set()
    for code, venue in presets.items():
        keys = [k for k in ml_model.preset_venue_key(venue["name"], venue.get("city", "")) if k in catalog]
        # one naming scheme for countries (e.g. Barbados -> West Indies) so the country filter groups correctly
        country = country_for(venue["name"], venue.get("city", ""))
        venue = {**venue, "country": country if country != "Other" else venue.get("country", "Other")}
        if keys:
            stats = catalog[keys[0]]
            venue = {**venue, "_key": keys[0], "_kind": kind, "_matches": stats["t20"] + stats["odi"], "_last": stats["last"]}
            covered.update(keys)
        merged[code] = venue
    for key, entry in catalog.items():
        if key in covered:
            continue
        code = "D-" + "".join(ch if ch.isalnum() else "-" for ch in key)[:48]
        merged[code] = {
            "name": entry["name"].split(",")[0] if entry.get("city") and entry["name"].endswith(entry["city"]) else entry["name"],
            "city": entry.get("city") or "",
            "country": country_for(entry["name"], entry.get("city") or "", entry.get("teams")),
            "surface": "balanced",
            "batting_level": "medium",
            "pace_level": "medium",
            "spin_level": "medium",
            "straight_boundary_m": "N/A",
            "square_boundary_m": "N/A",
            "highest_t20": entry.get("highest_t20") or 0,
            "highest_odi": entry.get("highest_odi") or 0,
            "_key": key,
            "_kind": kind,
            "_matches": entry["t20"] + entry["odi"],
            "_last": entry["last"],
            "_from_data": True,
        }
    for stale in [k for k in _VENUE_BANK_CACHE if k[0] == mode]:  # drop the list built from older data
        del _VENUE_BANK_CACHE[stale]
    _VENUE_BANK_CACHE[cache_key] = merged
    return merged


def _default_venue_code(mode: str) -> str:
    return "LORDS" if _mode_key(mode) == "international" else "MUM"


def _venue_preset(mode: str, code: str | None) -> dict[str, Any]:
    bank = _venue_bank(mode)
    default_code = _default_venue_code(mode)
    return bank.get(code or default_code, bank[default_code])


def _team_preset(mode: str, code: str, fallback_name: str) -> dict[str, Any]:
    preset = _team_bank(mode).get(code, {})
    squad = preset.get("squad", [])
    batting_rating = preset.get("batting_rating")
    bowling_rating = preset.get("bowling_rating")
    return {
        "name": preset.get("name", fallback_name),
        "batting_rating": batting_rating if batting_rating is not None else 70.0,
        "bowling_rating": bowling_rating if bowling_rating is not None else 70.0,
        "fielding_rating": preset.get("fielding_rating", 70.0),
        "recent_form": preset.get("recent_form", 0.5),
        "squad": squad,
        "source_url": preset.get("source_url", ""),
    }


STAR_PLAYER_BOOSTS: dict[str, dict[str, float]] = {
    "Virat Kohli": {"batting_average": 46.0, "strike_rate": 148.0, "recent_form": 0.82},
    "Phil Salt": {"batting_average": 34.0, "strike_rate": 159.0, "recent_form": 0.76},
    "Rohit Sharma": {"batting_average": 39.0, "strike_rate": 146.0, "recent_form": 0.74},
    "Surya Kumar Yadav": {"batting_average": 38.0, "strike_rate": 171.0, "recent_form": 0.82},
    "Hardik Pandya": {"batting_average": 30.0, "strike_rate": 150.0, "bowling_average": 27.0, "economy_rate": 8.1, "recent_form": 0.74},
    "Jasprit Bumrah": {"bowling_average": 18.5, "economy_rate": 6.6, "recent_form": 0.86},
    "Shubman Gill": {"batting_average": 44.0, "strike_rate": 151.0, "recent_form": 0.8},
    "Jos Buttler": {"batting_average": 39.0, "strike_rate": 154.0, "recent_form": 0.77},
    "Rashid Khan": {"bowling_average": 20.0, "economy_rate": 6.8, "recent_form": 0.82},
    "KL Rahul": {"batting_average": 41.0, "strike_rate": 145.0, "recent_form": 0.73},
    "Mitchell Starc": {"bowling_average": 22.0, "economy_rate": 7.6, "recent_form": 0.76},
    "Kuldeep Yadav": {"bowling_average": 22.0, "economy_rate": 7.1, "recent_form": 0.78},
    "Ruturaj Gaikwad": {"batting_average": 42.0, "strike_rate": 148.0, "recent_form": 0.76},
    "Noor Ahmad": {"bowling_average": 21.0, "economy_rate": 7.0, "recent_form": 0.77},
    "Matheesha Pathirana": {"bowling_average": 20.0, "economy_rate": 7.3, "recent_form": 0.78},
    "Ajinkya Rahane": {"batting_average": 34.0, "strike_rate": 142.0, "recent_form": 0.66},
    "Andre Russell": {"batting_average": 29.0, "strike_rate": 176.0, "bowling_average": 25.0, "economy_rate": 8.2, "recent_form": 0.75},
    "Sunil Narine": {"batting_average": 24.0, "strike_rate": 171.0, "bowling_average": 24.0, "economy_rate": 6.9, "recent_form": 0.77},
    "Rishabh Pant": {"batting_average": 34.0, "strike_rate": 150.0, "recent_form": 0.71},
    "Nicholas Pooran": {"batting_average": 33.0, "strike_rate": 170.0, "recent_form": 0.81},
    "Mitchell Marsh": {"batting_average": 32.0, "strike_rate": 152.0, "bowling_average": 30.0, "economy_rate": 8.4, "recent_form": 0.7},
    "Shreyas Iyer": {"batting_average": 37.0, "strike_rate": 149.0, "recent_form": 0.74},
    "Marcus Stoinis": {"batting_average": 29.0, "strike_rate": 154.0, "bowling_average": 29.0, "economy_rate": 8.3, "recent_form": 0.7},
    "Arshdeep Singh": {"bowling_average": 23.0, "economy_rate": 7.8, "recent_form": 0.76},
    "Riyan Parag": {"batting_average": 36.0, "strike_rate": 154.0, "recent_form": 0.73},
    "Yashasvi Jaiswal": {"batting_average": 39.0, "strike_rate": 156.0, "recent_form": 0.76},
    "Jofra Archer": {"bowling_average": 23.0, "economy_rate": 7.5, "recent_form": 0.72},
    "Rajat Patidar": {"batting_average": 35.0, "strike_rate": 154.0, "recent_form": 0.72},
    "Josh Hazlewood": {"bowling_average": 21.0, "economy_rate": 7.1, "recent_form": 0.79},
    "Ishan Kishan": {"batting_average": 33.0, "strike_rate": 149.0, "recent_form": 0.69},
    "Heinrich Klaasen": {"batting_average": 37.0, "strike_rate": 174.0, "recent_form": 0.8},
    "Travis Head": {"batting_average": 36.0, "strike_rate": 172.0, "recent_form": 0.79},
    "Pat Cummins": {"bowling_average": 25.0, "economy_rate": 8.1, "recent_form": 0.73},
    # New Zealand
    "Kane Williamson": {"batting_average": 42.0, "strike_rate": 134.0, "recent_form": 0.77},
    "Devon Conway": {"batting_average": 38.0, "strike_rate": 142.0, "recent_form": 0.74},
    "Rachin Ravindra": {"batting_average": 35.0, "strike_rate": 138.0, "bowling_average": 32.0, "economy_rate": 7.8, "recent_form": 0.72},
    "Trent Boult": {"bowling_average": 23.0, "economy_rate": 7.9, "recent_form": 0.74},
    "Lockie Ferguson": {"bowling_average": 25.0, "economy_rate": 8.3, "recent_form": 0.70},
    # South Africa
    "Kagiso Rabada": {"bowling_average": 20.0, "economy_rate": 7.4, "recent_form": 0.80},
    "Temba Bavuma": {"batting_average": 35.0, "strike_rate": 137.0, "recent_form": 0.70},
    "Keshav Maharaj": {"bowling_average": 26.0, "economy_rate": 5.5, "recent_form": 0.72},
    "Quinton de Kock": {"batting_average": 38.0, "strike_rate": 155.0, "recent_form": 0.76},
    "Lungi Ngidi": {"bowling_average": 27.0, "economy_rate": 8.0, "recent_form": 0.68},
    "Tabraiz Shamsi": {"bowling_average": 24.0, "economy_rate": 7.0, "recent_form": 0.72},
    # Sri Lanka
    "Wanindu Hasaranga": {"bowling_average": 22.0, "economy_rate": 7.1, "batting_average": 22.0, "strike_rate": 138.0, "recent_form": 0.76},
    "Maheesh Theekshana": {"bowling_average": 23.0, "economy_rate": 6.8, "recent_form": 0.74},
    "Pathum Nissanka": {"batting_average": 37.0, "strike_rate": 143.0, "recent_form": 0.73},
    "Kusal Mendis": {"batting_average": 34.0, "strike_rate": 152.0, "recent_form": 0.71},
    # West Indies
    "Alzarri Joseph": {"bowling_average": 24.0, "economy_rate": 7.8, "recent_form": 0.72},
    "Romario Shepherd": {"batting_average": 24.0, "strike_rate": 155.0, "bowling_average": 28.0, "economy_rate": 8.0, "recent_form": 0.68},
    "Jason Holder": {"batting_average": 23.0, "strike_rate": 130.0, "bowling_average": 26.0, "economy_rate": 7.4, "recent_form": 0.67},
    # Bangladesh
    "Shakib Al Hasan": {"batting_average": 27.0, "strike_rate": 141.0, "bowling_average": 26.0, "economy_rate": 7.3, "recent_form": 0.68},
    "Taskin Ahmed": {"bowling_average": 28.0, "economy_rate": 7.8, "recent_form": 0.67},
    "Mustafizur Rahman": {"bowling_average": 27.0, "economy_rate": 7.6, "recent_form": 0.68},
    # Afghanistan
    "Rahmanullah Gurbaz": {"batting_average": 32.0, "strike_rate": 157.0, "recent_form": 0.73},
    "Fazalhaq Farooqi": {"bowling_average": 23.0, "economy_rate": 7.1, "recent_form": 0.74},
    "Mujeeb Ur Rahman": {"bowling_average": 22.0, "economy_rate": 6.8, "recent_form": 0.74},
    "Sanju Samson": {"batting_average": 35.0, "strike_rate": 152.0, "recent_form": 0.73},
    # India — additional
    "Suryakumar Yadav": {"batting_average": 38.0, "strike_rate": 171.0, "recent_form": 0.82},
    "Tilak Varma": {"batting_average": 36.0, "strike_rate": 152.0, "recent_form": 0.74},
    "Abhishek Sharma": {"batting_average": 31.0, "strike_rate": 163.0, "recent_form": 0.71},
    "Nitish Kumar Reddy": {"batting_average": 28.0, "strike_rate": 148.0, "bowling_average": 34.0, "economy_rate": 9.0, "recent_form": 0.68},
    "Dhruv Jurel": {"batting_average": 30.0, "strike_rate": 140.0, "recent_form": 0.67},
    "Shivam Dube": {"batting_average": 28.0, "strike_rate": 162.0, "bowling_average": 38.0, "economy_rate": 9.5, "recent_form": 0.68},
    "Washington Sundar": {"batting_average": 22.0, "strike_rate": 138.0, "bowling_average": 28.0, "economy_rate": 7.4, "recent_form": 0.68},
    "Venkatesh Iyer": {"batting_average": 26.0, "strike_rate": 154.0, "bowling_average": 34.0, "economy_rate": 9.2, "recent_form": 0.65},
    "Shardul Thakur": {"batting_average": 22.0, "strike_rate": 148.0, "bowling_average": 30.0, "economy_rate": 9.1, "recent_form": 0.64},
    "Krunal Pandya": {"batting_average": 22.0, "strike_rate": 142.0, "bowling_average": 28.0, "economy_rate": 7.8, "recent_form": 0.64},
    "Ravindra Jadeja": {"batting_average": 25.0, "strike_rate": 138.0, "bowling_average": 24.0, "economy_rate": 6.8, "recent_form": 0.74},
    "Axar Patel": {"batting_average": 22.0, "strike_rate": 144.0, "bowling_average": 24.0, "economy_rate": 7.0, "recent_form": 0.72},
    "Varun Chakaravarthy": {"bowling_average": 21.0, "economy_rate": 7.2, "recent_form": 0.77},
    "Ravi Bishnoi": {"bowling_average": 23.0, "economy_rate": 7.4, "recent_form": 0.72},
    "Yuzvendra Chahal": {"bowling_average": 22.0, "economy_rate": 7.6, "recent_form": 0.71},
    "Ravichandran Ashwin": {"bowling_average": 22.0, "economy_rate": 6.5, "recent_form": 0.72},
    "Mohammed Shami": {"bowling_average": 22.0, "economy_rate": 7.6, "recent_form": 0.80},
    "Mohammed Siraj": {"bowling_average": 25.0, "economy_rate": 8.0, "recent_form": 0.73},
    "Deepak Chahar": {"bowling_average": 28.0, "economy_rate": 7.8, "recent_form": 0.68},
    "Prasidh Krishna": {"bowling_average": 27.0, "economy_rate": 8.1, "recent_form": 0.67},
    "Avesh Khan": {"bowling_average": 28.0, "economy_rate": 8.6, "recent_form": 0.65},
    "Harshit Rana": {"bowling_average": 26.0, "economy_rate": 8.3, "recent_form": 0.68},
    "Akash Deep": {"bowling_average": 26.0, "economy_rate": 8.0, "recent_form": 0.67},
    "T Natarajan": {"bowling_average": 27.0, "economy_rate": 8.2, "recent_form": 0.66},
    # Australia — additional
    "David Warner": {"batting_average": 34.0, "strike_rate": 144.0, "recent_form": 0.68},
    "Usman Khawaja": {"batting_average": 40.0, "strike_rate": 130.0, "recent_form": 0.74},
    "Marnus Labuschagne": {"batting_average": 38.0, "strike_rate": 132.0, "recent_form": 0.72},
    "Steve Smith": {"batting_average": 42.0, "strike_rate": 131.0, "recent_form": 0.75},
    "Jake Fraser-McGurk": {"batting_average": 30.0, "strike_rate": 174.0, "recent_form": 0.72},
    "Matt Short": {"batting_average": 29.0, "strike_rate": 158.0, "recent_form": 0.68},
    "Josh Inglis": {"batting_average": 29.0, "strike_rate": 152.0, "recent_form": 0.68},
    "Glenn Maxwell": {"batting_average": 30.0, "strike_rate": 163.0, "bowling_average": 30.0, "economy_rate": 7.8, "recent_form": 0.72},
    "Cameron Green": {"batting_average": 27.0, "strike_rate": 142.0, "bowling_average": 32.0, "economy_rate": 8.4, "recent_form": 0.67},
    "Tim David": {"batting_average": 31.0, "strike_rate": 166.0, "recent_form": 0.72},
    "Aaron Hardie": {"batting_average": 24.0, "strike_rate": 140.0, "bowling_average": 32.0, "economy_rate": 8.5, "recent_form": 0.66},
    "Ashton Agar": {"batting_average": 19.0, "strike_rate": 138.0, "bowling_average": 27.0, "economy_rate": 7.3, "recent_form": 0.65},
    "Adam Zampa": {"bowling_average": 24.0, "economy_rate": 7.8, "recent_form": 0.74},
    "Nathan Ellis": {"bowling_average": 26.0, "economy_rate": 8.4, "recent_form": 0.66},
    "Spencer Johnson": {"bowling_average": 24.0, "economy_rate": 8.6, "recent_form": 0.68},
    # England — additional
    "Joe Root": {"batting_average": 48.0, "strike_rate": 133.0, "recent_form": 0.80},
    "Ben Stokes": {"batting_average": 32.0, "strike_rate": 140.0, "bowling_average": 29.0, "economy_rate": 7.2, "recent_form": 0.78},
    "Harry Brook": {"batting_average": 41.0, "strike_rate": 152.0, "recent_form": 0.80},
    "Zak Crawley": {"batting_average": 35.0, "strike_rate": 148.0, "recent_form": 0.71},
    "Ben Duckett": {"batting_average": 36.0, "strike_rate": 152.0, "recent_form": 0.73},
    "Dawid Malan": {"batting_average": 34.0, "strike_rate": 138.0, "recent_form": 0.67},
    "Will Jacks": {"batting_average": 28.0, "strike_rate": 152.0, "bowling_average": 32.0, "economy_rate": 8.0, "recent_form": 0.68},
    "Jacob Bethell": {"batting_average": 28.0, "strike_rate": 148.0, "bowling_average": 32.0, "economy_rate": 8.2, "recent_form": 0.69},
    "Liam Livingstone": {"batting_average": 28.0, "strike_rate": 162.0, "bowling_average": 32.0, "economy_rate": 8.4, "recent_form": 0.70},
    "Sam Curran": {"batting_average": 22.0, "strike_rate": 145.0, "bowling_average": 27.0, "economy_rate": 8.2, "recent_form": 0.72},
    "Chris Woakes": {"batting_average": 22.0, "strike_rate": 130.0, "bowling_average": 26.0, "economy_rate": 7.4, "recent_form": 0.72},
    "Moeen Ali": {"batting_average": 22.0, "strike_rate": 148.0, "bowling_average": 27.0, "economy_rate": 7.6, "recent_form": 0.67},
    "Adil Rashid": {"bowling_average": 23.0, "economy_rate": 7.3, "recent_form": 0.74},
    "Mark Wood": {"bowling_average": 25.0, "economy_rate": 8.5, "recent_form": 0.72},
    "Gus Atkinson": {"bowling_average": 26.0, "economy_rate": 8.0, "recent_form": 0.70},
    "Brydon Carse": {"bowling_average": 25.0, "economy_rate": 8.2, "recent_form": 0.68},
    "Reece Topley": {"bowling_average": 27.0, "economy_rate": 8.4, "recent_form": 0.66},
    "Saqib Mahmood": {"bowling_average": 27.0, "economy_rate": 8.6, "recent_form": 0.65},
    # Pakistan — additional
    "Babar Azam": {"batting_average": 43.0, "strike_rate": 137.0, "recent_form": 0.76},
    "Mohammad Rizwan": {"batting_average": 37.0, "strike_rate": 136.0, "recent_form": 0.76},
    "Shaheen Afridi": {"bowling_average": 22.0, "economy_rate": 7.8, "recent_form": 0.78},
    "Haris Rauf": {"bowling_average": 24.0, "economy_rate": 8.6, "recent_form": 0.73},
    "Naseem Shah": {"bowling_average": 26.0, "economy_rate": 8.2, "recent_form": 0.70},
    "Shadab Khan": {"batting_average": 20.0, "strike_rate": 141.0, "bowling_average": 24.0, "economy_rate": 7.8, "recent_form": 0.72},
    "Fakhar Zaman": {"batting_average": 36.0, "strike_rate": 148.0, "recent_form": 0.70},
    "Saim Ayub": {"batting_average": 32.0, "strike_rate": 152.0, "recent_form": 0.71},
    "Imad Wasim": {"batting_average": 18.0, "strike_rate": 136.0, "bowling_average": 26.0, "economy_rate": 7.2, "recent_form": 0.68},
    "Abrar Ahmed": {"bowling_average": 23.0, "economy_rate": 7.4, "recent_form": 0.70},
    # New Zealand — additional
    "Tim Southee": {"bowling_average": 26.0, "economy_rate": 8.4, "recent_form": 0.70},
    "Matt Henry": {"bowling_average": 25.0, "economy_rate": 7.9, "recent_form": 0.71},
    "Kyle Jamieson": {"bowling_average": 24.0, "economy_rate": 7.7, "recent_form": 0.70},
    "Glenn Phillips": {"batting_average": 30.0, "strike_rate": 152.0, "bowling_average": 34.0, "economy_rate": 8.0, "recent_form": 0.72},
    "Daryl Mitchell": {"batting_average": 34.0, "strike_rate": 145.0, "bowling_average": 36.0, "economy_rate": 8.8, "recent_form": 0.72},
    "Michael Bracewell": {"batting_average": 22.0, "strike_rate": 138.0, "bowling_average": 30.0, "economy_rate": 7.8, "recent_form": 0.67},
    "Mitchell Santner": {"batting_average": 18.0, "strike_rate": 130.0, "bowling_average": 26.0, "economy_rate": 6.8, "recent_form": 0.70},
    "Ish Sodhi": {"bowling_average": 26.0, "economy_rate": 8.0, "recent_form": 0.68},
    "William O'Rourke": {"bowling_average": 25.0, "economy_rate": 8.1, "recent_form": 0.69},
    # South Africa — additional
    "Marco Jansen": {"batting_average": 22.0, "strike_rate": 138.0, "bowling_average": 25.0, "economy_rate": 8.0, "recent_form": 0.74},
    "Anrich Nortje": {"bowling_average": 22.0, "economy_rate": 8.1, "recent_form": 0.74},
    "David Miller": {"batting_average": 33.0, "strike_rate": 157.0, "recent_form": 0.76},
    "Aiden Markram": {"batting_average": 36.0, "strike_rate": 145.0, "bowling_average": 36.0, "economy_rate": 8.4, "recent_form": 0.73},
    "Rassie van der Dussen": {"batting_average": 35.0, "strike_rate": 140.0, "recent_form": 0.72},
    "Ryan Rickelton": {"batting_average": 30.0, "strike_rate": 148.0, "recent_form": 0.70},
    "Gerald Coetzee": {"bowling_average": 26.0, "economy_rate": 8.6, "recent_form": 0.70},
    # Sri Lanka — additional
    "Kamindu Mendis": {"batting_average": 34.0, "strike_rate": 138.0, "bowling_average": 32.0, "economy_rate": 7.6, "recent_form": 0.73},
    "Charith Asalanka": {"batting_average": 32.0, "strike_rate": 148.0, "recent_form": 0.71},
    "Dhananjaya de Silva": {"batting_average": 28.0, "strike_rate": 138.0, "bowling_average": 34.0, "economy_rate": 7.8, "recent_form": 0.68},
    "Lahiru Kumara": {"bowling_average": 26.0, "economy_rate": 8.4, "recent_form": 0.66},
    "Nuwan Thushara": {"bowling_average": 26.0, "economy_rate": 8.6, "recent_form": 0.65},
    "Dilshan Madushanka": {"bowling_average": 24.0, "economy_rate": 8.2, "recent_form": 0.68},
    "Dunith Wellalage": {"batting_average": 18.0, "strike_rate": 130.0, "bowling_average": 26.0, "economy_rate": 7.4, "recent_form": 0.66},
    # West Indies — additional
    "Rovman Powell": {"batting_average": 28.0, "strike_rate": 158.0, "recent_form": 0.70},
    "Shai Hope": {"batting_average": 36.0, "strike_rate": 128.0, "recent_form": 0.70},
    "Brandon King": {"batting_average": 30.0, "strike_rate": 145.0, "recent_form": 0.68},
    "Shimron Hetmyer": {"batting_average": 30.0, "strike_rate": 164.0, "recent_form": 0.70},
    "Kyle Mayers": {"batting_average": 28.0, "strike_rate": 146.0, "bowling_average": 34.0, "economy_rate": 8.4, "recent_form": 0.68},
    "Shamar Joseph": {"bowling_average": 25.0, "economy_rate": 8.0, "recent_form": 0.70},
    "Jayden Seales": {"bowling_average": 26.0, "economy_rate": 8.2, "recent_form": 0.67},
    "Gudakesh Motie": {"bowling_average": 26.0, "economy_rate": 7.8, "recent_form": 0.67},
    "Akeal Hosein": {"bowling_average": 26.0, "economy_rate": 7.6, "recent_form": 0.67},
    # Bangladesh — additional
    "Litton Das": {"batting_average": 31.0, "strike_rate": 146.0, "recent_form": 0.68},
    "Najmul Hossain Shanto": {"batting_average": 34.0, "strike_rate": 140.0, "recent_form": 0.68},
    "Mehidy Hasan Miraz": {"batting_average": 22.0, "strike_rate": 128.0, "bowling_average": 27.0, "economy_rate": 7.2, "recent_form": 0.68},
    "Mushfiqur Rahim": {"batting_average": 33.0, "strike_rate": 134.0, "recent_form": 0.66},
    # Afghanistan — additional
    "Naveen-ul-Haq": {"bowling_average": 26.0, "economy_rate": 8.4, "recent_form": 0.70},
    "Mohammad Nabi": {"batting_average": 24.0, "strike_rate": 144.0, "bowling_average": 26.0, "economy_rate": 7.4, "recent_form": 0.68},
    "Azmatullah Omarzai": {"batting_average": 26.0, "strike_rate": 148.0, "bowling_average": 28.0, "economy_rate": 8.0, "recent_form": 0.70},
    "Ibrahim Zadran": {"batting_average": 32.0, "strike_rate": 132.0, "recent_form": 0.68},
    # Zimbabwe
    "Sikandar Raza": {"batting_average": 28.0, "strike_rate": 148.0, "bowling_average": 26.0, "economy_rate": 7.6, "recent_form": 0.70},
    "Blessing Muzarabani": {"bowling_average": 26.0, "economy_rate": 8.4, "recent_form": 0.68},
    "Craig Ervine": {"batting_average": 30.0, "strike_rate": 136.0, "recent_form": 0.62},
    "Sean Williams": {"batting_average": 26.0, "strike_rate": 138.0, "bowling_average": 28.0, "economy_rate": 7.6, "recent_form": 0.60},
    "Ryan Burl": {"batting_average": 22.0, "strike_rate": 142.0, "bowling_average": 28.0, "economy_rate": 7.8, "recent_form": 0.60},
    # Ireland
    "Paul Stirling": {"batting_average": 32.0, "strike_rate": 148.0, "bowling_average": 32.0, "economy_rate": 8.0, "recent_form": 0.64},
    "Josh Little": {"bowling_average": 24.0, "economy_rate": 8.2, "recent_form": 0.66},
    "Andrew Balbirnie": {"batting_average": 28.0, "strike_rate": 134.0, "recent_form": 0.60},
    "Harry Tector": {"batting_average": 26.0, "strike_rate": 132.0, "recent_form": 0.58},
    "Lorcan Tucker": {"batting_average": 28.0, "strike_rate": 142.0, "recent_form": 0.60},
    "Curtis Campher": {"batting_average": 22.0, "strike_rate": 136.0, "bowling_average": 30.0, "economy_rate": 8.0, "recent_form": 0.60},
}


def _player_from_roster_entry(entry: dict[str, str]) -> Player:
    role = entry["role"]
    profile: dict[str, float]
    if role == "batter":
        profile = {"batting_average": 31.0, "strike_rate": 139.0, "recent_form": 0.62, "fitness": 0.96}
    elif role == "wicket_keeper":
        profile = {"batting_average": 30.0, "strike_rate": 142.0, "recent_form": 0.62, "fitness": 0.96}
    elif role == "all_rounder":
        profile = {
            "batting_average": 25.0,
            "strike_rate": 136.0,
            "bowling_average": 28.0,
            "economy_rate": 7.8,
            "recent_form": 0.63,
            "fitness": 0.95,
        }
    else:
        profile = {"bowling_average": 24.5, "economy_rate": 7.4, "recent_form": 0.64, "fitness": 0.96}

    profile.update(STAR_PLAYER_BOOSTS.get(entry["name"], {}))
    return Player(name=entry["name"], role=role, **profile)


def _selected_players(form: dict[str, list[str]], field_name: str, preset: dict[str, Any]) -> list[Player]:
    selected_names = form.get(field_name, [])
    squad = preset["squad"]
    selected_entries = [entry for entry in squad if entry["name"] in selected_names]
    if not selected_entries:
        selected_entries = squad[:11]
    else:
        selected_entries = selected_entries[:11]
    return [_player_from_roster_entry(entry) for entry in selected_entries]


def _team_strength_from_players(players: list[Player], default_batting: float = 70.0, default_bowling: float = 70.0) -> tuple[float, float, float]:
    batting_values: list[float] = []
    bowling_values: list[float] = []
    recent_form_values: list[float] = []

    for player in players:
        recent_form_values.append(player.recent_form)
        if player.role in {"batter", "wicket_keeper", "all_rounder"}:
            batting_values.append(player.batting_average * 0.7 + player.strike_rate * 0.18)
        if player.role in {"bowler", "all_rounder"}:
            bowling_average = player.bowling_average if player.bowling_average > 0 else 32.0
            economy = player.economy_rate if player.economy_rate > 0 else 8.2
            bowling_values.append((45.0 - bowling_average) * 1.8 + (9.2 - economy) * 10.0 + 42.0)

    batting_rating = min(88.0, max(62.0, sum(batting_values) / len(batting_values))) if batting_values else default_batting
    bowling_rating = min(88.0, max(62.0, sum(bowling_values) / len(bowling_values))) if bowling_values else default_bowling
    recent_form = sum(recent_form_values) / len(recent_form_values) if recent_form_values else 0.6
    return round(batting_rating, 1), round(bowling_rating, 1), round(recent_form, 2)


def _fielding_strength_from_players(players: list[Player], default_fielding: float = 72.0) -> float:
    if not players:
        return default_fielding
    fielding_values: list[float] = []
    for player in players:
        role_bonus = 2.4 if player.role == "wicket_keeper" else 3.0 if player.role == "all_rounder" else 1.4 if player.role == "batter" else 0.8
        fielding_values.append(55.0 + player.fitness * 18.0 + player.recent_form * 12.0 + role_bonus)
    return round(min(88.0, max(62.0, sum(fielding_values) / len(fielding_values))), 1)



def parse_form_body(body: bytes) -> MatchContext:
    form = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    mode = _mode_key(form.get("mode", ["ipl"])[0])
    match_format = form.get("format", ["t20"])[0]
    venue = _venue_preset(mode, form.get("venue_code", [_default_venue_code(mode)])[0])
    default_batting_code, default_chasing_code = _default_team_codes(mode)
    batting_team_code = form.get("batting_first_team_code", [default_batting_code])[0]
    chasing_team_code = form.get("chasing_team_code", [default_chasing_code])[0]
    if batting_team_code == chasing_team_code:
        chasing_team_code = next(
            (code for code in _team_bank(mode) if code != batting_team_code),
            default_chasing_code,
        )
    batting_preset = _team_preset(mode, batting_team_code, "Batting First XI")
    chasing_preset = _team_preset(mode, chasing_team_code, "Chasing XI")
    surface = _choice(form, "pitch_surface", venue.get("surface", "balanced"))
    base_average, base_batting, base_pace, base_spin = _pitch_template(surface)
    pace_level = _choice(form, "pace_level", str(venue.get("pace_level", "medium")))
    spin_level = _choice(form, "spin_level", str(venue.get("spin_level", "medium")))
    batting_level = _choice(form, "batting_level", str(venue.get("batting_level", "medium")))

    venue_average = _venue_average_score(venue, match_format)
    average_first_innings_score = _to_float(form, "average_first_innings_score", venue_average or base_average)
    batting_friendliness = _to_float(
        form,
        "batting_friendliness",
        base_batting + _pitch_adjustment(batting_level),
    )
    pace_assist = _to_float(form, "pace_assist", base_pace + _pitch_adjustment(pace_level))
    spin_assist = _to_float(form, "spin_assist", base_spin + _pitch_adjustment(spin_level))
    batting_players = _selected_players(form, "batting_first_playing", batting_preset)
    chasing_players = _selected_players(form, "chasing_playing", chasing_preset)
    batting_rating, bowling_rating, batting_recent_form = _team_strength_from_players(batting_players)
    chasing_batting_rating, chasing_bowling_rating, chasing_recent_form = _team_strength_from_players(chasing_players)
    batting_fielding_rating = _fielding_strength_from_players(batting_players, batting_preset["fielding_rating"])
    chasing_fielding_rating = _fielding_strength_from_players(chasing_players, chasing_preset["fielding_rating"])

    batting_first_team = TeamSnapshot(
        name=batting_preset["name"],
        players=batting_players,
        batting_rating=batting_rating,
        bowling_rating=bowling_rating,
        fielding_rating=batting_fielding_rating,
        recent_form=batting_recent_form,
    )
    chasing_team = TeamSnapshot(
        name=chasing_preset["name"],
        players=chasing_players,
        batting_rating=chasing_batting_rating,
        bowling_rating=chasing_bowling_rating,
        fielding_rating=chasing_fielding_rating,
        recent_form=chasing_recent_form,
    )
    return MatchContext(
        format=match_format,
        batting_first_team=batting_first_team,
        chasing_team=chasing_team,
        first_innings_score=_to_int(form, "first_innings_score", {"t20": 160, "odi": 265, "test": 280}.get(match_format, 160)),
        wickets_lost=_to_int(form, "wickets_lost", 6),
        overs_faced=_to_float(form, "overs_faced", {"t20": 20.0, "odi": 50.0, "test": 90.0}.get(match_format, 20.0)),
        pitch_report=PitchReport(
            average_first_innings_score=average_first_innings_score,
            batting_friendliness=batting_friendliness,
            pace_assist=pace_assist,
            spin_assist=spin_assist,
            dew_expected=_to_bool(form, "dew_expected"),
        ),
    )


def _read_history() -> list[dict[str, Any]]:
    if PUBLIC:
        return [dict(x) for x in getattr(_REQ, "history", []) if isinstance(x, dict)]
    if not HISTORY_PATH.exists():
        return []

    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    return data if isinstance(data, list) else []


def _write_history(entries: list[dict[str, Any]]) -> None:
    if PUBLIC:  # handed back to the visitor's browser with the response, never written to disk
        _REQ.history = entries[:HISTORY_LIMIT]
        _REQ.changed = True
        return
    _backup_history(entries)
    tmp = HISTORY_PATH.with_name(HISTORY_PATH.name + ".tmp")  # written whole, then swapped in: never a half-written file
    tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    tmp.replace(HISTORY_PATH)


# Backups of the saved predictions: one copy a day, plus a copy just before a "Clear all" or a restore.
# A test copy (CRICKET_HISTORY_PATH set) keeps its backups beside its own test file, never with the real ones.
HISTORY_BACKUP_DIR = Path(os.environ.get("CRICKET_HISTORY_BACKUPS") or (
    HISTORY_PATH.with_name(HISTORY_PATH.stem + "_backups") if os.environ.get("CRICKET_HISTORY_PATH") else Path("data") / "history_backups"))
HISTORY_BACKUP_KEEP = 40


def _backup_history(new_entries: list[dict[str, Any]] | None = None, reason: str = "") -> str | None:
    """Copy the predictions file as it is now (before it's overwritten). Returns the backup's name, if one was made."""
    try:
        if PUBLIC or not HISTORY_PATH.exists():
            return None
        current = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        if not isinstance(current, list) or not current:
            return None  # nothing worth keeping
        from datetime import datetime as _dt

        now = _dt.now()
        HISTORY_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        lost = new_entries is not None and len(new_entries) <= len(current) - 3  # "Clear all" or several gone at once
        name = None
        if reason or lost:
            name = f"history_{now:%Y-%m-%d_%H%M%S}_{reason or 'before_clear'}.json"
        elif not any(HISTORY_BACKUP_DIR.glob(f"history_{now:%Y-%m-%d}*.json")):
            name = f"history_{now:%Y-%m-%d}_daily.json"
        if not name:
            return None
        (HISTORY_BACKUP_DIR / name).write_text(json.dumps(current, indent=2), encoding="utf-8")
        old = sorted(HISTORY_BACKUP_DIR.glob("history_*.json"))[:-HISTORY_BACKUP_KEEP]
        for f in old:
            f.unlink()
        return name
    except (OSError, ValueError):
        return None  # a backup must never stop a prediction being saved



def _format_megabytes(value: int | float) -> str:
    return f"{value / (1024 * 1024):.1f} MB"


def _format_eta(seconds: float | int | None) -> str:
    if seconds is None:
        return "Calculating ETA"
    seconds = max(0, int(seconds))
    minutes, remaining_seconds = divmod(seconds, 60)
    if minutes:
        return f"About {minutes}m {remaining_seconds:02d}s left"
    return f"About {remaining_seconds}s left"





def _save_prediction(context: MatchContext, result: Any) -> list[dict[str, Any]]:
    history = _read_history()
    history.insert(
        0,
        {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "format": context.format.upper(),
            "batting_first_team": context.batting_first_team.name,
            "chasing_team": context.chasing_team.name,
            "first_innings_score": context.first_innings_score,
            "predicted_winner": result.predicted_winner,
            "batting_first_win_probability": result.batting_first_win_probability,
            "chasing_win_probability": result.chasing_win_probability,
            "confidence": result.confidence,
            "model": getattr(result, "model_used", "formula"),
        },
    )
    trimmed_history = history[:HISTORY_LIMIT]
    _write_history(trimmed_history)
    return trimmed_history


def _iter_watched_files() -> list[Path]:
    files: list[Path] = []
    for path in WATCHED_PATHS:
        if path.is_file():
            files.append(path)
            continue
        if path.is_dir():
            files.extend(sorted(candidate for candidate in path.rglob("*.py") if candidate.is_file()))
    return files


def _snapshot_mtimes() -> dict[str, float]:
    snapshot: dict[str, float] = {}
    for file_path in _iter_watched_files():
        try:
            snapshot[str(file_path)] = file_path.stat().st_mtime
        except FileNotFoundError:
            continue
    return snapshot


def run_dev_server() -> None:
    print("Starting Cricket Win Predictor in auto-reload mode...")
    child: subprocess.Popen[str] | None = None
    previous_snapshot = _snapshot_mtimes()

    try:
        while True:
            if child is None or child.poll() is not None:
                child = subprocess.Popen([sys.executable, __file__, "serve", "--noreload"])
                print("Auto-reload server started.")

            time.sleep(1)
            current_snapshot = _snapshot_mtimes()
            if current_snapshot != previous_snapshot:
                print("Change detected. Reloading server...")
                previous_snapshot = current_snapshot
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)
                child = None
    except KeyboardInterrupt:
        print("Stopping auto-reload server...")
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()










class PredictorHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        webapp.set_view(params.get("source", [""])[0])  # History's Yours / Model checks / Both switch
        app = sys.modules[__name__]
        if PUBLIC:
            if parsed.path.startswith("/api/") and not _rate_ok(self._client_ip()):
                self._send_json({"error": "Too many requests: wait a minute and try again."}, 429)
                return
            if parsed.path.startswith("/static/img/") and not PUBLIC_IMAGES:  # photos / team logos stay on your PC
                self.send_error(404)
                return
            allowed = parsed.path == "/" or parsed.path.startswith(("/api/", "/static/")) or parsed.path in ("/sw.js", "/manifest.webmanifest")
            if not allowed:
                self._send_redirect("/")
                return
            if parsed.path == "/api/photos" and not PUBLIC_IMAGES:
                self._send_json({})
                return
        # ---- the app: one page (web/index.html) that talks to the /api/ routes ----
        if parsed.path == "/":
            page = webapp.index_html()
            if PUBLIC:
                page = page.replace(b'<html lang="en"', b'<html lang="en" class="public"', 1)
            self._send_bytes(page, "text/html; charset=utf-8")
            return
        if parsed.path in ("/sw.js", "/manifest.webmanifest"):  # app install: these must sit at the site root
            found = webapp.static_file("/static" + parsed.path)
            if found is None:
                self.send_error(404)
                return
            self._send_bytes(*found)
            return
        if parsed.path.startswith("/static/"):
            found = webapp.static_file(parsed.path)
            if found is None:
                self.send_error(404)
                return
            self._send_bytes(*found)
            return
        if parsed.path.startswith("/api/"):
            try:
                if parsed.path == "/api/config":
                    self._send_json(webapp.config(app, params.get("mode", ["ipl"])[0]))
                elif parsed.path == "/api/settings":
                    self._send_json(webapp.get_settings())
                elif parsed.path == "/api/photos":
                    self._send_json(webapp.photos())
                elif parsed.path == "/api/scorecard":
                    self._send_json(webapp.scorecard(app))
                elif parsed.path == "/api/phase-par":
                    self._send_json(webapp.phase_par())
                elif parsed.path == "/api/replay/search":  # match time machine: find a past match
                    from cricket_predictor import replay as _replay
                    q, comp, srt = params.get("q", [""])[0], params.get("competition", [""])[0], params.get("sort", [""])[0]
                    found = _replay.search(q, comp, sort=srt)
                    if not PUBLIC and found.get("ready") and not srt:  # newer results from CricketData (result only)
                        found["recent"] = webapp.replay_recent(app, found.get("newest"), q, comp)
                    self._send_json(found)
                elif parsed.path == "/api/last5" and not PUBLIC:  # model on the last 5 matches of a kind (no calls)
                    self._send_json(webapp.last5(app, params.get("kind", ["odi"])[0]))
                elif parsed.path == "/api/live-check" and not PUBLIC:  # model check at the innings break (no calls)
                    self._send_json(webapp.live_check(app, params.get("id", [""])[0]))
                elif parsed.path == "/api/replay":  # ... and replay it over by over
                    from cricket_predictor import replay as _replay
                    self._send_json(_replay.replay(params.get("id", [""])[0]))
                elif parsed.path == "/api/top-teams":
                    self._send_json(webapp.top_teams(app, params.get("mode", ["ipl"])[0]))
                elif parsed.path == "/api/history":
                    self._send_json(webapp.history(app))
                elif parsed.path == "/api/history/backups":
                    self._send_json(webapp.history_backups(app))
                elif parsed.path == "/api/ping":  # an open page saying "still here" (see _start_auto_exit)
                    _note_ping(params.get("tab", [""])[0], params.get("bye", [""])[0] == "1")
                    self._send_json({"ok": True})
                elif parsed.path == "/api/busy":  # an update or retrain is running (don't shut down mid-way)
                    self._send_json({"busy": _busy()})
                elif parsed.path == "/api/health":
                    self._send_json(webapp.health())
                elif parsed.path == "/api/honesty":  # how honest the percentages are (Accuracy page)
                    self._send_json(webapp.honesty(app))
                elif parsed.path == "/api/accuracy":
                    self._send_json(webapp.accuracy())
                elif parsed.path == "/api/innings-break-trial" and not PUBLIC:
                    from cricket_predictor import innings_trial

                    self._send_json(innings_trial.report(innings_trial.database_path()))
                elif parsed.path == "/api/status":
                    self._send_json({**webapp.status(UPDATE_SERVICE.snapshot()), "public": PUBLIC})
                else:
                    self.send_error(404)
            except Exception as exc:  # report API errors as JSON instead of dropping the connection
                self._send_error_json(exc, parsed.path)
            return
        # any other address (the old server-made pages, /classic, /result ..., were removed on 26 Nov 2026): the app
        self._send_redirect("/")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        _REQ.history, _REQ.changed = [], False
        # a size limit before anything is read: one huge request could otherwise fill the (small) online server's memory
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self.close_connection = True
            self._send_json({"error": f"That request is too big (the limit is {MAX_BODY // 1_000_000} MB)."}, 413)
            return
        if PUBLIC:
            if not parsed.path.startswith("/api/") or parsed.path in PUBLIC_BLOCKED:
                self._send_json({"error": "That isn't available in the online version."}, 403)
                return
            if not _rate_ok(self._client_ip()):
                self._send_json({"error": "Too many requests: wait a minute and try again."}, 429)
                return
        if parsed.path == "/api/ping":  # a closing tab's goodbye, sent with navigator.sendBeacon (always a POST)
            q = parse_qs(parsed.query)
            _note_ping(q.get("tab", [""])[0], q.get("bye", [""])[0] == "1")
            self._send_json({"ok": True})
            return
        if parsed.path.startswith("/api/"):
            app = sys.modules[__name__]
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(length) if length else b""
                payload = json.loads(raw.decode("utf-8")) if raw else {}
                problem = _input_problem(payload)
                if problem:
                    self._send_json({"error": problem}, status=400)
                    return
                webapp.set_view(payload.get("source") if isinstance(payload, dict) else None)
                if PUBLIC:
                    sent = payload.pop("client_history", None) if isinstance(payload, dict) else None
                    _REQ.history = [x for x in sent if isinstance(x, dict)][:HISTORY_LIMIT] if isinstance(sent, list) else []
                    if parsed.path == "/api/drops" and int(payload.get("delta") or 0) != 0:
                        self._send_json({"error": "Logging dropped catches is only in the desktop version."}, 403)
                        return
                if parsed.path == "/api/history":  # public mode: the browser sends its saved predictions to be checked
                    self._send_json(webapp.history(app))
                elif parsed.path == "/api/predict":
                    self._send_json(webapp.predict(app, payload))
                elif parsed.path == "/api/chase":
                    self._send_json(webapp.chase(app, payload))
                elif parsed.path == "/api/chase/scenarios":
                    self._send_json(webapp.chase_scenarios(app, payload))
                elif parsed.path == "/api/insights":
                    self._send_json(webapp.player_insights(app, payload))
                elif parsed.path == "/api/suggest-xi":
                    self._send_json(webapp.suggest_xi(app, payload))
                elif parsed.path == "/api/settings":
                    self._send_json(webapp.save_settings(payload))
                elif parsed.path == "/api/compare":
                    self._send_json(webapp.compare_players(app, payload))
                elif parsed.path == "/api/drops":
                    self._send_json(webapp.log_drop(app, payload))
                elif parsed.path == "/api/fielding":
                    self._send_json(webapp.fielding(app, payload))
                elif parsed.path == "/api/phases":
                    self._send_json(webapp.phase_stats(app, payload))
                elif parsed.path == "/api/par-grid":
                    self._send_json(webapp.par_grid(app, payload))
                elif parsed.path == "/api/resources":
                    self._send_json(webapp.resources(app, payload))
                elif parsed.path == "/api/live-results" and not PUBLIC:
                    self._send_json(webapp.live_refresh(payload))
                elif parsed.path == "/api/last5" and not PUBLIC:  # ... and look for / check newer matches (uses calls)
                    self._send_json(webapp.last5(app, str(payload.get("kind") or "odi"), fetch=True))
                elif parsed.path == "/api/go-back/clear" and not PUBLIC:  # take fetched checks back out
                    self._send_json(webapp.clear_fetched(app, str(payload.get("kind") or "")))
                elif parsed.path == "/api/go-back" and not PUBLIC:  # fetch the next older matches into History
                    self._send_json(webapp.go_back(app, str(payload.get("kind") or "")))
                elif parsed.path == "/api/live-check" and not PUBLIC:  # get the match's data first (about 10 calls)
                    self._send_json(webapp.live_check(app, str(payload.get("id") or ""), fetch=True))
                elif parsed.path == "/api/pitch-read":  # pitch report text -> pitch and dew buttons, with the words used
                    from cricket_predictor import pitch_report
                    self._send_json(pitch_report.read(str(payload.get("text") or "")))
                elif parsed.path == "/api/pitch-read-image" and not PUBLIC:  # ... from a picture (Windows text recognition)
                    from cricket_predictor import pitch_report
                    try:
                        self._send_json(pitch_report.read_image(str(payload.get("image") or "")))
                    except ValueError as exc:
                        self._send_json({"error": str(exc)}, status=400)
                elif parsed.path == "/api/official-squad" and not PUBLIC:  # Update squad: the official IPL squad (Wikipedia)
                    try:
                        self._send_json(webapp.official_squad(app, payload))
                    except ValueError as exc:
                        self._send_json({"error": str(exc)}, status=400)
                elif parsed.path in ("/api/squad-update", "/api/latest-players") and not PUBLIC:  # Update squad (XI box)
                    try:
                        self._send_json(webapp.squad_update(app, payload) if parsed.path.endswith("update")
                                        else webapp.latest_players(app, payload, fetch=bool(payload.get("fetch"))))
                    except ValueError as exc:
                        self._send_json({"error": str(exc)}, status=400)
                elif parsed.path == "/api/link-check" and not PUBLIC:  # check a match from a link (Replay)
                    try:
                        self._send_json(webapp.link_check(app, payload))
                    except ValueError as exc:
                        self._send_json({"error": str(exc)}, status=400)
                elif parsed.path in ("/api/xi-read", "/api/xi-read-image"):  # playing XIs from a team sheet
                    picture = parsed.path.endswith("image")
                    if picture and PUBLIC:
                        self.send_error(404)
                    else:
                        try:
                            self._send_json(webapp.xi_read(app, payload, picture=picture))
                        except ValueError as exc:
                            self._send_json({"error": str(exc)}, status=400)
                elif parsed.path == "/api/toss":
                    self._send_json(webapp.toss_advice(app, payload))
                elif parsed.path == "/api/preview":
                    self._send_json(webapp.match_preview(app, payload))
                elif parsed.path == "/api/teams":
                    self._send_json(webapp.team_record(app, payload))
                elif parsed.path == "/api/venue":
                    self._send_json(webapp.venue_report(app, payload))
                elif parsed.path == "/api/h2h":
                    self._send_json(webapp.head_to_head(app, payload))
                elif parsed.path == "/api/history/practice":  # practice run / real match
                    self._send_json(webapp.set_practice(app, payload))
                elif parsed.path == "/api/history/result":
                    self._send_json(webapp.set_result(app, payload))
                elif parsed.path == "/api/history/clear":
                    self._send_json(webapp.clear_history(app))
                elif parsed.path == "/api/history/delete":
                    self._send_json(webapp.delete_entry(app, payload))
                elif parsed.path == "/api/history/restore":
                    self._send_json(webapp.restore_entries(app, payload))
                elif parsed.path == "/api/retrain":
                    self._send_json(webapp.RETRAINER.start(label=str(payload.get("label") or "Retrained from the app")[:60]))
                elif parsed.path == "/api/history/restore-backup":
                    self._send_json(webapp.restore_backup(app, payload))
                elif parsed.path == "/api/update-all":
                    self._send_json(webapp.RETRAINER.start(download=True, label=str(payload.get("label") or "Updated from the app")[:60]))
                elif parsed.path == "/api/auto-update":
                    self._send_json(webapp.set_auto_schedule(bool(payload.get("enable"))))
                elif parsed.path == "/api/update-data":
                    self._send_json(UPDATE_SERVICE.start_update())
                else:
                    self.send_error(404)
            except Exception as exc:
                self._send_error_json(exc, parsed.path)
            return

        # anything else posted outside /api/ (the old form): back to the app
        self._send_redirect("/")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_bytes(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _client_ip(self) -> str:
        fwd = self.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() if fwd else self.client_address[0]

    def _send_error_json(self, exc: Exception, path: str) -> None:
        """An API error as a plain message: what you sent couldn't be used (400), or the server failed (500). The
        technical details go to the log (and, on your PC, also to the message, to help track a fault down)."""
        if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return  # the browser left before the answer was sent (a quick page switch, a closed tab): not a fault
        if isinstance(exc, json.JSONDecodeError):
            self._send_json({"error": "That request couldn't be read (it isn't valid JSON)."}, status=400)
            return
        if isinstance(exc, (ValueError, TypeError)):
            text = str(exc)
            technical = isinstance(exc, TypeError) or re.search(r"invalid literal|could not convert|unsupported operand|object has no", text)
            self._send_json({"error": "Check what you entered: the score, wickets, overs and target must be numbers."
                             if technical else text}, status=400)
            return
        logging.getLogger(__name__).exception("API error on %s", path)
        message = "Something went wrong on the server. Try again in a moment."
        self._send_json({"error": message if PUBLIC else f"{message} ({type(exc).__name__}: {exc})"}, status=500)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        if PUBLIC and getattr(_REQ, "changed", False) and isinstance(payload, dict):
            payload = {**payload, "client_history": _REQ.history}
            _REQ.changed = False
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()


# ---- close by itself when the browser is closed: every open page says "still here" (/api/ping) every 20 s; once
# every tab has closed (see CLOSE_AFTER below), the app stops with exit code 0 and the launcher closes its window. It never stops during an update or a
# retrain, and stays on until a page has opened at least once (so starting it without a browser does nothing).
AUTO_EXIT_AFTER = int(os.environ.get("CREASE_AUTO_EXIT_SECONDS") or 180)
# Each open page pings with its own tab id every 20 s and says goodbye (bye=1) when it is closed or reloaded.
# Once the last open tab has said goodbye, the app closes CLOSE_AFTER seconds later (30 s; a reload pings again
# well before that). A tab that disappears without saying goodbye (browser crash, PC asleep) counts as gone after
# AUTO_EXIT_AFTER seconds, which stays long because Chrome slows timers in background tabs to about one a minute.
CLOSE_AFTER = int(os.environ.get("CREASE_CLOSE_AFTER_SECONDS") or 30)
_TABS: dict[str, float] = {}
_TAB_STATE: dict[str, float | None] = {"closed_at": None, "seen": None}
_TAB_LOCK = threading.Lock()


def _note_ping(tab: str = "", bye: bool = False) -> None:
    now = time.time()
    with _TAB_LOCK:
        _TAB_STATE["seen"] = now
        if bye:
            if _TABS.pop(tab, None) is None:  # a tab we never heard from: nothing changes
                return
            live = [t for t in _TABS.values() if now - t < AUTO_EXIT_AFTER]
            _TAB_STATE["closed_at"] = None if live else now
        else:
            _TABS[tab] = now
            _TAB_STATE["closed_at"] = None


def _should_close() -> bool:
    now = time.time()
    with _TAB_LOCK:
        if _TAB_STATE["seen"] is None:  # no page has opened yet
            return False
        if any(now - t < AUTO_EXIT_AFTER for t in _TABS.values()):
            return False
        closed = _TAB_STATE["closed_at"]
        return (closed is not None and now - closed >= CLOSE_AFTER) or now - _TAB_STATE["seen"] >= AUTO_EXIT_AFTER


def _busy() -> bool:
    try:
        if UPDATE_SERVICE.snapshot().get("state") == "running":
            return True
        return webapp.RETRAINER.snapshot().get("state") == "running"
    except Exception:  # noqa: BLE001
        return False


def _start_auto_exit() -> None:
    if PUBLIC or os.environ.get("CREASE_NO_AUTO_EXIT") or AUTO_EXIT_AFTER <= 0:
        return

    def watch() -> None:
        while True:
            time.sleep(5)
            if not _should_close() or _busy():
                continue
            print("The app's last browser tab was closed: closing.", flush=True)
            os._exit(0)

    threading.Thread(target=watch, daemon=True, name="auto-exit").start()


class QuietHTTPServer(ThreadingHTTPServer):
    """A browser that leaves while an answer is on its way (a quick page switch, a closed tab) isn't a server error:
    no traceback for it in the window (or the online logs). Any other error is still printed as before."""

    def handle_error(self, request, client_address):  # noqa: ANN001 - same signature as socketserver
        if isinstance(sys.exc_info()[1], (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    host = os.environ.get("CREASE_HOST", host)
    port = int(os.environ.get("PORT", port))
    _start_auto_exit()
    if not PUBLIC:  # the online copy gets new models by upload, not by downloading and retraining itself
        # a test copy (its own history file, or CREASE_NO_AUTO_UPDATE=1) never downloads or rebuilds the real data
        if os.environ.get("CREASE_NO_AUTO_UPDATE") != "1" and not os.environ.get("CRICKET_HISTORY_PATH"):
            UPDATE_SERVICE.start_auto_updates()
        try:  # a copy of your saved predictions, squads and settings in OneDrive (not for test copies)
            from cricket_predictor import backup
            backup.start_background()
        except Exception:  # noqa: BLE001 - a backup must never stop the app
            pass
        try:  # recent results from CricketData every few hours, if you've put a key in data/cricketdata_key.txt
            from cricket_predictor import live_results
            live_results.start_background()
            webapp.start_auto_check(sys.modules[__name__])  # daily: check missing matches against the model
        except Exception:  # noqa: BLE001 - optional extra
            pass
    try:
        from cricket_predictor import insights

        insights.warm_up()  # load model + matchup data in the background so the first click is instant
    except Exception:
        pass
    try:
        from cricket_predictor import tracking

        tracking.warm_totals()  # match totals for History (only reads the files after a data update)
    except Exception:
        pass

    def practice_run() -> None:
        """One hidden prediction of each kind right after start-up (nothing saved), so every model, data table and
        code path is loaded before your first click instead of during it."""
        import time as _time

        _time.sleep(0.2)
        try:
            from cricket_predictor import webapp

            codes = list(sys.modules[__name__]._team_bank("ipl").keys())[:2]
            if len(codes) == 2:
                base = {"mode": "ipl", "format": "t20", "batting": codes[0], "chasing": codes[1], "save": False, "_no_warm": True}
                webapp.predict(sys.modules[__name__], {**base, "runs": 95, "wickets": 3, "overs": 12})
                webapp.chase(sys.modules[__name__], {**base, "target": 180, "runs": 60, "wickets": 2, "overs": 8})
        except Exception:  # noqa: BLE001 - only a head start
            pass

    def count_cores() -> None:
        """LightGBM asks joblib how many CPU cores this PC has before its first prediction, and on Windows joblib
        finds out by starting PowerShell (about 2 s, once; the answer is kept). Asked here, it runs alongside the
        model loading instead of after it."""
        try:
            from joblib import cpu_count

            cpu_count(only_physical_cores=True)
        except Exception:  # noqa: BLE001 - only a head start
            pass

    threading.Thread(target=count_cores, daemon=True, name="core-count").start()
    threading.Thread(target=practice_run, daemon=True, name="practice-run").start()
    server = QuietHTTPServer((host, port), PredictorHandler)
    server.daemon_threads = True
    print(f"Serving Cricket Win Predictor at http://{host}:{port}", flush=True)
    server.serve_forever()


def main() -> None:
    args = sys.argv[1:]

    if args and args[0] == "dev":
        run_dev_server()
        return

    if args and args[0] == "serve":
        port = int(args[1]) if len(args) > 1 and args[1].isdigit() else 8000
        run_server(port=port)
        return

    sample_path = Path("sample_match.json")
    context = load_match_context(sample_path)
    prediction = predict_match_winner(context)
    print(json.dumps(asdict(prediction), indent=2))


if __name__ == "__main__":
    main()

