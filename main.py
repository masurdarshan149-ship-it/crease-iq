from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from dataclasses import asdict
from email.utils import parsedate_to_datetime
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

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
PLAYER_INSIGHTS_CACHE_PATH = Path("data/player_insights_cache.json")
CRICSHEET_ARCHIVE_PATH = Path("data/cricsheet_all_json_full.zip")
CRICSHEET_ALL_JSON_URL = "https://cricsheet.org/downloads/all_json.zip"
WATCHED_PATHS = [
    Path("main.py"),
    Path("sample_match.json"),
    Path("cricket_predictor"),
]
_LAST_RESULT: dict[str, Any] | None = None

_DATA_UPDATE_LOCK = threading.Lock()
_DATA_UPDATE_STATE: dict[str, Any] = {
    "state": "idle",
    "message": "",
    "stage": "idle",
    "progress": 0,
    "downloaded_bytes": 0,
    "total_bytes": 0,
    "eta_seconds": None,
    "processed_items": 0,
    "total_items": 0,
    "started_at": None,
    "stage_started_at": None,
}

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


def _display_form_score(value: float) -> int:
    return int(round(max(0.0, min(1.0, value)) * 100))


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


def _render_home(status_html: str = "") -> str:
    return HOME_HTML.replace("<!--HOME_STATUS-->", status_html or _current_home_status_html(), 1)


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


def _data_update_snapshot() -> dict[str, Any]:
    with _DATA_UPDATE_LOCK:
        return dict(_DATA_UPDATE_STATE)


def _set_data_update_state(**changes: Any) -> None:
    with _DATA_UPDATE_LOCK:
        stage_before = _DATA_UPDATE_STATE.get("stage")
        _DATA_UPDATE_STATE.update(changes)
        stage_after = _DATA_UPDATE_STATE.get("stage")
        if "started_at" not in _DATA_UPDATE_STATE or _DATA_UPDATE_STATE.get("started_at") is None:
            _DATA_UPDATE_STATE["started_at"] = time.time()
        if stage_after != stage_before:
            _DATA_UPDATE_STATE["stage_started_at"] = time.time()


def _progress_meta_text(snapshot: dict[str, Any]) -> str:
    stage = str(snapshot.get("stage", "idle")).lower()
    downloaded_bytes = int(snapshot.get("downloaded", 0) or 0)
    total_bytes = int(snapshot.get("total", 0) or 0)
    processed_items = int(snapshot.get("processedItems", 0) or 0)
    total_items = int(snapshot.get("totalItems", 0) or 0)
    eta_copy = str(snapshot.get("eta", "Calculating ETA") or "Calculating ETA")
    archive_known = total_bytes > 0
    if stage == "downloading" and total_bytes > 0:
        remaining = max(total_bytes - downloaded_bytes, 0)
        return (
            f"{_format_megabytes(downloaded_bytes)} / {_format_megabytes(total_bytes)} downloaded"
            f" • {_format_megabytes(remaining)} remaining • {eta_copy}"
        )
    if stage == "downloading" and not archive_known:
        return "Starting archive refresh from the network."
    if stage in {"processing", "finalizing"} and total_items > 0:
        return f"Processed {processed_items:,} of {total_items:,} archive files • {eta_copy}"
    if stage in {"processing", "finalizing"} and total_bytes > 0:
        return f"Archive ready at {_format_megabytes(total_bytes)} • rebuilding player insights cache • {eta_copy}"
    if stage == "completed" and total_bytes > 0:
        return f"Processed {_format_megabytes(total_bytes)} archive successfully"
    return _last_updated_label()


def _progress_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    state = str(snapshot.get("state", "idle"))
    stage = str(snapshot.get("stage", "idle"))
    percent = int(snapshot.get("percent", 0) or 0)
    if state == "success":
        stage = "Completed"
        percent = 100
    return {
        "percent": percent,
        "stage": stage,
        "downloadedSize": _format_megabytes(int(snapshot.get("downloaded", 0) or 0)),
        "totalSize": _format_megabytes(int(snapshot.get("total", 0) or 0)) if int(snapshot.get("total", 0) or 0) else "Pending",
        "eta": "Completed" if state == "success" else str(snapshot.get("eta", "Calculating ETA")),
        "message": "Update Completed \u2705" if state == "success" else str(snapshot.get("message", "")),
        "meta": _progress_meta_text(snapshot),
        "state": state,
        "processedItems": int(snapshot.get("processedItems", 0) or 0),
        "totalItems": int(snapshot.get("totalItems", 0) or 0),
    }


def _render_home_status(message: str, is_error: bool = False, is_running: bool = False, snapshot: dict[str, Any] | None = None) -> str:
    snapshot = snapshot or _data_update_snapshot()
    status_class = "update-status"
    if is_error:
        status_class += " is-error"
    elif is_running:
        status_class += " is-running"
    title = "Update in progress" if is_running else ("Update failed" if is_error else "Data updated")
    timestamp = _last_updated_label()
    progress_markup = ""
    action_markup = ""
    helper_copy = f'<span class="update-meta">{escape(timestamp)}</span>'
    if is_running:
        progress_value = max(1, min(100, int(snapshot.get("percent", 12) or 12)))
        stage_raw = str(snapshot.get("stage", "Downloading")).lower()
        stage = escape(stage_raw)
        meta_copy = escape(_progress_meta_text(snapshot))
        downloaded_bytes = int(snapshot.get("downloaded", 0) or 0)
        total_bytes = int(snapshot.get("total", 0) or 0)
        stage_label = {
            "downloading": "Downloading",
            "processing": "Building cache",
            "finalizing": "Finalizing",
            "completed": "Completed",
        }.get(stage_raw, "Preparing archive")
        eta_copy = str(snapshot.get("eta", "Calculating ETA") or "Calculating ETA")
        metric_markup = (
            '<div class="update-metrics">'
            f'<div class="update-metric"><span>Stage</span><strong>{escape(stage_label)}</strong></div>'
            f'<div class="update-metric"><span>Size</span><strong>{escape(_format_megabytes(downloaded_bytes))} / {escape(_format_megabytes(total_bytes)) if total_bytes else "Pending"}</strong></div>'
            f'<div class="update-metric"><span>ETA</span><strong>{escape(eta_copy)}</strong></div>'
            "</div>"
        )
        progress_markup = (
            '<div class="update-progress-shell" data-progress-shell>'
            f'<div class="update-progress-head"><span>Live progress</span><strong data-progress-value>{progress_value}%</strong></div>'
            '<div class="update-progress" aria-hidden="true">'
            f'<div class="update-progress-fill" data-progress-fill style="width: {progress_value}%;"></div>'
            "</div>"
            f"{metric_markup}"
            '<div class="update-progress-steps">'
            f'<span{" class=\"is-active\"" if stage_raw == "downloading" else ""} data-progress-step="download">Downloading archive</span>'
            f'<span{" class=\"is-active\"" if stage_raw in {"processing", "finalizing"} else ""} data-progress-step="cache">Building cache</span>'
            f'<span{" class=\"is-active\"" if stage_raw == "completed" else ""} data-progress-step="done">Finalizing</span>'
            "</div></div>"
        )
        helper_copy = (
            f'<span class="update-meta" data-progress-meta>{meta_copy}</span>'
            '<span class="update-meta">Status refreshes automatically while the update is running.</span>'
        )
    elif is_error:
        action_markup = '<div class="update-actions"><button class="status-secondary" type="submit" form="update-data-form">Retry Update</button></div>'
    return (
        f'<div class="{status_class}" data-update-state="{"running" if is_running else ("error" if is_error else "success")}"><strong>{escape(title)}</strong>'
        f'<span>{escape(message)}</span>'
        f"{progress_markup}"
        f"{action_markup}"
        f"{helper_copy}</div>"
    )


def _current_home_status_html() -> str:
    snapshot = UPDATE_SERVICE.snapshot()
    state = str(snapshot.get("state", "idle"))
    message = str(snapshot.get("message", ""))
    if not message:
        return ""
    if state == "running":
        return _render_home_status(message, is_running=True, snapshot=snapshot)
    return _render_home_status(message, is_error=state == "error", snapshot=snapshot)


def _last_updated_label() -> str:
    paths = [PLAYER_INSIGHTS_CACHE_PATH, CRICSHEET_ARCHIVE_PATH]
    existing = [path for path in paths if path.exists()]
    if not existing:
        return "Updated on: Not available yet"
    latest_path = max(existing, key=lambda path: path.stat().st_mtime)
    updated_at = datetime.fromtimestamp(latest_path.stat().st_mtime).strftime("%d %b %Y, %I:%M %p")
    return f"Updated on: {updated_at}"


def _fetch_remote_archive_metadata() -> tuple[int | None, float | None]:
    request = Request(
        CRICSHEET_ALL_JSON_URL,
        headers={"User-Agent": "Cricket-Win-Predictor/1.0"},
        method="HEAD",
    )
    try:
        with urlopen(request, timeout=20) as response:
            size_header = response.headers.get("Content-Length")
            modified_header = response.headers.get("Last-Modified")
    except Exception:
        return None, None

    remote_size = int(size_header) if size_header and size_header.isdigit() else None
    remote_mtime = None
    if modified_header:
        try:
            remote_mtime = parsedate_to_datetime(modified_header).timestamp()
        except Exception:
            remote_mtime = None
    return remote_size, remote_mtime


def _is_local_archive_current() -> bool:
    if not CRICSHEET_ARCHIVE_PATH.exists():
        return False
    remote_size, remote_mtime = _fetch_remote_archive_metadata()
    local_stat = CRICSHEET_ARCHIVE_PATH.stat()
    if remote_size is not None and local_stat.st_size != remote_size:
        return False
    if remote_mtime is not None and abs(local_stat.st_mtime - remote_mtime) > 60:
        return False
    return remote_size is not None or remote_mtime is not None


def _cache_is_fresh_for_archive() -> bool:
    if not PLAYER_INSIGHTS_CACHE_PATH.exists() or not CRICSHEET_ARCHIVE_PATH.exists():
        return False
    return PLAYER_INSIGHTS_CACHE_PATH.stat().st_mtime >= CRICSHEET_ARCHIVE_PATH.stat().st_mtime


def _download_latest_cricsheet_archive() -> tuple[bool, str]:
    CRICSHEET_ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _is_local_archive_current():
        archive_size = CRICSHEET_ARCHIVE_PATH.stat().st_size if CRICSHEET_ARCHIVE_PATH.exists() else 0
        _set_data_update_state(
            stage="building",
            progress=76,
            downloaded_bytes=archive_size,
            total_bytes=archive_size,
            eta_seconds=3,
            message=f"Latest Cricsheet archive already available locally at {_format_megabytes(archive_size)}.",
        )
        return True, "Latest Cricsheet archive already available locally."

    temporary_path = CRICSHEET_ARCHIVE_PATH.with_suffix(".zip.tmp")
    request = Request(
        CRICSHEET_ALL_JSON_URL,
        headers={"User-Agent": "Cricket-Win-Predictor/1.0"},
    )
    try:
        download_started_at = time.time()
        with urlopen(request, timeout=300) as response, temporary_path.open("wb") as handle:
            total_bytes = int(response.headers.get("Content-Length", "0") or 0)
            downloaded_bytes = 0
            _set_data_update_state(
                stage="downloading",
                progress=3,
                downloaded_bytes=0,
                total_bytes=total_bytes,
                eta_seconds=None,
                message="Downloading the latest Cricsheet archive.",
            )
            while True:
                chunk = response.read(4 * 1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded_bytes += len(chunk)
                if total_bytes > 0:
                    progress = max(3, min(72, int((downloaded_bytes / total_bytes) * 72)))
                    elapsed = max(time.time() - download_started_at, 0.001)
                    bytes_per_second = downloaded_bytes / elapsed
                    remaining_bytes = max(total_bytes - downloaded_bytes, 0)
                    eta_seconds = remaining_bytes / bytes_per_second if bytes_per_second > 0 else None
                else:
                    progress = 36
                    eta_seconds = None
                _set_data_update_state(
                    stage="downloading",
                    progress=progress,
                    downloaded_bytes=downloaded_bytes,
                    total_bytes=total_bytes,
                    eta_seconds=eta_seconds,
                    message="Downloading the latest Cricsheet archive.",
                )
        temporary_path.replace(CRICSHEET_ARCHIVE_PATH)
        archive_size = CRICSHEET_ARCHIVE_PATH.stat().st_size if CRICSHEET_ARCHIVE_PATH.exists() else downloaded_bytes
        _set_data_update_state(
            stage="building",
            progress=76,
            downloaded_bytes=archive_size,
            total_bytes=archive_size,
            eta_seconds=None,
            message="Archive download finished. Rebuilding the player insights cache.",
        )
        return True, "Latest Cricsheet archive downloaded."
    except Exception as exc:
        if temporary_path.exists():
            temporary_path.unlink(missing_ok=True)
        if CRICSHEET_ARCHIVE_PATH.exists():
            archive_size = CRICSHEET_ARCHIVE_PATH.stat().st_size
            _set_data_update_state(
                stage="building",
                progress=76,
                downloaded_bytes=archive_size,
                total_bytes=archive_size,
                eta_seconds=3,
                message=f"Could not fetch the newest Cricsheet archive, so the updater is using the local {_format_megabytes(archive_size)} archive.",
            )
            return True, f"Could not download the latest Cricsheet archive, using the local archive instead: {exc}"
        return False, f"Could not download the latest Cricsheet archive: {exc}"


def _update_player_data_cache() -> tuple[bool, str]:
    download_ok, download_message = _download_latest_cricsheet_archive()
    if not download_ok:
        return False, download_message
    if _cache_is_fresh_for_archive():
        archive_size = CRICSHEET_ARCHIVE_PATH.stat().st_size if CRICSHEET_ARCHIVE_PATH.exists() else 0
        _set_data_update_state(
            stage="done",
            progress=100,
            downloaded_bytes=archive_size,
            total_bytes=archive_size,
            message="Latest Cricsheet archive and player insights cache are already up to date.",
        )
        return True, "Latest Cricsheet archive and player insights cache are already up to date."

    archive_size = CRICSHEET_ARCHIVE_PATH.stat().st_size if CRICSHEET_ARCHIVE_PATH.exists() else 0
    _set_data_update_state(
        stage="building",
        progress=82,
        downloaded_bytes=archive_size,
        total_bytes=archive_size,
        processed_items=0,
        total_items=0,
        eta_seconds=None,
        message="Archive ready. Rebuilding the player insights cache.",
    )

    try:
        process = subprocess.Popen(
            [sys.executable, str(Path("scripts/build_cricsheet_cache.py"))],
            cwd=Path.cwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except Exception as exc:
        return False, f"Could not start the data update: {exc}"

    global _PLAYER_INSIGHTS_CACHE
    _PLAYER_INSIGHTS_CACHE = None
    stdout_lines: list[str] = []
    build_started_at = time.time()

    try:
        assert process.stdout is not None
        for line in process.stdout:
            entry = line.strip()
            if not entry:
                continue
            stdout_lines.append(entry)
            if entry.startswith("BUILD_PROGRESS "):
                parts = entry.split()
                if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                    processed_items = int(parts[1])
                    total_items = int(parts[2])
                    progress_share = (processed_items / total_items) if total_items else 0.0
                    progress_value = 82 + int(progress_share * 16)
                    elapsed = max(time.time() - build_started_at, 0.001)
                    items_per_second = processed_items / elapsed if processed_items else 0.0
                    remaining_items = max(total_items - processed_items, 0)
                    eta_seconds = remaining_items / items_per_second if items_per_second > 0 else None
                    _set_data_update_state(
                        stage="building",
                        progress=min(progress_value, 98),
                        downloaded_bytes=archive_size,
                        total_bytes=archive_size,
                        processed_items=processed_items,
                        total_items=total_items,
                        eta_seconds=eta_seconds,
                        message="Building the player insights cache from the archive.",
                    )
                continue
            _set_data_update_state(
                stage="building",
                progress=98,
                downloaded_bytes=archive_size,
                total_bytes=archive_size,
                eta_seconds=2,
                message=entry,
            )
        stderr_output = process.stderr.read() if process.stderr is not None else ""
        return_code = process.wait(timeout=3600)
    except subprocess.TimeoutExpired:
        process.kill()
        return False, "Could not finish the data update within the expected time."

    if return_code == 0:
        summary = next((line for line in reversed(stdout_lines) if not line.startswith("BUILD_PROGRESS ")), "")
        summary = summary or "Latest Cricsheet cache rebuilt successfully."
        _set_data_update_state(
            stage="done",
            progress=100,
            downloaded_bytes=archive_size,
            total_bytes=archive_size,
            processed_items=int(_data_update_snapshot().get("total_items", 0) or 0),
            total_items=int(_data_update_snapshot().get("total_items", 0) or 0),
            eta_seconds=0,
            message=f"{download_message} {summary}",
        )
        return True, f"{download_message} {summary}"

    details = stderr_output.strip() or "\n".join(stdout_lines).strip() or "Unknown error during cache rebuild."
    return False, f"{download_message} {details.splitlines()[-1]}"


def _run_player_data_update_background() -> None:
    success, message = _update_player_data_cache()
    snapshot = _data_update_snapshot()
    _set_data_update_state(
        state="success" if success else "error",
        message=message,
        progress=100 if success else int(snapshot.get("progress", 0) or 0),
        stage="completed" if success else str(snapshot.get("stage", "idle")),
        eta_seconds=0 if success else snapshot.get("eta_seconds"),
    )


def _start_player_data_update() -> tuple[bool, str]:
    snapshot = _data_update_snapshot()
    if snapshot.get("state") == "running":
        return False, str(snapshot.get("message", "An update is already in progress."))
    archive_exists = CRICSHEET_ARCHIVE_PATH.exists()
    archive_size = CRICSHEET_ARCHIVE_PATH.stat().st_size if archive_exists else 0
    _set_data_update_state(
        state="running",
        stage="building" if archive_exists else "downloading",
        progress=76 if archive_exists else 1,
        downloaded_bytes=archive_size if archive_exists else 0,
        total_bytes=archive_size if archive_exists else 0,
        processed_items=0,
        total_items=0,
        eta_seconds=None,
        started_at=time.time(),
        stage_started_at=time.time(),
        message=(f"Using the local {_format_megabytes(archive_size)} Cricsheet archive."
                 if archive_exists else "Starting the latest Cricsheet data update."),
    )
    worker = threading.Thread(target=_run_player_data_update_background, daemon=True)
    worker.start()
    return True, (f"Using the local {_format_megabytes(archive_size)} Cricsheet archive."
                  if archive_exists else "Starting the latest Cricsheet data update.")


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


HOME_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Cricket Win Predictor</title>
  <style>
    :root {
      --bg: #0c1220;
      --surface: #1a2537;
      --surface-2: #1f2e44;
      --surface-3: #243452;
      --border: #2a3d57;
      --border-bright: #3d5a7a;
      --text: #e2eaf5;
      --muted: #7b93af;
      --dim: #4a6080;
      --accent: #3b82f6;
      --accent-soft: rgba(59,130,246,0.14);
      --green: #22c55e;
      --amber: #f59e0b;
      --shadow: 0 4px 24px rgba(0,0,0,0.5);
      --shadow-sm: 0 2px 12px rgba(0,0,0,0.35);
      --radius: 16px;
      --radius-sm: 10px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
      color: var(--text);
      background: linear-gradient(160deg, #0a0f1e 0%, #0d1627 50%, #0c1525 100%);
      min-height: 100vh;
    }
    .home {
      position: relative;
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px 20px 60px;
    }
    .home-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }
    .toolbar-copy {
      flex: 1 1 300px;
    }
    .toolbar-copy strong {
      display: block;
      margin-bottom: 4px;
      font-size: 0.95rem;
      color: var(--text);
    }
    .toolbar-copy span {
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.6;
    }
    .update-form {
      margin: 0;
      flex: 0 0 auto;
    }
    .update-button {
      border: 1px solid var(--border-bright);
      background: var(--surface-2);
      color: var(--accent);
      border-radius: var(--radius-sm);
      padding: 10px 20px;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      font-family: inherit;
      transition: all 150ms ease;
    }
    .update-button:hover {
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }
    .update-button:disabled {
      cursor: progress;
      opacity: 0.6;
    }
    .update-status {
      margin-bottom: 20px;
      padding: 16px 18px;
      border-radius: var(--radius);
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--text);
      box-shadow: var(--shadow-sm);
    }
    .update-status strong {
      display: block;
      margin-bottom: 4px;
      font-size: 0.95rem;
      color: var(--text);
    }
    .update-status span {
      display: block;
      line-height: 1.6;
      color: var(--muted);
      font-size: 0.9rem;
    }
    .update-meta {
      margin-top: 4px;
      font-size: 0.82rem;
      color: var(--dim);
    }
    .update-status.is-running {
      border-color: var(--border-bright);
    }
    .update-status.is-error {
      border-color: rgba(239,68,68,0.4);
      background: rgba(239,68,68,0.08);
      color: #fca5a5;
    }
    .update-progress-shell {
      margin: 14px 0 8px;
      padding: 14px;
      border-radius: var(--radius-sm);
      background: rgba(0,0,0,0.3);
      border: 1px solid var(--border);
    }
    .update-progress-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
      color: var(--muted);
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .update-progress-head strong {
      margin: 0;
      font-size: 1.2rem;
      line-height: 1;
      color: var(--text);
      letter-spacing: -0.03em;
    }
    .update-progress {
      position: relative;
      margin: 0;
      height: 8px;
      border-radius: 999px;
      overflow: hidden;
      background: rgba(255,255,255,0.06);
    }
    .update-progress-fill {
      position: absolute;
      inset: 0 auto 0 0;
      width: 12%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--amber) 0%, var(--accent) 100%);
      transition: width 700ms ease;
    }
    .update-progress-fill::after {
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(120deg, transparent 0 30%, rgba(255,255,255,0.2) 30% 40%, transparent 40% 100%);
      background-size: 40px 100%;
      animation: update-progress-stripes 1.2s linear infinite;
    }
    .update-progress-steps {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin-top: 10px;
    }
    .update-metrics {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 8px;
      margin-top: 10px;
    }
    .update-metric {
      padding: 10px 12px;
      border-radius: var(--radius-sm);
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--border);
    }
    .update-metric span {
      display: block;
      margin-bottom: 3px;
      font-size: 0.72rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--dim);
    }
    .update-metric strong {
      margin: 0;
      font-size: 0.9rem;
      color: var(--text);
    }
    .update-progress-steps span {
      padding: 8px;
      border-radius: 8px;
      background: rgba(255,255,255,0.04);
      color: var(--dim);
      font-size: 0.78rem;
      font-weight: 700;
      text-align: center;
      transition: all 150ms ease;
    }
    .update-progress-steps span.is-active {
      background: var(--accent-soft);
      color: #93c5fd;
    }
    .update-actions {
      margin-top: 12px;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .status-secondary {
      background: rgba(255,255,255,0.06);
      border-color: var(--border);
      color: var(--text);
    }
    @keyframes update-progress-stripes {
      from { transform: translateX(0); }
      to { transform: translateX(40px); }
    }
    .home-hero {
      position: relative;
      overflow: hidden;
      padding: 40px;
      border-radius: 20px;
      background: linear-gradient(135deg, #131d34 0%, #0f1926 100%);
      border: 1px solid var(--border);
      box-shadow: var(--shadow);
      margin-bottom: 28px;
    }
    .home-hero::before {
      content: "";
      position: absolute;
      top: -80px;
      right: -80px;
      width: 320px;
      height: 320px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(59,130,246,0.12), transparent 70%);
      pointer-events: none;
    }
    .home-hero::after {
      content: "";
      position: absolute;
      bottom: -60px;
      left: 40%;
      width: 240px;
      height: 240px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(245,158,11,0.08), transparent 70%);
      pointer-events: none;
    }
    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 16px;
      padding: 6px 12px;
      border-radius: 999px;
      background: var(--accent-soft);
      border: 1px solid rgba(59,130,246,0.25);
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #93c5fd;
    }
    .home-hero h1 {
      margin: 0 0 12px;
      max-width: 700px;
      font-size: clamp(2.2rem, 4.5vw, 4rem);
      line-height: 1.04;
      letter-spacing: -0.04em;
      color: #fff;
    }
    .home-hero p {
      margin: 0;
      max-width: 680px;
      font-size: 1rem;
      line-height: 1.7;
      color: var(--muted);
    }
    .home-note {
      margin-top: 20px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .section-title {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 10px;
    }
    .section-title h2 {
      margin: 0;
      color: var(--text);
      font-size: 1.1rem;
      letter-spacing: -0.02em;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 999px;
      background: rgba(255,255,255,0.06);
      border: 1px solid var(--border);
      color: var(--muted);
      font-size: 0.72rem;
      letter-spacing: 0.04em;
    }
    .home-chip {
      display: inline-flex;
      align-items: center;
      padding: 6px 12px;
      border-radius: 999px;
      background: rgba(255,255,255,0.06);
      border: 1px solid var(--border);
      font-size: 0.84rem;
      color: var(--muted);
    }
    .home-grid {
      display: grid;
      gap: 20px;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    }
    .player-stats-board {
      margin-top: 24px;
      padding: 20px;
      border-radius: var(--radius);
      border: 1px solid var(--border);
      background: var(--surface);
      box-shadow: var(--shadow-sm);
    }
    .player-stats-grid {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      margin-top: 14px;
    }
    .player-stat-card {
      padding: 14px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: var(--surface-2);
    }
    .player-stat-card h4 {
      margin: 0 0 8px;
      color: var(--text);
      font-size: 0.9rem;
    }
    .player-stat-line {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      padding: 5px 0;
      color: var(--muted);
      font-size: 0.84rem;
      border-bottom: 1px solid rgba(255,255,255,0.04);
    }
    .player-stat-line:last-child { border-bottom: none; }
    .player-stat-line strong {
      color: var(--text);
    }
    .player-stats-empty {
      margin: 12px 0 0;
      color: var(--muted);
      font-size: 0.9rem;
    }
    .home-card {
      position: relative;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      gap: 16px;
      min-height: 320px;
      padding: 28px;
      border-radius: 20px;
      text-decoration: none;
      border: 1px solid transparent;
      box-shadow: var(--shadow);
      color: white;
      transition: transform 200ms ease, box-shadow 200ms ease;
    }
    .home-card::after {
      content: "";
      position: absolute;
      inset: 0;
      border-radius: inherit;
      background: linear-gradient(180deg, rgba(255,255,255,0.07) 0%, transparent 50%);
      pointer-events: none;
    }
    .home-card:hover {
      transform: translateY(-4px);
      box-shadow: 0 20px 50px rgba(0,0,0,0.6);
    }
    .home-card.ipl {
      background: linear-gradient(145deg, #6b1f9b 0%, #c4520a 55%, #d97706 100%);
    }
    .home-card.international {
      background: linear-gradient(145deg, #1e3a8a 0%, #1d4ed8 55%, #2563eb 100%);
    }
    .card-kicker {
      display: inline-flex;
      width: fit-content;
      padding: 6px 10px;
      border-radius: 8px;
      background: rgba(255,255,255,0.14);
      border: 1px solid rgba(255,255,255,0.18);
      font-size: 0.74rem;
      font-weight: 700;
      letter-spacing: 0.07em;
      text-transform: uppercase;
    }
    .home-card h2 {
      margin: 0;
      font-size: clamp(1.8rem, 2.5vw, 2.5rem);
      line-height: 1.05;
      letter-spacing: -0.04em;
    }
    .home-card p {
      margin: 0;
      max-width: 28ch;
      line-height: 1.65;
      color: rgba(255,255,255,0.85);
      font-size: 0.96rem;
    }
    .home-points {
      margin-top: auto;
      display: grid;
      gap: 8px;
    }
    .home-point {
      display: flex;
      align-items: center;
      gap: 10px;
      color: rgba(255,255,255,0.88);
      font-size: 0.9rem;
    }
    .home-point::before {
      content: "";
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: rgba(255,255,255,0.7);
      flex: 0 0 auto;
    }
    .home-arrow {
      margin-top: 10px;
      font-size: 0.9rem;
      font-weight: 700;
      letter-spacing: 0.02em;
      color: rgba(255,255,255,0.95);
    }
    @media (max-width: 700px) {
      .home { padding: 20px 14px 40px; }
      .home-hero { padding: 28px 20px; }
      .home-card { min-height: 280px; padding: 22px; }
      .update-form, .update-button { width: 100%; }
      .update-progress-steps { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main class="home">
    <div class="home-toolbar">
      <div class="toolbar-copy">
        <strong>Keep the local stats fresh</strong>
        <span>Refresh the Cricsheet download and rebuild the player insights cache right from the home page. A live progress bar appears while the update is running.</span>
      </div>
      <form class="update-form" id="update-data-form" method="post" action="/update-data">
        <button class="update-button" type="submit">Update Data</button>
      </form>
    </div>
    <!--HOME_STATUS-->
    <section class="home-hero">
      <div class="eyebrow">Choose your format</div>
      <h1>Choose Your Match Desk</h1>
      <p>Start from a dedicated match desk instead of a single mixed flow. Pick the tournament style you want, then move into a predictor page with its own theme, squad logic, and match experience.</p>
      <div class="home-note">
        <div class="home-chip">Separate themes</div>
        <div class="home-chip">Dedicated squad banks</div>
        <div class="home-chip">Cleaner user flow</div>
      </div>
    </section>
    <section class="home-grid">
      <a class="home-card ipl" href="/?mode=ipl">
        <span class="card-kicker">Franchise Match Desk</span>
        <h2>IPL Matches</h2>
        <p>Use the franchise predictor with the IPL squad bank, playing-XI controls, and a sharper league-style dashboard.</p>
        <div class="home-points">
          <div class="home-point">Updated squad selector</div>
          <div class="home-point">Playing XI control</div>
          <div class="home-point">League-style layout</div>
        </div>
        <div class="home-arrow">Open IPL desk -></div>
      </a>
      <a class="home-card international" href="/?mode=international">
        <span class="card-kicker">National Match Desk</span>
        <h2>International Matches</h2>
        <p>Open a separate international predictor page with a darker tournament mood and a cleaner national-team experience.</p>
        <div class="home-points">
          <div class="home-point">International team bank</div>
          <div class="home-point">Separate visual theme</div>
          <div class="home-point">Focused match experience</div>
        </div>
        <div class="home-arrow">Open international desk -></div>
      </a>
    </section>
    <section class="player-stats-board">
      <div class="section-title">
        <h2>Player Stats</h2>
        <span class="badge">Latest Cricsheet-backed summary</span>
      </div>
      <p class="player-stats-empty" data-player-stats-empty>Update the data to refresh the latest player stats.</p>
      <div class="player-stats-grid" data-player-stats-grid></div>
    </section>
  </main>
  <script>
    (() => {
      const form = document.querySelector(".update-form");
      const button = form?.querySelector(".update-button");
      const toolbar = document.querySelector(".home-toolbar");
      const playerStatsGrid = document.querySelector("[data-player-stats-grid]");
      const playerStatsEmpty = document.querySelector("[data-player-stats-empty]");
      if (!form || !button || !toolbar || !playerStatsGrid || !playerStatsEmpty) {
        return;
      }

      const POLL_INTERVAL_MS = 1000;
      const SMOOTH_INTERVAL_MS = 100;
      const STALE_AFTER_MS = 20000;
      const MAX_UPDATE_MS = 1200000;
      const FINALIZING_PERCENT = 90;
      const COMPLETE_AFTER_PERCENT = 95;

      const statusMarkup = `
        <div class="update-status is-running" data-update-state="running">
          <strong>Update in progress</strong>
          <span data-progress-message>Preparing archive</span>
          <div class="update-progress-shell" data-progress-shell>
            <div class="update-progress-head"><span>Live progress</span><strong data-progress-value>0%</strong></div>
            <div class="update-progress" aria-hidden="true">
              <div class="update-progress-fill" data-progress-fill style="width: 0%;"></div>
            </div>
            <div class="update-metrics">
              <div class="update-metric"><span>Stage</span><strong data-progress-stage>Preparing archive</strong></div>
              <div class="update-metric"><span>Size</span><strong data-progress-size>0.0 MB / Pending</strong></div>
              <div class="update-metric"><span>ETA</span><strong data-progress-eta>Starting...</strong></div>
            </div>
            <div class="update-progress-steps">
              <span class="is-active" data-progress-step="download">Preparing archive</span>
              <span data-progress-step="cache">Building cache</span>
              <span data-progress-step="done">Finalizing</span>
            </div>
          </div>
          <span class="update-meta" data-progress-meta>Starting a fresh update run.</span>
          <span class="update-meta">Status refreshes automatically while the update is running.</span>
        </div>
      `;

      const state = {
        active: false,
        progress: 0,
        target: 0,
        stage: "Preparing archive",
        downloadedSize: "0.0 MB",
        totalSize: "Pending",
        eta: "Starting...",
        message: "Preparing archive",
        meta: "Starting a fresh update run.",
        lastBackendAt: 0,
        startedAt: 0,
        forceCompleting: false,
        completeScheduled: false,
        pollTimer: null,
        smoothTimer: null,
        completionTimer: null,
      };

      const parseSizeMb = (value) => {
        const match = String(value || "").match(/([0-9.]+)/);
        return match ? Number(match[1]) : 0;
      };

      const normalizeStage = (snapshot) => {
        const rawStage = String(snapshot?.stage || "").toLowerCase();
        const rawState = String(snapshot?.state || "").toLowerCase();
        if (rawState === "success" || rawStage === "completed") {
          return "completed";
        }
        if (rawStage.includes("download") || rawStage.includes("prepar")) {
          return "download";
        }
        if (rawStage.includes("process") || rawStage.includes("build") || rawStage.includes("cache")) {
          return "build";
        }
        if (rawStage.includes("final")) {
          return "finalizing";
        }
        if (rawState === "error" && Number(snapshot?.percent || 0) >= FINALIZING_PERCENT) {
          return "finalizing";
        }
        return "download";
      };

      const renderPlayerStats = (players) => {
        playerStatsGrid.innerHTML = "";
        if (!players.length) {
          playerStatsEmpty.hidden = false;
          return;
        }
        playerStatsEmpty.hidden = true;
        for (const player of players) {
          const card = document.createElement("article");
          card.className = "player-stat-card";
          card.innerHTML = `
            <h4>${player.name}</h4>
            <div class="player-stat-line"><span>Runs</span><strong>${player.runs}</strong></div>
            <div class="player-stat-line"><span>Wickets</span><strong>${player.wickets}</strong></div>
            <div class="player-stat-line"><span>Matches</span><strong>${player.matches}</strong></div>
          `;
          playerStatsGrid.appendChild(card);
        }
      };

      const loadPlayerStats = async () => {
        try {
          const response = await fetch(`/player-stats?timestamp=${Date.now()}`, { cache: "no-store" });
          if (!response.ok) {
            return;
          }
          const payload = await response.json();
          console.log("[player-stats] fresh payload", payload);
          renderPlayerStats(Array.isArray(payload.players) ? payload.players : []);
        } catch {
        }
      };

      const clearTimers = () => {
        if (state.pollTimer) {
          window.clearInterval(state.pollTimer);
          state.pollTimer = null;
        }
        if (state.smoothTimer) {
          window.clearInterval(state.smoothTimer);
          state.smoothTimer = null;
        }
        if (state.completionTimer) {
          window.clearTimeout(state.completionTimer);
          state.completionTimer = null;
        }
      };

      const ensureStatus = () => {
        let status = document.querySelector(".update-status");
        if (!status) {
          toolbar.insertAdjacentHTML("afterend", statusMarkup);
          status = document.querySelector(".update-status");
        } else {
          status.outerHTML = statusMarkup;
          status = document.querySelector(".update-status");
        }
        return status;
      };

      const render = () => {
        const status = ensureStatus();
        status.querySelector("[data-progress-fill]").style.width = `${state.progress}%`;
        status.querySelector("[data-progress-value]").textContent = `${state.progress}%`;
        status.querySelector("[data-progress-message]").textContent = state.message;
        status.querySelector("[data-progress-meta]").textContent = state.meta;
        status.querySelector("[data-progress-stage]").textContent = state.stage;
        status.querySelector("[data-progress-size]").textContent = `${state.downloadedSize} / ${state.totalSize}`;
        status.querySelector("[data-progress-eta]").textContent = state.eta;
        for (const step of status.querySelectorAll("[data-progress-step]")) {
          step.classList.remove("is-active");
        }
        if (state.progress >= FINALIZING_PERCENT) {
          status.querySelector('[data-progress-step="done"]')?.classList.add("is-active");
        } else if (state.progress >= 70) {
          status.querySelector('[data-progress-step="cache"]')?.classList.add("is-active");
        } else {
          status.querySelector('[data-progress-step="download"]')?.classList.add("is-active");
        }
      };

      const resetForUpdate = () => {
        clearTimers();
        state.active = true;
        state.progress = 0;
        state.target = 0;
        state.stage = "Preparing archive";
        state.downloadedSize = "0.0 MB";
        state.totalSize = "Pending";
        state.eta = "Starting...";
        state.message = "Preparing archive";
        state.meta = "Starting a fresh update run.";
        state.lastBackendAt = Date.now();
        state.startedAt = Date.now();
        state.forceCompleting = false;
        state.completeScheduled = false;
      };

      const complete = () => {
        if (!state.active && state.completeScheduled) {
          return;
        }
        state.progress = 100;
        state.target = 100;
        state.stage = "Completed";
        state.eta = "Completed";
        state.message = "Download Completed ✅";
        state.meta = "The update finished successfully.";
        state.forceCompleting = false;
        state.completeScheduled = true;
        render();
        clearTimers();
        state.active = false;
        button.disabled = false;
        button.textContent = "Update Data";
        loadPlayerStats();
      };

      const failUpdate = (errorMessage) => {
        console.log("[update] failure", errorMessage);
        clearTimers();
        state.active = false;
        state.forceCompleting = false;
        state.completeScheduled = false;
        state.stage = "Failed";
        state.message = "Update failed";
        state.eta = "Retry available";
        state.meta = errorMessage || "Processing failed. Please retry the update.";
        render();
        button.disabled = false;
        button.textContent = "Retry Update";
      };

      const triggerForceComplete = (reason) => {
        if (!state.active) {
          return;
        }
        if (!state.forceCompleting) {
          console.log("[update] force-complete triggered:", reason, {
            progress: state.progress,
            target: state.target,
            stage: state.stage,
          });
        }
        state.forceCompleting = true;
        state.stage = "Finalizing...";
        state.message = "Finalizing...";
        state.eta = "Almost done";
        state.meta = `Completing update automatically (${reason}).`;
        state.target = 100;
        if (state.progress < COMPLETE_AFTER_PERCENT) {
          state.progress = COMPLETE_AFTER_PERCENT;
        }
        render();
      };

      const applySnapshot = (snapshot) => {
        state.lastBackendAt = Date.now();
        state.downloadedSize = snapshot?.downloadedSize || state.downloadedSize;
        state.totalSize = snapshot?.totalSize || state.totalSize;
        state.meta = snapshot?.meta || state.meta;

        const downloadedMb = parseSizeMb(state.downloadedSize);
        const totalMb = parseSizeMb(state.totalSize);
        const sizeRatio = totalMb > 0 ? downloadedMb / totalMb : 0;
        const backendPercent = Math.max(0, Math.min(100, Number(snapshot?.percent || 0)));
        const stageKey = normalizeStage(snapshot);
        const isFailure = snapshot?.success === false || String(snapshot?.state || "").toLowerCase() === "error" || String(snapshot?.stage || "").toLowerCase() === "failed";

        console.log("[update] snapshot", {
          percent: backendPercent,
          stage: snapshot?.stage,
          state: snapshot?.state,
          success: snapshot?.success,
          eta: snapshot?.eta,
          downloadedSize: snapshot?.downloadedSize,
          totalSize: snapshot?.totalSize,
          error: snapshot?.error,
        });

        if (isFailure) {
          failUpdate(snapshot?.error || snapshot?.message || "Update failed while processing Cricsheet data.");
          return;
        }

        if (snapshot?.success === true || stageKey === "completed" || backendPercent >= 100) {
          state.target = 100;
          if (state.progress < COMPLETE_AFTER_PERCENT) {
            state.progress = COMPLETE_AFTER_PERCENT;
          }
          state.stage = "Finalizing...";
          state.message = "Finalizing...";
          state.eta = "Almost done";
          render();
          return;
        }

        if (stageKey === "download") {
          state.forceCompleting = false;
          state.stage = backendPercent > 0 ? "Downloading" : "Preparing archive";
          state.message = snapshot?.message || state.stage;
          state.eta = snapshot?.eta || "Starting...";
          const inferredDownloadTarget = totalMb > 0 ? Math.min(70, Math.round(sizeRatio * 70)) : 0;
          state.target = Math.max(state.target, Math.min(70, Math.max(backendPercent, inferredDownloadTarget)));
          if (sizeRatio >= 0.97 || state.target >= 70) {
            state.stage = "Building cache";
            state.message = "Building cache";
            state.eta = "Calculating ETA";
            state.target = Math.max(state.target, 70);
          }
        } else if (stageKey === "build") {
          state.forceCompleting = false;
          state.stage = backendPercent >= FINALIZING_PERCENT ? "Finalizing..." : "Building cache";
          state.message = snapshot?.message || state.stage;
          state.eta = snapshot?.eta || "Calculating ETA";
          state.target = Math.max(state.target, Math.min(FINALIZING_PERCENT, Math.max(70, backendPercent)));
        } else {
          state.stage = "Finalizing...";
          state.message = snapshot?.message || "Finalizing...";
          state.eta = snapshot?.eta || "Almost done";
          state.target = Math.max(state.target, Math.max(FINALIZING_PERCENT, backendPercent));
          if (state.progress >= FINALIZING_PERCENT) {
            state.forceCompleting = true;
          }
        }

        render();
      };

      const smoothTick = () => {
        if (!state.active) {
          return;
        }

        const now = Date.now();
        const idleFor = now - state.lastBackendAt;
        const runningFor = now - state.startedAt;
        const downloadedMb = parseSizeMb(state.downloadedSize);
        const totalMb = parseSizeMb(state.totalSize);
        const sizeRatio = totalMb > 0 ? downloadedMb / totalMb : 0;
        const isFinalizing = state.stage === "Finalizing..." || state.progress >= FINALIZING_PERCENT || state.target >= FINALIZING_PERCENT;

        if ((isFinalizing && idleFor >= STALE_AFTER_MS) || runningFor >= MAX_UPDATE_MS) {
          triggerForceComplete(runningFor >= MAX_UPDATE_MS ? "max-timeout" : "stale-finalizing");
        } else if (state.stage === "Downloading" && sizeRatio >= 0.97 && idleFor >= 1500) {
          console.log("[update] promoting stalled download to cache build", { sizeRatio, idleFor });
          state.stage = "Building cache";
          state.message = "Building cache";
          state.eta = "Calculating ETA";
          state.target = Math.max(state.target, 70);
        }

        if (state.progress < state.target) {
          state.progress = Math.min(state.target, state.progress + 1);
          if (state.progress >= FINALIZING_PERCENT) {
            state.stage = "Finalizing...";
            if (!state.forceCompleting) {
              state.message = "Finalizing...";
            }
            state.eta = state.progress >= COMPLETE_AFTER_PERCENT ? "Almost done" : state.eta;
          }
          render();
        }

        if (state.progress >= 100 && !state.completeScheduled) {
          state.completeScheduled = true;
          state.completionTimer = window.setTimeout(() => complete(), 250);
        }
      };

      const pollProgress = async () => {
        if (!state.active) {
          return;
        }
        try {
          const response = await fetch("/progress", { cache: "no-store" });
          if (!response.ok) {
            return;
          }
          const snapshot = await response.json();
          applySnapshot(snapshot);
        } catch (error) {
          console.log("[update] progress poll failed", error);
        }
      };

      const beginUpdate = async () => {
        if (state.active) {
          return;
        }
        resetForUpdate();
        button.disabled = true;
        button.textContent = "Updating...";
        render();
        state.pollTimer = window.setInterval(pollProgress, POLL_INTERVAL_MS);
        state.smoothTimer = window.setInterval(smoothTick, SMOOTH_INTERVAL_MS);
        try {
          const response = await fetch(form.action, {
            method: "POST",
            headers: { "Accept": "application/json" },
            body: new FormData(form),
          });
          if (!response.ok) {
            throw new Error(`Update start failed with status ${response.status}`);
          }
          const snapshot = await response.json();
          applySnapshot(snapshot);
        } catch (error) {
          console.log("[update] begin update failed", error);
          failUpdate(error?.message || "Unable to start the update request.");
        }
      };

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        await beginUpdate();
      });

      loadPlayerStats();
    })();
  </script>
</body>
</html>
"""


FORM_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Cricket Win Predictor</title>
  <style>
    :root {{
      --bg: #0c1220;
      --surface: #1a2537;
      --surface-2: #1f2e44;
      --surface-3: #243452;
      --border: #2a3d57;
      --border-bright: #3d5a7a;
      --text: #e2eaf5;
      --muted: #7b93af;
      --dim: #4a6080;
      --accent: #3b82f6;
      --accent-soft: rgba(59,130,246,0.14);
      --green: #22c55e;
      --green-soft: rgba(34,197,94,0.14);
      --amber: #f59e0b;
      --red: #ef4444;
      --shadow: 0 4px 24px rgba(0,0,0,0.5);
      --shadow-sm: 0 2px 12px rgba(0,0,0,0.35);
      --radius: 16px;
      --radius-sm: 10px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
      color: var(--text);
      background: linear-gradient(160deg, #0a0f1e 0%, #0d1627 50%, #0c1525 100%);
      min-height: 100vh;
    }}
    body.theme-international {{
      background: linear-gradient(160deg, #06091a 0%, #0a0f29 50%, #080d22 100%);
    }}
    .page {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 24px 20px 48px;
    }}
    .page-home-link {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 14px;
      color: var(--muted);
      text-decoration: none;
      font-size: 0.88rem;
      font-weight: 500;
      transition: color 150ms ease;
    }}
    .page-home-link:hover {{ color: var(--text); }}
    .top-strip {{
      margin-bottom: 20px;
      border: 1px solid var(--border);
      background: var(--surface);
      border-radius: var(--radius-sm);
      overflow: hidden;
    }}
    .ticker {{
      display: flex;
      gap: 24px;
      white-space: nowrap;
      padding: 10px 16px;
      min-width: max-content;
      animation: ticker-scroll 24s linear infinite;
      font-size: 0.82rem;
      letter-spacing: 0.02em;
      color: var(--muted);
    }}
    .ticker strong {{ color: var(--accent); }}
    @keyframes ticker-scroll {{
      from {{ transform: translateX(0); }}
      to {{ transform: translateX(-35%); }}
    }}
    .hero {{
      display: grid;
      gap: 16px;
      align-items: stretch;
      grid-template-columns: minmax(0, 1.5fr) minmax(260px, 0.85fr);
      margin-bottom: 24px;
    }}
    .hero-copy {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 28px;
      box-shadow: var(--shadow-sm);
      position: relative;
      overflow: hidden;
    }}
    .hero-copy::before {{
      content: "";
      position: absolute;
      top: -60px;
      right: -60px;
      width: 220px;
      height: 220px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(59,130,246,0.1), transparent 70%);
      pointer-events: none;
    }}
    .hero h1 {{
      margin: 0 0 10px;
      font-size: clamp(1.9rem, 2.8vw, 3rem);
      line-height: 1.02;
      letter-spacing: -0.04em;
      color: #fff;
    }}
    .hero p {{
      margin: 0;
      max-width: 680px;
      line-height: 1.65;
      font-size: 0.96rem;
      color: var(--muted);
    }}
    .hero-stats {{ display: grid; gap: 12px; }}
    .hero-stat {{
      background: linear-gradient(135deg, #1d3461, #152a56);
      color: #c8d8f0;
      border: 1px solid rgba(59,130,246,0.2);
      border-radius: var(--radius);
      padding: 18px;
      box-shadow: var(--shadow-sm);
    }}
    body.theme-international .hero-stat {{
      background: linear-gradient(135deg, #2d1b69, #1a1050);
      border-color: rgba(139,92,246,0.2);
    }}
    .hero-stat strong {{
      display: block;
      font-size: 1rem;
      margin-bottom: 6px;
      color: #fff;
    }}
    form {{ display: grid; gap: 18px; }}
    .grid {{
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 22px;
      box-shadow: var(--shadow-sm);
    }}
    .card h2, .card h3 {{
      margin-top: 0;
      letter-spacing: -0.02em;
      color: var(--text);
    }}
    .card p {{ color: var(--muted); }}
    body.theme-international .top-strip,
    body.theme-international .card,
    body.theme-international .history {{
      background: rgba(12, 8, 30, 0.85);
      border-color: rgba(139,92,246,0.2);
    }}
    body.theme-international .hero-copy {{
      background: linear-gradient(135deg, rgba(18,12,46,0.9), rgba(14,18,58,0.9));
      border-color: rgba(139,92,246,0.2);
    }}
    body.theme-international .hero-copy p,
    body.theme-international .card p,
    body.theme-international .history-card p,
    body.theme-international .squad-help,
    body.theme-international .role-tag,
    body.theme-international .badge,
    body.theme-international .ticker,
    body.theme-international .selection-warning {{
      color: rgba(200,190,255,0.7);
    }}
    body.theme-international .badge,
    body.theme-international .selection-status,
    body.theme-international .stats-toggle {{
      background: rgba(139,92,246,0.14);
      border-color: rgba(139,92,246,0.3);
      color: #c4b5fd;
    }}
    body.theme-international input,
    body.theme-international select,
    body.theme-international .history-card,
    body.theme-international .squad-box,
    body.theme-international .player-check,
    body.theme-international .stats-panel,
    body.theme-international .venue-card,
    body.theme-international .venue-stat {{
      background: rgba(10, 6, 24, 0.85);
      border-color: rgba(139,92,246,0.2);
      color: #e0d9ff;
    }}
    body.theme-international .player-check.is-disabled {{
      background: rgba(8, 5, 18, 0.7);
    }}
    body.theme-international .result {{
      background: linear-gradient(135deg, #1e0c5c 0%, #0e2980 100%);
    }}
    .fields {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .fields .full {{ grid-column: 1 / -1; }}
    label {{
      display: grid;
      gap: 6px;
      font-size: 0.86rem;
      font-weight: 600;
      color: var(--muted);
      position: relative;
      z-index: 1;
    }}
    input, select {{
      width: 100%;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background: rgba(0,0,0,0.35);
      font: inherit;
      color: var(--text);
      font-size: 0.9rem;
      transition: border-color 120ms ease, box-shadow 120ms ease;
    }}
    option {{ background: #1a2537; color: #e2eaf5; }}
    input:focus, select:focus {{
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(59,130,246,0.15);
    }}
    .section-title {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 14px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 999px;
      background: rgba(255,255,255,0.06);
      border: 1px solid var(--border);
      color: var(--muted);
      font-size: 0.72rem;
      letter-spacing: 0.04em;
    }}
    .venue-card {{
      display: grid;
      gap: 8px;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      margin-top: 12px;
      padding: 14px;
      border-radius: var(--radius-sm);
      background: rgba(0,0,0,0.2);
      border: 1px solid var(--border);
    }}
    .venue-stat {{
      padding: 10px 12px;
      border-radius: 8px;
      background: var(--surface-2);
      border: 1px solid var(--border);
    }}
    .venue-stat span {{
      display: block;
      margin-bottom: 4px;
      font-size: 0.72rem;
      letter-spacing: 0.04em;
      color: var(--muted);
      text-transform: uppercase;
    }}
    .venue-stat strong {{
      font-size: 0.92rem;
      color: var(--text);
    }}
    button {{
      padding: 13px 24px;
      border: 0;
      border-radius: var(--radius-sm);
      background: var(--accent);
      color: #fff;
      font: inherit;
      font-weight: 700;
      font-size: 0.95rem;
      letter-spacing: 0.01em;
      cursor: pointer;
      box-shadow: 0 4px 16px rgba(59,130,246,0.3);
      transition: all 150ms ease;
    }}
    button:hover {{
      background: #2563eb;
      box-shadow: 0 6px 20px rgba(59,130,246,0.4);
    }}
    button:active {{ transform: translateY(1px); }}
    .result {{
      margin-top: 24px;
      background: linear-gradient(135deg, #0f3460 0%, #0a5568 100%);
      color: #e8f4fd;
      border: 1px solid rgba(59,130,246,0.25);
      border-radius: var(--radius);
      padding: 24px;
      box-shadow: var(--shadow);
      position: relative;
      overflow: hidden;
    }}
    .result::before {{
      content: "Prediction Summary";
      position: absolute;
      right: 16px;
      top: 14px;
      font-size: 0.7rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: rgba(232,244,253,0.4);
    }}
    .result-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      gap: 16px;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }}
    .winner-chip {{
      display: inline-block;
      padding: 5px 12px;
      border-radius: 999px;
      background: rgba(34,197,94,0.2);
      color: #86efac;
      border: 1px solid rgba(34,197,94,0.3);
      font-size: 0.74rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      font-weight: 700;
    }}
    .probabilities {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      margin-top: 14px;
    }}
    .pill {{
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: var(--radius-sm);
      padding: 16px;
    }}
    .pill strong {{ display: block; margin-bottom: 6px; font-size: 0.98rem; }}
    .meter {{
      margin-top: 10px;
      height: 8px;
      width: 100%;
      border-radius: 999px;
      background: rgba(255,255,255,0.1);
      overflow: hidden;
    }}
    .meter-fill {{
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, #22c55e 0%, #3b82f6 60%, #8b5cf6 100%);
    }}
    .insights {{
      display: grid;
      gap: 12px;
      grid-template-columns: minmax(0, 1.2fr) minmax(240px, 0.8fr);
      margin-top: 16px;
    }}
    .insight-card {{
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: var(--radius-sm);
      padding: 18px;
    }}
    .mini-stat {{
      display: flex;
      justify-content: space-between;
      padding: 9px 0;
      border-bottom: 1px solid rgba(255,255,255,0.08);
      font-size: 0.9rem;
    }}
    .mini-stat:last-child {{ border-bottom: 0; }}
    .history {{
      margin-top: 24px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px;
      box-shadow: var(--shadow-sm);
    }}
    .history-grid {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      margin-top: 14px;
    }}
    .history-card {{
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 14px;
      position: relative;
    }}
    .history-card::before {{
      content: "Saved";
      position: absolute;
      right: 12px;
      top: 12px;
      font-size: 0.65rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--dim);
    }}
    .history-card h4 {{ margin: 0 0 6px; font-size: 0.9rem; color: var(--text); }}
    .history-card p {{ margin: 3px 0; color: var(--muted); font-size: 0.84rem; }}
    .history-card a {{ color: var(--accent); }}
    .squad-box {{
      margin-top: 14px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background: rgba(0,0,0,0.2);
      padding: 14px;
    }}
    .squad-box-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin: 0 0 8px;
    }}
    .squad-box-head h3 {{ margin: 0; font-size: 0.95rem; }}
    .squad-box h3 {{ margin: 0 0 8px; font-size: 0.95rem; }}
    .squad-toggle-btn {{
      padding: 5px 12px;
      border: 1px solid var(--border-bright);
      border-radius: 8px;
      background: transparent;
      color: var(--accent);
      font: inherit;
      font-size: 0.8rem;
      font-weight: 700;
      cursor: pointer;
      box-shadow: none;
      transition: all 120ms ease;
    }}
    .squad-toggle-btn:hover {{
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }}
    body.theme-international .squad-toggle-btn {{
      border-color: rgba(139,92,246,0.4);
      color: #a78bfa;
    }}
    body.theme-international .squad-toggle-btn:hover {{
      background: rgba(139,92,246,0.5);
      color: #fff;
    }}
    .squad-help {{ margin: 0 0 10px; color: var(--muted); font-size: 0.86rem; }}
    .selection-status {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin: 0 0 12px;
      padding: 7px 12px;
      border: 1px solid rgba(34,197,94,0.3);
      border-radius: 999px;
      background: var(--green-soft);
      color: #86efac;
    }}
    .selection-status strong {{
      font-size: 0.75rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .selection-status span {{ font-size: 0.84rem; font-weight: 600; color: #4ade80; }}
    .selection-status.is-full {{
      border-color: rgba(245,158,11,0.35);
      background: rgba(245,158,11,0.12);
      color: #fcd34d;
    }}
    .selection-status.is-full span {{ color: #fbbf24; }}
    .selection-warning {{
      margin: 0 0 12px;
      min-height: 1.2em;
      font-size: 0.82rem;
      font-weight: 700;
      color: var(--amber);
      visibility: hidden;
    }}
    .selection-warning.is-visible {{ visibility: visible; }}
    .squad-grid {{
      display: grid;
      gap: 8px;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    }}
    .player-check {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      padding: 9px 11px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background: var(--surface-2);
      font-size: 0.88rem;
      transition: border-color 120ms ease, background 120ms ease;
      cursor: pointer;
    }}
    .player-check:hover {{
      border-color: var(--border-bright);
      background: var(--surface-3);
    }}
    .player-check.is-disabled {{
      opacity: 0.38;
      background: rgba(0,0,0,0.2);
      box-shadow: none;
      pointer-events: none;
    }}
    .player-name {{ flex: 1; font-weight: 600; color: var(--text); }}
    .player-check input {{
      width: auto;
      margin: 0;
      box-shadow: none;
      accent-color: var(--accent);
      background: transparent;
      border: none;
      padding: 0;
    }}
    .player-stats {{ position: relative; margin-left: 4px; }}
    .player-stats.is-open {{ width: 100%; margin-left: 0; margin-top: 8px; }}
    .stats-toggle {{
      width: 26px;
      height: 26px;
      border-radius: 50%;
      border: 1px solid var(--border-bright);
      background: var(--surface);
      color: var(--accent);
      font-weight: 700;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      line-height: 1;
      font-size: 0.9rem;
      box-shadow: none;
      padding: 0;
    }}
    .player-stats-disabled .stats-toggle {{ opacity: 0.35; cursor: not-allowed; }}
    .stats-panel {{
      display: none;
      position: relative;
      width: 100%;
      max-height: 360px;
      overflow: auto;
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background: var(--surface);
      box-shadow: var(--shadow);
    }}
    .player-stats.is-open .stats-panel {{ display: block; }}
    .stats-title {{ margin: 0 0 8px; font-size: 0.8rem; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }}
    .stats-group {{ margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); }}
    .stats-group h5 {{ margin: 0 0 6px; font-size: 0.72rem; letter-spacing: 0.06em; text-transform: uppercase; color: var(--dim); }}
    .stats-copy {{ margin: 0; font-size: 0.8rem; line-height: 1.5; color: var(--muted); }}
    .stats-chip-grid {{ display: grid; gap: 7px; }}
    .stats-summary-grid {{ display: grid; gap: 7px; grid-template-columns: repeat(3, minmax(0, 1fr)); margin-bottom: 8px; }}
    .stats-chip {{
      padding: 8px;
      border-radius: 8px;
      background: rgba(0,0,0,0.25);
      border: 1px solid var(--border);
    }}
    .stats-chip strong {{ display: block; font-size: 0.96rem; color: var(--text); }}
    .stats-chip span {{ font-size: 0.76rem; color: var(--muted); }}
    .stats-line {{ display: flex; justify-content: space-between; gap: 8px; font-size: 0.82rem; padding: 3px 0; color: var(--muted); }}
    .stats-line strong {{ color: var(--text); }}
    .role-tag {{ margin-left: auto; font-size: 0.68rem; letter-spacing: 0.05em; text-transform: uppercase; color: var(--dim); }}
    ul {{ line-height: 1.65; padding-left: 18px; }}
    @media (max-width: 900px) {{
      .hero {{ grid-template-columns: 1fr; }}
      .insights {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 700px) {{
      .fields {{ grid-template-columns: 1fr; }}
      .page {{ padding: 16px 14px 40px; }}
    }}
  </style>
</head>
<body class="{page_mode_class}">
  <div class="page">
    <a class="page-home-link" href="/">&#8592; Back to home</a>
    <section class="top-strip">
      <div class="ticker">
        <span><strong>{ticker_title}</strong> {ticker_copy}</span>
        <span><strong>Inputs</strong> Score, pitch, form, player stats, and chase pressure</span>
        <span><strong>Playing XI</strong> {ticker_squads}</span>
        <span><strong>History</strong> Recent predictions are saved automatically</span>
        <span><strong>{ticker_title}</strong> {ticker_copy}</span>
        <span><strong>Inputs</strong> Score, pitch, form, player stats, and chase pressure</span>
      </div>
    </section>
    <section class="hero">
      <div class="hero-copy">
        <h1>{hero_title}</h1>
        <p>{hero_copy}</p>
      </div>
      <div class="hero-stats">
        <div class="hero-stat">
          <strong>{hero_stat_one_title}</strong>
          {hero_stat_one_body}
        </div>
        <div class="hero-stat">
          <strong>{hero_stat_two_title}</strong>
          {hero_stat_two_body}
        </div>
      </div>
    </section>
    <form method="post">
      <input type="hidden" name="mode" value="{mode}">
      <div class="grid">
        <section class="card">
          <div class="section-title">
            <h2>Match Context</h2>
            <span class="badge">Inputs that shape the chase</span>
          </div>
          <div class="fields">
            <label>Format<select name="format">{format_options}</select></label>
            <label class="full">Venue<select name="venue_code">{venue_options}</select></label>
            <label>First innings score<input name="first_innings_score" type="number" value="{first_innings_score_default}"></label>
            <label>Wickets lost<input name="wickets_lost" type="number" value="6"></label>
            <label>Overs faced<input name="overs_faced" type="number" step="0.1" value="20"></label>
            <label>Pitch surface
              <select name="pitch_surface">{surface_options}</select>
            </label>
            <label>Batting support
              <select name="batting_level">{batting_level_options}</select>
            </label>
            <label>Pace help
              <select name="pace_level">{pace_level_options}</select>
            </label>
            <label>Spin help
              <select name="spin_level">{spin_level_options}</select>
            </label>
            <label>Pitch average score<input name="average_first_innings_score" type="number" step="0.1" value="{average_first_innings_score_value}"></label>
            <label class="full"><span>Dew expected</span><input name="dew_expected" type="checkbox"{dew_checked}></label>
          </div>
          {venue_summary_html}
        </section>
        <section class="card">
          <div class="section-title">
            <h2>Batting First Team</h2>
            <span class="badge">Defending side profile</span>
          </div>
          <div class="fields">
            <label class="full">{team_selector_label}<select name="batting_first_team_code">{batting_team_options}</select></label>
            <label class="full">Team name<input name="batting_first_name" value="{batting_team_name}" readonly></label>
            <label>Batting rating<input name="batting_first_batting_rating" type="number" step="0.1" value="{batting_batting_rating}" readonly></label>
            <label>Bowling rating<input name="batting_first_bowling_rating" type="number" step="0.1" value="{batting_bowling_rating}" readonly></label>
            <label>Fielding rating<input name="batting_first_fielding_rating" type="number" step="0.1" value="{batting_fielding_rating}" readonly></label>
            <label>{batting_h2h_label}<input name="batting_first_recent_form" type="text" value="{batting_recent_form}" readonly></label>
            <label>{batting_team_form_label}<input name="batting_first_team_form" type="text" value="{batting_team_form}" readonly></label>
          </div>
          <div class="squad-box">
            <div class="squad-box-head">
              <h3>Playing 11</h3>
              <button type="button" class="squad-toggle-btn" data-squad-toggle="batting_first_playing">Select 11</button>
            </div>
            <p class="squad-help">{squad_help_text}</p>
            {batting_selection_status}
            {batting_selection_warning}
            <div class="squad-grid">{batting_playing_checkboxes}</div>
          </div>
        </section>
        <section class="card">
          <div class="section-title">
            <h2>Chasing Team</h2>
            <span class="badge">Target pursuit profile</span>
          </div>
          <div class="fields">
            <label class="full">{team_selector_label}<select name="chasing_team_code">{chasing_team_options}</select></label>
            <label class="full">Team name<input name="chasing_name" value="{chasing_team_name}" readonly></label>
            <label>Batting rating<input name="chasing_batting_rating" type="number" step="0.1" value="{chasing_batting_rating}" readonly></label>
            <label>Bowling rating<input name="chasing_bowling_rating" type="number" step="0.1" value="{chasing_bowling_rating}" readonly></label>
            <label>Fielding rating<input name="chasing_fielding_rating" type="number" step="0.1" value="{chasing_fielding_rating}" readonly></label>
            <label>{chasing_h2h_label}<input name="chasing_recent_form" type="text" value="{chasing_recent_form}" readonly></label>
            <label>{chasing_team_form_label}<input name="chasing_team_form" type="text" value="{chasing_team_form}" readonly></label>
          </div>
          <div class="squad-box">
            <div class="squad-box-head">
              <h3>Playing 11</h3>
              <button type="button" class="squad-toggle-btn" data-squad-toggle="chasing_playing">Select 11</button>
            </div>
            <p class="squad-help">{squad_help_text}</p>
            {chasing_selection_status}
            {chasing_selection_warning}
            <div class="squad-grid">{chasing_playing_checkboxes}</div>
          </div>
        </section>
      </div>
      <button type="submit">Predict Winner</button>
    </form>
    {team_library_html}
    {result_html}
    {history_html}
  </div>
  <script>
    const MAX_PLAYING_XI = 11;

    function updatePlayingXiGroup(fieldName) {{
      const checkboxes = Array.from(document.querySelectorAll(`input[type="checkbox"][name="${{fieldName}}"]`));
      if (!checkboxes.length) {{
        return;
      }}

      const checkedCount = checkboxes.filter((checkbox) => checkbox.checked).length;
      for (const checkbox of checkboxes) {{
        checkbox.disabled = checkedCount >= MAX_PLAYING_XI && !checkbox.checked;
        const card = checkbox.closest(".player-check");
        if (card) {{
          card.classList.toggle("is-disabled", checkbox.disabled);
        }}
      }}

      const status = document.querySelector(`[data-selection-status-for="${{fieldName}}"]`);
      if (status) {{
        status.classList.toggle("is-full", checkedCount >= MAX_PLAYING_XI);
        const countLabel = status.querySelector("span");
        if (countLabel) {{
          countLabel.textContent = `${{checkedCount}}/${{MAX_PLAYING_XI}} selected`;
        }}
      }}

      const warning = document.querySelector(`[data-selection-warning-for="${{fieldName}}"]`);
      if (warning) {{
        warning.classList.toggle("is-visible", checkedCount >= MAX_PLAYING_XI);
      }}
    }}

    function bindPlayingXiGroup(fieldName) {{
      const checkboxes = Array.from(document.querySelectorAll(`input[type="checkbox"][name="${{fieldName}}"]`));
      for (const checkbox of checkboxes) {{
        checkbox.addEventListener("change", () => updatePlayingXiGroup(fieldName));
      }}
      updatePlayingXiGroup(fieldName);
    }}

    function bindPlayerInsights() {{
      const insightWrappers = Array.from(document.querySelectorAll(".player-stats"));
      const toggles = Array.from(document.querySelectorAll(".stats-toggle"));

      function syncMatchupRows(wrapper) {{
        const opponentField = wrapper.dataset.opponentField;
        if (!opponentField) {{
          return;
        }}
        const selectedOpposition = new Set(
          Array.from(document.querySelectorAll(`input[type="checkbox"][name="${{opponentField}}"]:checked`))
            .map((checkbox) => checkbox.value)
        );
        const battingRows = Array.from(wrapper.querySelectorAll('.matchup-row[data-kind="batting"]'));
        let visibleRows = 0;
        for (const row of battingRows) {{
          const playerName = row.getAttribute("data-player-name");
          const shouldShow = !!playerName && selectedOpposition.has(playerName);
          row.hidden = !shouldShow;
          if (shouldShow) {{
            visibleRows += 1;
          }}
        }}
        const battingEmpty = wrapper.querySelector(".matchup-empty");
        if (battingEmpty) {{
          battingEmpty.hidden = visibleRows > 0;
        }}

        const bowlingRows = Array.from(wrapper.querySelectorAll('.bowling-matchup-row[data-kind="bowling"]'));
        let bowlingVisibleRows = 0;
        let totalRuns = 0;
        let totalBalls = 0;
        let totalOuts = 0;
        for (const row of bowlingRows) {{
          const playerName = row.getAttribute("data-player-name");
          const shouldShow = !!playerName && selectedOpposition.has(playerName);
          row.hidden = !shouldShow;
          if (shouldShow) {{
            bowlingVisibleRows += 1;
            totalRuns += Number(row.getAttribute("data-runs") || "0");
            totalBalls += Number(row.getAttribute("data-balls") || "0");
            totalOuts += Number(row.getAttribute("data-outs") || "0");
          }}
        }}
        const wicketsTarget = wrapper.querySelector("[data-bowling-wickets]");
        const economyTarget = wrapper.querySelector("[data-bowling-economy]");
        const strikeRateTarget = wrapper.querySelector("[data-bowling-strike-rate]");
        if (wicketsTarget) {{
          wicketsTarget.textContent = `${{totalOuts}}`;
        }}
        if (economyTarget) {{
          const economy = totalBalls ? ((totalRuns * 6) / totalBalls).toFixed(2) : "0.00";
          economyTarget.textContent = economy;
        }}
        if (strikeRateTarget) {{
          const strikeRate = totalOuts ? (totalBalls / totalOuts).toFixed(2) : "No wickets";
          strikeRateTarget.textContent = `${{strikeRate}}`;
        }}
        const bowlingEmpty = wrapper.querySelector(".bowling-matchup-empty");
        if (bowlingEmpty) {{
          bowlingEmpty.hidden = bowlingVisibleRows > 0;
        }}
      }}

      function closeAllInsights(exceptWrapper) {{
        for (const wrapper of insightWrappers) {{
          if (wrapper !== exceptWrapper) {{
            wrapper.classList.remove("is-open");
          }}
        }}
      }}

      for (const toggle of toggles) {{
        toggle.addEventListener("click", (event) => {{
          event.preventDefault();
          event.stopPropagation();
          const wrapper = toggle.closest(".player-stats");
          if (!wrapper) {{
            return;
          }}
          const willOpen = !wrapper.classList.contains("is-open");
          closeAllInsights(wrapper);
          wrapper.classList.toggle("is-open", willOpen);
          if (willOpen) {{
            syncMatchupRows(wrapper);
          }}
        }});
      }}

      document.addEventListener("click", (event) => {{
        if (!(event.target instanceof Element) || !event.target.closest(".player-stats")) {{
          closeAllInsights(null);
        }}
      }});

      for (const checkbox of document.querySelectorAll('input[type="checkbox"][name="batting_first_playing"], input[type="checkbox"][name="chasing_playing"]')) {{
        checkbox.addEventListener("change", () => {{
          for (const wrapper of insightWrappers) {{
            if (wrapper.classList.contains("is-open")) {{
              syncMatchupRows(wrapper);
            }}
          }}
        }});
      }}
    }}

    function bindContextRefresh() {{
      const form = document.querySelector("form");
      if (!form) {{
        return;
      }}
      const battingTeamField = form.querySelector('[name="batting_first_team_code"]');
      const chasingTeamField = form.querySelector('[name="chasing_team_code"]');

      function syncDistinctTeams(changedField, otherField) {{
        if (!changedField || !otherField || changedField.value !== otherField.value) {{
          return;
        }}
        const nextOption = Array.from(otherField.options).find((option) => option.value !== changedField.value);
        if (nextOption) {{
          otherField.value = nextOption.value;
        }}
      }}

      const refreshFields = ["venue_code", "format", "batting_first_team_code", "chasing_team_code"];
      for (const fieldName of refreshFields) {{
        const field = form.querySelector(`[name="${{fieldName}}"]`);
        if (!field) {{
          continue;
        }}
        field.addEventListener("change", () => {{
          if (fieldName === "batting_first_team_code") {{
            syncDistinctTeams(battingTeamField, chasingTeamField);
          }} else if (fieldName === "chasing_team_code") {{
            syncDistinctTeams(chasingTeamField, battingTeamField);
          }}
          form.requestSubmit();
        }});
      }}
    }}

    bindPlayingXiGroup("batting_first_playing");
    bindPlayingXiGroup("chasing_playing");
    bindPlayerInsights();
    bindContextRefresh();

    function bindSquadToggleButtons() {{
      for (const btn of document.querySelectorAll('[data-squad-toggle]')) {{
        btn.addEventListener('click', () => {{
          const fieldName = btn.dataset.squadToggle;
          const checkboxes = Array.from(document.querySelectorAll(`input[type="checkbox"][name="${{fieldName}}"]`));
          const checkedCount = checkboxes.filter(cb => cb.checked).length;
          if (checkedCount > 0) {{
            for (const cb of checkboxes) {{
              cb.checked = false;
              cb.disabled = false;
              const card = cb.closest('.player-check');
              if (card) card.classList.remove('is-disabled');
            }}
            btn.textContent = 'Select 11';
          }} else {{
            let selected = 0;
            for (const cb of checkboxes) {{
              if (selected < 11) {{ cb.checked = true; selected++; }}
              else {{ cb.checked = false; }}
            }}
            btn.textContent = 'Deselect All';
          }}
          updatePlayingXiGroup(fieldName);
        }});
      }}
    }}
    bindSquadToggleButtons();
  </script>
</body>
</html>
"""

RESULT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Prediction Result — Cricket Win Predictor</title>
  <style>
    :root {{
      --surface: #1a2537;
      --surface-2: #1f2e44;
      --border: #2a3d57;
      --border-bright: #3d5a7a;
      --text: #e2eaf5;
      --muted: #7b93af;
      --dim: #4a6080;
      --accent: #3b82f6;
      --green: #22c55e;
      --amber: #f59e0b;
      --shadow: 0 4px 24px rgba(0,0,0,0.5);
      --shadow-sm: 0 2px 12px rgba(0,0,0,0.35);
      --radius: 16px;
      --radius-sm: 10px;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
      color: var(--text);
      background: linear-gradient(160deg, #0a0f1e 0%, #0d1627 50%, #0c1525 100%);
      min-height: 100vh;
    }}
    body.theme-international {{
      background: linear-gradient(160deg, #06091a 0%, #0a0f29 50%, #080d22 100%);
    }}
    .page {{
      max-width: 900px;
      margin: 0 auto;
      padding: 28px 20px 60px;
    }}
    .nav {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 32px;
    }}
    .nav-link {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      text-decoration: none;
      font-size: 0.88rem;
      font-weight: 500;
      transition: color 150ms ease;
    }}
    .nav-link:hover {{ color: var(--text); }}
    .nav-right {{
      display: flex;
      gap: 10px;
    }}
    .nav-btn {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 14px;
      border: 1px solid var(--border-bright);
      border-radius: var(--radius-sm);
      background: var(--surface);
      color: var(--text);
      text-decoration: none;
      font-size: 0.84rem;
      font-weight: 600;
      transition: all 150ms ease;
    }}
    .nav-btn:hover {{
      border-color: var(--accent);
      color: var(--accent);
    }}
    /* Winner hero */
    .winner-hero {{
      position: relative;
      overflow: hidden;
      padding: 48px 40px;
      border-radius: 20px;
      background: linear-gradient(135deg, #0f3460 0%, #0a5568 60%, #0d4a3a 100%);
      border: 1px solid rgba(59,130,246,0.25);
      box-shadow: var(--shadow);
      text-align: center;
      margin-bottom: 24px;
    }}
    body.theme-international .winner-hero {{
      background: linear-gradient(135deg, #1e0c5c 0%, #0e2980 100%);
      border-color: rgba(139,92,246,0.25);
    }}
    .winner-hero::before {{
      content: "";
      position: absolute;
      inset: 0;
      background: radial-gradient(ellipse at 50% -20%, rgba(34,197,94,0.18), transparent 60%);
      pointer-events: none;
    }}
    .winner-label {{
      display: inline-block;
      padding: 5px 14px;
      border-radius: 999px;
      background: rgba(34,197,94,0.2);
      color: #86efac;
      border: 1px solid rgba(34,197,94,0.35);
      font-size: 0.74rem;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      margin-bottom: 16px;
    }}
    .winner-name {{
      font-size: clamp(2.4rem, 6vw, 4rem);
      font-weight: 800;
      letter-spacing: -0.04em;
      color: #fff;
      line-height: 1;
      margin-bottom: 10px;
    }}
    .winner-sub {{
      font-size: 0.96rem;
      color: rgba(255,255,255,0.6);
    }}
    .confidence-badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-top: 20px;
      padding: 8px 16px;
      border-radius: 999px;
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.14);
      font-size: 0.86rem;
      color: rgba(255,255,255,0.8);
    }}
    .confidence-badge strong {{ color: #fff; }}
    /* Probability bars */
    .probs {{
      display: grid;
      gap: 14px;
      grid-template-columns: 1fr 1fr;
      margin-bottom: 24px;
    }}
    .prob-card {{
      padding: 22px;
      border-radius: var(--radius);
      background: var(--surface);
      border: 1px solid var(--border);
      box-shadow: var(--shadow-sm);
    }}
    .prob-card.is-winner {{
      border-color: rgba(34,197,94,0.35);
      background: rgba(20,40,30,0.9);
    }}
    .prob-label {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 6px;
    }}
    .prob-team {{
      font-size: 0.82rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .prob-card.is-winner .prob-team {{ color: #4ade80; }}
    .prob-pct {{
      font-size: 1.8rem;
      font-weight: 800;
      letter-spacing: -0.04em;
      color: var(--text);
      margin-bottom: 4px;
    }}
    .prob-card.is-winner .prob-pct {{ color: #4ade80; }}
    .prob-role {{
      font-size: 0.8rem;
      color: var(--muted);
      margin-bottom: 14px;
    }}
    .meter {{
      height: 8px;
      border-radius: 999px;
      background: rgba(255,255,255,0.08);
      overflow: hidden;
    }}
    .meter-fill {{
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, #22c55e 0%, #3b82f6 60%, #8b5cf6 100%);
    }}
    /* Insights */
    .insights-grid {{
      display: grid;
      gap: 14px;
      grid-template-columns: 1.3fr 0.7fr;
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 22px;
      box-shadow: var(--shadow-sm);
    }}
    .card h3 {{
      font-size: 0.82rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 14px;
    }}
    .card ul {{
      padding-left: 18px;
      line-height: 1.75;
      font-size: 0.9rem;
      color: var(--text);
    }}
    .card ul li {{ margin-bottom: 4px; }}
    .stat-row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 0;
      border-bottom: 1px solid var(--border);
      font-size: 0.9rem;
    }}
    .stat-row:last-child {{ border-bottom: none; }}
    .stat-row span {{ color: var(--muted); }}
    .stat-row strong {{ color: var(--text); }}
    .win-tag {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 6px;
      background: rgba(34,197,94,0.15);
      color: #4ade80;
      font-size: 0.76rem;
      font-weight: 700;
    }}
    @media (max-width: 700px) {{
      .page {{ padding: 16px 14px 48px; }}
      .winner-hero {{ padding: 36px 20px; }}
      .probs {{ grid-template-columns: 1fr; }}
      .insights-grid {{ grid-template-columns: 1fr; }}
      .nav {{ flex-wrap: wrap; }}
    }}
  </style>
</head>
<body class="{page_mode_class}">
  <div class="page">
    <nav class="nav">
      <a class="nav-link" href="/{back_href}">&#8592; Back to form</a>
      <div class="nav-right">
        <a class="nav-btn" href="/">&#8962; Home</a>
      </div>
    </nav>

    <div class="winner-hero">
      <div class="winner-label">Predicted Winner</div>
      <div class="winner-name">{winner_name}</div>
      <div class="winner-sub">{match_summary}</div>
      <div class="confidence-badge">
        Model confidence &nbsp;<strong>{confidence:.2f}</strong>
      </div>
    </div>

    <div class="probs">
      <div class="prob-card {batting_winner_class}">
        <div class="prob-label">
          <span class="prob-team">{batting_team}</span>
          {batting_win_tag}
        </div>
        <div class="prob-pct">{batting_pct:.1f}%</div>
        <div class="prob-role">Defending · batting first</div>
        <div class="meter"><div class="meter-fill" style="width:{batting_pct:.1f}%"></div></div>
      </div>
      <div class="prob-card {chasing_winner_class}">
        <div class="prob-label">
          <span class="prob-team">{chasing_team}</span>
          {chasing_win_tag}
        </div>
        <div class="prob-pct">{chasing_pct:.1f}%</div>
        <div class="prob-role">Chasing · set target</div>
        <div class="meter"><div class="meter-fill" style="width:{chasing_pct:.1f}%"></div></div>
      </div>
    </div>

    <div class="insights-grid">
      <div class="card">
        <h3>Why the model leaned this way</h3>
        <ul>{explanation_items}</ul>
      </div>
      <div class="card">
        <h3>Quick Read</h3>
        <div class="stat-row"><span>Winner</span><strong>{winner_name}</strong></div>
        <div class="stat-row"><span>Defending</span><strong>{batting_pct:.1f}%</strong></div>
        <div class="stat-row"><span>Chasing</span><strong>{chasing_pct:.1f}%</strong></div>
        <div class="stat-row"><span>Confidence</span><strong>{confidence:.2f}</strong></div>
        <div class="stat-row"><span>Format</span><strong>{match_format}</strong></div>
      </div>
    </div>
  </div>
</body>
</html>
"""


def _render_result_page(pred: dict[str, Any]) -> str:
    batting_pct = max(0.0, min(100.0, pred["batting_first_win_probability"]))
    chasing_pct = max(0.0, min(100.0, pred["chasing_win_probability"]))
    is_batting_winner = pred["predicted_winner"] == pred["batting_first_team"]
    explanation_items = "".join(f"<li>{escape(item)}</li>" for item in pred["explanation"])
    win_tag = '<span class="win-tag">&#10003; Winner</span>'
    mode = pred.get("mode", "ipl")
    back_href = f"?mode={mode}"
    return RESULT_HTML.format(
        page_mode_class="theme-international" if mode == "international" else "",
        back_href=back_href,
        winner_name=escape(pred["predicted_winner"]),
        match_summary=escape(
            f"{pred['batting_first_team']} vs {pred['chasing_team']} · {pred['match_format'].upper()} · {pred['venue']}"
        ),
        confidence=pred["confidence"],
        batting_team=escape(pred["batting_first_team"]),
        chasing_team=escape(pred["chasing_team"]),
        batting_pct=batting_pct,
        chasing_pct=chasing_pct,
        batting_winner_class="is-winner" if is_batting_winner else "",
        chasing_winner_class="is-winner" if not is_batting_winner else "",
        batting_win_tag=win_tag if is_batting_winner else "",
        chasing_win_tag=win_tag if not is_batting_winner else "",
        explanation_items=explanation_items,
        match_format=escape(pred["match_format"].upper()),
    )


def _render_result(result: Any) -> str:
    explanation_items = "".join(f"<li>{escape(item)}</li>" for item in result.explanation)
    batting_width = max(0.0, min(100.0, result.batting_first_win_probability))
    chasing_width = max(0.0, min(100.0, result.chasing_win_probability))
    return f"""
    <section class="result">
      <div class="result-header">
        <div>
          <span class="winner-chip">Predicted Winner</span>
          <h2>{escape(result.predicted_winner)}</h2>
        </div>
        <div class="pill">
          <strong>Confidence</strong>
          <div>{result.confidence:.2f}</div>
        </div>
      </div>
      <div class="probabilities">
        <div class="pill">
          <strong>{escape(result.batting_first_team)}</strong>
          <div>{result.batting_first_win_probability:.2f}% win probability</div>
          <div class="meter"><div class="meter-fill" style="width: {batting_width:.2f}%"></div></div>
        </div>
        <div class="pill">
          <strong>{escape(result.chasing_team)}</strong>
          <div>{result.chasing_win_probability:.2f}% win probability</div>
          <div class="meter"><div class="meter-fill" style="width: {chasing_width:.2f}%"></div></div>
        </div>
      </div>
      <div class="insights">
        <div class="insight-card">
          <h3>Why the model leaned this way</h3>
          <ul>{explanation_items}</ul>
        </div>
        <div class="insight-card">
          <h3>Quick Read</h3>
          <div class="mini-stat"><span>Likely result</span><strong>{escape(result.predicted_winner)}</strong></div>
          <div class="mini-stat"><span>Defending side</span><strong>{result.batting_first_win_probability:.2f}%</strong></div>
          <div class="mini-stat"><span>Chasing side</span><strong>{result.chasing_win_probability:.2f}%</strong></div>
          <div class="mini-stat"><span>Model confidence</span><strong>{result.confidence:.2f}</strong></div>
        </div>
      </div>
    </section>
    """


def _render_team_options(mode: str, selected_code: str) -> str:
    options = []
    for code, preset in _team_bank(mode).items():
        selected = " selected" if code == selected_code else ""
        options.append(f'<option value="{code}"{selected}>{escape(preset["name"])}</option>')
    return "".join(options)


def _default_selected_names(mode: str, team_code: str) -> list[str]:
    squad = _team_bank(mode).get(team_code, {}).get("squad", [])
    return [entry["name"] for entry in squad[:11]]


def _resolved_selected_names(mode: str, team_code: str, selected_names: list[str] | None) -> list[str]:
    squad = _team_bank(mode).get(team_code, {}).get("squad", [])
    squad_names = {entry["name"] for entry in squad}
    valid_names = [name for name in (selected_names or []) if name in squad_names]
    return valid_names[:11] if valid_names else _default_selected_names(mode, team_code)


_PLAYER_INSIGHTS_CACHE: dict[str, Any] | None = None
_PLAYER_INSIGHTS_CACHE_MTIME: float | None = None


def _normalize_stat_key(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _load_player_insights() -> dict[str, Any]:
    global _PLAYER_INSIGHTS_CACHE, _PLAYER_INSIGHTS_CACHE_MTIME
    try:
        cache_mtime = PLAYER_INSIGHTS_CACHE_PATH.stat().st_mtime
    except FileNotFoundError:
        _PLAYER_INSIGHTS_CACHE = {"players": {}}
        _PLAYER_INSIGHTS_CACHE_MTIME = None
        return _PLAYER_INSIGHTS_CACHE

    if _PLAYER_INSIGHTS_CACHE is None or _PLAYER_INSIGHTS_CACHE_MTIME != cache_mtime:
        try:
            _PLAYER_INSIGHTS_CACHE = json.loads(PLAYER_INSIGHTS_CACHE_PATH.read_text(encoding="utf-8"))
            _PLAYER_INSIGHTS_CACHE_MTIME = cache_mtime
        except (FileNotFoundError, json.JSONDecodeError):
            _PLAYER_INSIGHTS_CACHE = {"players": {}}
            _PLAYER_INSIGHTS_CACHE_MTIME = None
    return _PLAYER_INSIGHTS_CACHE


def _team_head_to_head_summary(mode: str, team_name: str, opponent_name: str, match_format: str) -> str:
    if not team_name or not opponent_name or team_name == opponent_name:
        return "Choose different teams"
    cache = _load_player_insights()
    pair_key = "||".join(sorted([team_name, opponent_name]))
    matches = cache.get("team_head_to_head", {}).get(pair_key, [])
    if not isinstance(matches, list):
        return "No H2H data"
    preferred_team_type = "international" if _mode_key(mode) == "international" else "club"
    preferred_format = match_format.upper()
    filtered = [
        item
        for item in matches
        if item.get("team_type") == preferred_team_type and item.get("format") == preferred_format
    ] or [item for item in matches if item.get("team_type") == preferred_team_type] or matches
    last_five = filtered[:5]
    if not last_five:
        return "No H2H data"
    wins = sum(1 for item in last_five if item.get("winner") == team_name)
    losses = sum(1 for item in last_five if item.get("winner") == opponent_name)
    no_results = sum(1 for item in last_five if item.get("winner") not in {team_name, opponent_name})
    summary = f"{wins}W - {losses}L"
    if no_results:
        summary += f" - {no_results}NR"
    return f"{summary} in last {len(last_five)}"


def _team_recent_form_summary(mode: str, team_name: str, match_format: str) -> str:
    if not team_name:
        return "No team selected"
    cache = _load_player_insights()
    team_matches: list[dict[str, Any]] = []
    for matches in cache.get("team_head_to_head", {}).values():
        if not isinstance(matches, list):
            continue
        for item in matches:
            teams = item.get("teams", [])
            if isinstance(teams, list) and team_name in teams:
                team_matches.append(item)
    preferred_team_type = "international" if _mode_key(mode) == "international" else "club"
    preferred_format = match_format.upper()
    filtered = [
        item
        for item in team_matches
        if item.get("team_type") == preferred_team_type and item.get("format") == preferred_format
    ] or [item for item in team_matches if item.get("team_type") == preferred_team_type] or team_matches
    filtered.sort(key=lambda item: str(item.get("date", "")), reverse=True)
    last_ten = filtered[:10]
    if not last_ten:
        return "No recent team data"
    wins = sum(1 for item in last_ten if item.get("winner") == team_name)
    losses = sum(1 for item in last_ten if item.get("winner") and item.get("winner") != team_name)
    no_results = sum(1 for item in last_ten if not item.get("winner"))
    summary = f"{wins}W - {losses}L"
    if no_results:
        summary += f" - {no_results}NR"
    return f"{summary} in last {len(last_ten)}"


def _player_overall_strength(player: Player) -> int:
    batting_component = player.batting_average * 1.1 + player.strike_rate * 0.22
    bowling_component = (55.0 - player.bowling_average) * 1.3 + (9.8 - player.economy_rate) * 9.0
    blended = batting_component if player.role in {"batter", "wicket_keeper"} else bowling_component
    if player.role == "all_rounder":
        blended = (batting_component + bowling_component) / 2
    strength = max(45.0, min(98.0, blended * 0.42 + player.recent_form * 35.0 + player.fitness * 10.0))
    return int(round(strength))


def _recent_scores_markup(player_name: str, mode: str) -> str:
    entry = _load_player_insights().get("players", {}).get(player_name, {})
    recent_scores = entry.get("recent_scores", [])
    preferred_team_type = "international" if _mode_key(mode) == "international" else "club"
    filtered = [item for item in recent_scores if item.get("team_type") == preferred_team_type] or recent_scores
    if not filtered:
        return "<p class=\"stats-copy\">No Cricsheet innings found yet.</p>"
    chips = []
    for innings in filtered[:5]:
        chips.append(
            f'<div class="stats-chip"><strong>{innings["score"]}</strong><span>{innings["balls"]}b vs {escape(str(innings["opposition"]))}</span></div>'
        )
    return f'<div class="stats-chip-grid">{"".join(chips)}</div>'


def _venue_record_markup(player_name: str, venue_name: str) -> str:
    entry = _load_player_insights().get("players", {}).get(player_name, {})
    venues = entry.get("venues", {})
    venue_key = _normalize_stat_key(venue_name)
    selected = next(
        (
            stats
            for name, stats in venues.items()
            if _normalize_stat_key(name) == venue_key
            or venue_key in _normalize_stat_key(name)
            or _normalize_stat_key(name) in venue_key
        ),
        None,
    )
    if not selected:
        return "<p class=\"stats-copy\">No venue-specific batting record found in the local cache.</p>"
    return (
        "<div class=\"stats-line\"><span>Runs</span><strong>{runs}</strong></div>"
        "<div class=\"stats-line\"><span>Innings</span><strong>{innings}</strong></div>"
        "<div class=\"stats-line\"><span>Average</span><strong>{average}</strong></div>"
        "<div class=\"stats-line\"><span>Best</span><strong>{best}</strong></div>"
    ).format(**selected)


def _matchup_markup(player_name: str, opponent_bowlers: list[Player]) -> str:
    entry = _load_player_insights().get("players", {}).get(player_name, {})
    matchups = entry.get("matchups", {})
    if not opponent_bowlers:
        return "<p class=\"stats-copy\">Pick the opposition XI to see matchup numbers.</p>"
    rows = []
    for bowler in opponent_bowlers:
        stats = matchups.get(bowler.name)
        if not stats:
            rows.append(f'<div class="stats-line matchup-row" data-kind="batting" data-player-name="{escape(bowler.name)}"><span>{escape(bowler.name)}</span><strong>No data</strong></div>')
            continue
        rows.append(
            f'<div class="stats-line matchup-row" data-kind="batting" data-player-name="{escape(bowler.name)}"><span>{escape(bowler.name)}</span><strong>{stats["runs"]} runs, {stats["balls"]} balls, {stats["outs"]} outs</strong></div>'
        )
    return f'<div class="matchup-list">{"".join(rows)}</div><p class="stats-copy matchup-empty" hidden>No selected bowlers in the opposition XI yet.</p>'


def _bowling_matchup_markup(bowler_name: str, opponent_batters: list[Player]) -> str:
    if not opponent_batters:
        return "<p class=\"stats-copy\">Pick the opposition XI to see bowling matchup numbers.</p>"
    cache = _load_player_insights().get("players", {})
    rows = []
    for batter in opponent_batters:
        stats = cache.get(batter.name, {}).get("matchups", {}).get(bowler_name)
        if not stats:
            rows.append(
                f'<div class="stats-line bowling-matchup-row" data-kind="bowling" data-player-name="{escape(batter.name)}" data-runs="0" data-balls="0" data-outs="0"><span>{escape(batter.name)}</span><strong>No data</strong></div>'
            )
            continue
        rows.append(
            f'<div class="stats-line bowling-matchup-row" data-kind="bowling" data-player-name="{escape(batter.name)}" data-runs="{stats["runs"]}" data-balls="{stats["balls"]}" data-outs="{stats["outs"]}"><span>{escape(batter.name)}</span><strong>{stats["runs"]} runs, {stats["balls"]} balls, {stats["outs"]} outs</strong></div>'
        )
    return (
        '<div class="stats-summary-grid">'
        '<div class="stats-chip"><strong data-bowling-wickets>0</strong><span>Wickets</span></div>'
        '<div class="stats-chip"><strong data-bowling-economy>0.00</strong><span>Economy</span></div>'
        '<div class="stats-chip"><strong data-bowling-strike-rate>0.00</strong><span>Strike rate</span></div>'
        '</div>'
        f'<div class="matchup-list">{"".join(rows)}</div>'
        '<p class="stats-copy bowling-matchup-empty" hidden>No selected batters in the opposition XI yet.</p>'
    )


def _render_player_stats(player: Player, mode: str, venue: dict[str, Any], opponent_bowlers: list[Player], opponent_batters: list[Player]) -> str:
    overall_strength = _player_overall_strength(player)
    lines = [
        f'<div class="stats-line"><span>Overall strength</span><strong>{overall_strength}/100</strong></div>',
        f'<div class="stats-line"><span>Role</span><strong>{escape(player.role.replace("_", " "))}</strong></div>',
        f'<div class="stats-line"><span>Bat avg</span><strong>{player.batting_average:.1f}</strong></div>',
        f'<div class="stats-line"><span>Strike rate</span><strong>{player.strike_rate:.1f}</strong></div>',
        f'<div class="stats-line"><span>Bowl avg</span><strong>{player.bowling_average:.1f}</strong></div>',
        f'<div class="stats-line"><span>Economy</span><strong>{player.economy_rate:.1f}</strong></div>',
        f'<div class="stats-line"><span>Form score</span><strong>{_display_form_score(player.recent_form)}/100</strong></div>',
    ]
    sections = [
        f'<div class="stats-group"><h5>Recent scores</h5>{_recent_scores_markup(player.name, mode)}</div>',
        f'<div class="stats-group"><h5>At {escape(venue["name"])}</h5>{_venue_record_markup(player.name, venue["name"])}</div>',
    ]
    if player.role in {"batter", "wicket_keeper", "all_rounder"}:
        sections.append(f'<div class="stats-group"><h5>Batting vs selected bowlers</h5>{_matchup_markup(player.name, opponent_bowlers)}</div>')
    if player.role in {"bowler", "all_rounder"}:
        sections.append(f'<div class="stats-group"><h5>Bowling vs selected batters</h5>{_bowling_matchup_markup(player.name, opponent_batters)}</div>')
    return f'<div class="stats-panel"><h4 class="stats-title">{escape(player.name)} profile</h4>{"".join(lines)}{"".join(sections)}</div>'


def _render_playing_checkboxes(mode: str, team_code: str, field_name: str, selected_names: list[str], venue: dict[str, Any], opponent_bowlers: list[Player], opponent_batters: list[Player], opponent_field_name: str) -> str:
    squad = _team_bank(mode).get(team_code, {}).get("squad", [])
    selected_set = set(selected_names or _default_selected_names(mode, team_code))
    parts = []
    for entry in squad:
        is_selected = entry["name"] in selected_set
        checked = " checked" if is_selected else ""
        role_label = entry["role"].replace("_", " ")
        if is_selected:
            player = _player_from_roster_entry(entry)
            stats_html = _render_player_stats(player, mode, venue, opponent_bowlers, opponent_batters)
            stats_toggle_html = (
                f'<div class="player-stats" data-opponent-field="{opponent_field_name}">'
                f'<button type="button" class="stats-toggle" aria-label="View stats for {escape(entry["name"])}">i</button>'
                f"{stats_html}</div>"
            )
        else:
            stats_toggle_html = (
                '<div class="player-stats player-stats-disabled">'
                f'<button type="button" class="stats-toggle" aria-label="View stats for {escape(entry["name"])}" disabled>i</button>'
                "</div>"
            )
        parts.append(
            f'<div class="player-check"><input type="checkbox" name="{field_name}" value="{escape(entry["name"])}"{checked}>'
            f'<span class="player-name">{escape(entry["name"])}</span><span class="role-tag">{escape(role_label)}</span>'
            f"{stats_toggle_html}</div>"
        )
    return "".join(parts)


def _render_selection_status(field_name: str, selected_names: list[str]) -> str:
    count = min(len(selected_names), 11)
    return (
        f'<div class="selection-status" data-selection-status-for="{field_name}">'
        f"<strong>Playing XI</strong><span>{count}/11 selected</span></div>"
    )


def _render_selection_warning(field_name: str, selected_names: list[str]) -> str:
    is_full = len(selected_names) >= 11
    visible_class = " is-visible" if is_full else ""
    return (
        f'<p class="selection-warning{visible_class}" data-selection-warning-for="{field_name}">'
        "Playing XI locked. Uncheck one player to choose another.</p>"
    )


def _render_venue_options(mode: str, selected_code: str) -> str:
    bank = _venue_bank(mode)
    if _mode_key(mode) != "international":
        options = []
        for code, venue in bank.items():
            sel = " selected" if code == selected_code else ""
            options.append(f'<option value="{code}"{sel}>{escape(venue["name"])} — {escape(venue["city"])}</option>')
        return "".join(options)

    # Group international venues by country
    by_country: dict[str, list[tuple[str, dict]]] = {}
    for code, venue in bank.items():
        country = venue.get("country", "Other")
        by_country.setdefault(country, []).append((code, venue))

    parts = []
    for country in sorted(by_country):
        parts.append(f'<optgroup label="{escape(country)}">')
        for code, venue in by_country[country]:
            sel = " selected" if code == selected_code else ""
            parts.append(f'<option value="{code}"{sel}>{escape(venue["name"])} — {escape(venue["city"])}</option>')
        parts.append("</optgroup>")
    return "".join(parts)


def _venue_average_label(venue: dict[str, Any], match_format: str) -> str:
    recent = _venue_recent_average(venue, match_format)
    if not recent:
        return "Average 1st inns"
    if recent["n"] == 0:
        return "Average 1st inns (no recent games here; format average)"
    return f"Average 1st inns (last {recent['n']} games, to {recent['last']})"


def _render_venue_summary(venue: dict[str, Any], match_format: str) -> str:
    average_score = _venue_average_score(venue, match_format)
    if match_format == "test":
        highest_value = int(venue.get("highest_test", 0))
        highest_label = "Highest Test innings"
        lowest_defended = 0
        typical_winning_score = int(venue.get("typical_winning_score_test", round(average_score + 40)))
    elif match_format == "odi":
        highest_value = int(venue.get("highest_odi", 0))
        highest_label = "Highest ODI total"
        lowest_defended = 0
        typical_winning_score = int(venue.get("typical_winning_score_t20", round(average_score + 12)))
    else:
        highest_value = int(venue.get("highest_t20", 0))
        highest_label = "Highest T20 total"
        lowest_defended = int(venue.get("lowest_defended_t20", 0))
        typical_winning_score = int(venue.get("typical_winning_score_t20", round(average_score + 8)))
    lines = [
        f'<div class="venue-stat"><span>City</span><strong>{escape(venue["city"])}, {escape(venue["country"])}</strong></div>',
        f'<div class="venue-stat"><span>Approx straight boundary</span><strong>{venue["straight_boundary_m"]} m</strong></div>',
        f'<div class="venue-stat"><span>Approx square boundary</span><strong>{venue["square_boundary_m"]} m</strong></div>',
        f'<div class="venue-stat"><span>{escape(_venue_average_label(venue, match_format))}</span><strong>{average_score:.0f}</strong></div>',
        f'<div class="venue-stat"><span>{highest_label}</span><strong>{highest_value if highest_value else "N/A"}</strong></div>',
        f'<div class="venue-stat"><span>Lowest defended T20</span><strong>{lowest_defended if lowest_defended else "N/A"}</strong></div>',
        f'<div class="venue-stat"><span>Typical winning T20 score</span><strong>{typical_winning_score}</strong></div>',
        f'<div class="venue-stat"><span>Pitch profile</span><strong>{escape(str(venue["surface"]).replace("_", " ").title())}</strong></div>',
    ]
    return f'<div class="venue-card">{"".join(lines)}</div>'


def _render_select_options(options: list[tuple[str, str]], selected_value: str) -> str:
    parts = []
    for value, label in options:
        selected = " selected" if value == selected_value else ""
        parts.append(f'<option value="{value}"{selected}>{label}</option>')
    return "".join(parts)


def _render_team_library(mode: str) -> str:
    cards = []
    bank = _team_bank(mode)
    is_international = _mode_key(mode) == "international"
    for code, preset in bank.items():
        squad = ", ".join(entry["name"] for entry in preset["squad"])
        cards.append(
            f"""
            <article class="history-card">
              <h4>{escape(code)} &middot; {escape(preset["name"])}</h4>
              <p><strong>Squad:</strong> {escape(squad)}</p>
              <p><strong>Source:</strong> <a href="{escape(preset["source_url"])}" target="_blank" rel="noreferrer">{'ICC team reference' if is_international else 'Official IPL squad'}</a></p>
            </article>
            """
        )
    return f"""
    <section class="history">
      <div class="section-title">
        <h2>{"International Squad Bank" if is_international else "IPL 2026 Squad Bank"}</h2>
        <span class="badge">{"National team presets" if is_international else "Official squad presets"}</span>
      </div>
      <div class="history-grid">
        {"".join(cards)}
      </div>
    </section>
    """


def _render_history(history: list[dict[str, Any]]) -> str:
    if not history:
        return """
        <section class="history">
          <div class="section-title">
            <h2>Recent Predictions</h2>
            <span class="badge">History updates after each prediction</span>
          </div>
          <p>No saved predictions yet. Submit a match once and it will appear here.</p>
        </section>
        """

    cards = []
    for entry in history:
        cards.append(
            f"""
            <article class="history-card">
              <h4>{escape(entry["batting_first_team"])} vs {escape(entry["chasing_team"])}</h4>
              <p><strong>Winner:</strong> {escape(entry["predicted_winner"])}</p>
              <p><strong>Score:</strong> {entry["first_innings_score"]}</p>
              <p><strong>Defending:</strong> {entry["batting_first_win_probability"]:.2f}%</p>
              <p><strong>Chasing:</strong> {entry["chasing_win_probability"]:.2f}%</p>
              <p><strong>Confidence:</strong> {entry["confidence"]:.2f}</p>
              <p><strong>Format:</strong> {escape(entry["format"])}</p>
              <p><strong>Saved:</strong> {escape(entry["timestamp"])}</p>
            </article>
            """
        )

    return f"""
    <section class="history">
      <div class="section-title">
        <h2>Recent Predictions</h2>
        <span class="badge">Last {len(history)} saved runs</span>
      </div>
      <div class="history-grid">
        {"".join(cards)}
      </div>
    </section>
    """


def _render_page(
    mode: str,
    result_html: str,
    history_html: str,
    venue_code: str | None = None,
    match_format: str = "t20",
    batting_team_code: str | None = None,
    chasing_team_code: str | None = None,
    batting_selected_names: list[str] | None = None,
    chasing_selected_names: list[str] | None = None,
) -> str:
    mode = _mode_key(mode)
    default_batting_code, default_chasing_code = _default_team_codes(mode)
    bank = _team_bank(mode)
    venue_code = venue_code or _default_venue_code(mode)
    venue = _venue_preset(mode, venue_code)
    batting_team_code = batting_team_code or default_batting_code
    chasing_team_code = chasing_team_code or default_chasing_code
    if batting_team_code == chasing_team_code:
        chasing_team_code = next(
            (code for code in bank if code != batting_team_code),
            default_chasing_code,
        )
    batting_preset = bank.get(batting_team_code, bank[default_batting_code])
    chasing_preset = bank.get(chasing_team_code, bank[default_chasing_code])
    batting_selected_names = _resolved_selected_names(mode, batting_team_code, batting_selected_names)
    chasing_selected_names = _resolved_selected_names(mode, chasing_team_code, chasing_selected_names)
    batting_players = [_player_from_roster_entry(entry) for entry in batting_preset["squad"] if entry["name"] in batting_selected_names][:12]
    chasing_players = [_player_from_roster_entry(entry) for entry in chasing_preset["squad"] if entry["name"] in chasing_selected_names][:12]
    batting_opponent_bowlers = [
        _player_from_roster_entry(entry)
        for entry in chasing_preset["squad"]
        if entry["name"] in chasing_selected_names and entry["role"] in {"bowler", "all_rounder"}
    ]
    chasing_opponent_bowlers = [
        _player_from_roster_entry(entry)
        for entry in batting_preset["squad"]
        if entry["name"] in batting_selected_names and entry["role"] in {"bowler", "all_rounder"}
    ]
    batting_opponent_batters = [
        _player_from_roster_entry(entry)
        for entry in chasing_preset["squad"]
        if entry["name"] in chasing_selected_names and entry["role"] in {"batter", "wicket_keeper", "all_rounder"}
    ]
    chasing_opponent_batters = [
        _player_from_roster_entry(entry)
        for entry in batting_preset["squad"]
        if entry["name"] in batting_selected_names and entry["role"] in {"batter", "wicket_keeper", "all_rounder"}
    ]
    batting_batting_rating, batting_bowling_rating, batting_recent_form = _team_strength_from_players(batting_players)
    chasing_batting_rating, chasing_bowling_rating, chasing_recent_form = _team_strength_from_players(chasing_players)
    batting_fielding_rating = _fielding_strength_from_players(batting_players, batting_preset["fielding_rating"])
    chasing_fielding_rating = _fielding_strength_from_players(chasing_players, chasing_preset["fielding_rating"])
    is_international = mode == "international"
    return FORM_HTML.format(
        page_mode_class=f"theme-{mode}",
        mode=mode,
        ticker_title="International desk" if is_international else "Live predictor",
        ticker_copy="National match probability workspace" if is_international else "Mid-innings win probability workspace",
        ticker_squads="National team presets tuned for international fixtures" if is_international else "Team squads updated from official IPL pages",
        hero_title="International Match Predictor" if is_international else "Cricket Win Predictor",
        hero_copy="Read ODI or T20 internationals from a dedicated national-team desk with a darker tournament look and international squad presets." if is_international else "Estimate the likely winner after the first innings with a cleaner view of score context, pitch behavior, team balance, player quality, and current form.",
        hero_stat_one_title="National Match Read" if is_international else "Fast Match Read",
        hero_stat_one_body="Switch into an international-focused desk with national squads, cleaner contrast, and the same quick mid-innings prediction flow." if is_international else "Use score, wickets, overs, dew, and pitch trend in one place without jumping across sections.",
        hero_stat_two_title="Tournament Theme" if is_international else "Cleaner Team Setup",
        hero_stat_two_body="Choose two international sides, lock the playing XI, and compare the chase through a dedicated tournament-style page." if is_international else "Pick the actual playing XI, compare team strength, and read the result with clearer probability cards.",
        team_selector_label="International team" if is_international else "IPL 2026 team",
        squad_help_text="Select up to 11 players from the national squad. The predictor uses the checked XI." if is_international else "Select up to 11 players from the IPL squad. The predictor uses the checked XI.",
        format_options=_render_select_options(
            [("t20", "T20"), ("odi", "ODI"), ("test", "Test")] if is_international else [("t20", "T20"), ("odi", "ODI")],
            match_format,
        ),
        venue_options=_render_venue_options(mode, venue_code),
        surface_options=_render_select_options(
            [
                ("balanced", "Balanced"),
                ("batting", "Batting-friendly"),
                ("pace", "Pace-friendly"),
                ("spin", "Spin-friendly"),
                ("slow", "Slow / low"),
            ],
            str(venue.get("surface", "balanced")),
        ),
        batting_level_options=_render_select_options([("medium", "Medium"), ("high", "High"), ("low", "Low")], str(venue.get("batting_level", "medium"))),
        pace_level_options=_render_select_options([("medium", "Medium"), ("high", "High"), ("low", "Low")], str(venue.get("pace_level", "medium"))),
        spin_level_options=_render_select_options([("medium", "Medium"), ("high", "High"), ("low", "Low")], str(venue.get("spin_level", "medium"))),
        average_first_innings_score_value=f"{_venue_average_score(venue, match_format):.0f}",
        dew_checked=" checked" if venue.get("batting_level") == "high" else "",
        venue_summary_html=_render_venue_summary(venue, match_format),
        batting_team_options=_render_team_options(mode, batting_team_code),
        chasing_team_options=_render_team_options(mode, chasing_team_code),
        team_library_html=_render_team_library(mode),
        first_innings_score_default={"t20": 182, "odi": 270, "test": 280}.get(match_format, 182),
        result_html=result_html,
        history_html=history_html,
        batting_team_name=escape(batting_preset["name"]),
        chasing_team_name=escape(chasing_preset["name"]),
        batting_batting_rating=batting_batting_rating,
        batting_bowling_rating=batting_bowling_rating,
        batting_fielding_rating=batting_fielding_rating,
        batting_h2h_label=f"Last 5 vs {escape(chasing_preset['name'])}",
        batting_recent_form=_team_head_to_head_summary(mode, batting_preset["name"], chasing_preset["name"], match_format),
        batting_team_form_label="Team form last 10",
        batting_team_form=_team_recent_form_summary(mode, batting_preset["name"], match_format),
        chasing_batting_rating=chasing_batting_rating,
        chasing_bowling_rating=chasing_bowling_rating,
        chasing_fielding_rating=chasing_fielding_rating,
        chasing_h2h_label=f"Last 5 vs {escape(batting_preset['name'])}",
        chasing_recent_form=_team_head_to_head_summary(mode, chasing_preset["name"], batting_preset["name"], match_format),
        chasing_team_form_label="Team form last 10",
        chasing_team_form=_team_recent_form_summary(mode, chasing_preset["name"], match_format),
        batting_selection_status=_render_selection_status("batting_first_playing", batting_selected_names),
        batting_selection_warning=_render_selection_warning("batting_first_playing", batting_selected_names),
        chasing_selection_status=_render_selection_status("chasing_playing", chasing_selected_names),
        chasing_selection_warning=_render_selection_warning("chasing_playing", chasing_selected_names),
        batting_playing_checkboxes=_render_playing_checkboxes(mode, batting_team_code, "batting_first_playing", batting_selected_names, venue, batting_opponent_bowlers, batting_opponent_batters, "chasing_playing"),
        chasing_playing_checkboxes=_render_playing_checkboxes(mode, chasing_team_code, "chasing_playing", chasing_selected_names, venue, chasing_opponent_bowlers, chasing_opponent_batters, "batting_first_playing"),
    )


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
            if not allowed or (parsed.path == "/" and "mode" in params):  # no old server-rendered pages online
                self._send_redirect("/")
                return
            if parsed.path == "/api/photos" and not PUBLIC_IMAGES:
                self._send_json({})
                return
        # ---- new single-page app ----
        if parsed.path == "/" and "mode" not in params:
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
                self._send_json({"error": f"{type(exc).__name__}: {exc}"}, status=500)
            return
        # ---- original pages ("classic") ----
        if parsed.path == "/classic":
            self._send_html(_render_home())
            return
        if parsed.path in {"/update-status", "/progress"}:
            self._send_json(UPDATE_SERVICE.snapshot())
            return
        if parsed.path == "/player-stats":
            self._send_json(UPDATE_SERVICE.get_player_stats())
            return
        if parsed.path == "/result":
            if _LAST_RESULT is None:
                self._send_redirect("/")
                return
            self._send_html(_render_result_page(_LAST_RESULT))
            return
        mode = _mode_key(params.get("mode", [""])[0])
        if "mode" not in params:
            self._send_html(_render_home())
            return
        self._send_html(_render_page(mode, "", _render_history(_read_history()), _default_venue_code(mode), "t20"))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        _REQ.history, _REQ.changed = [], False
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
        if parsed.path == "/update-data":
            snapshot = UPDATE_SERVICE.start_update()
            accepts = self.headers.get("Accept", "")
            if "application/json" in accepts:
                self._send_json(snapshot)
            else:
                self._send_redirect("/classic")
            return
        if parsed.path.startswith("/api/"):
            app = sys.modules[__name__]
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(length) if length else b""
                payload = json.loads(raw.decode("utf-8")) if raw else {}
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
                self._send_json({"error": f"{type(exc).__name__}: {exc}"}, status=500)
            return

        global _LAST_RESULT
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        context = parse_form_body(body)
        result = predict_match_winner(context)
        _save_prediction(context, result)
        form = parse_qs(body.decode("utf-8"), keep_blank_values=True)
        mode = _mode_key(form.get("mode", ["ipl"])[0])
        match_format = form.get("format", ["t20"])[0]
        venue_code = form.get("venue_code", [_default_venue_code(mode)])[0]
        venue = _venue_bank(mode).get(venue_code, {})
        _LAST_RESULT = {
            "mode": mode,
            "match_format": match_format,
            "venue": venue.get("name", venue_code),
            "batting_first_team": result.batting_first_team,
            "chasing_team": result.chasing_team,
            "predicted_winner": result.predicted_winner,
            "batting_first_win_probability": result.batting_first_win_probability,
            "chasing_win_probability": result.chasing_win_probability,
            "confidence": result.confidence,
            "explanation": list(result.explanation),
        }
        self._send_redirect("/result")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_html(self, html: str) -> None:
        encoded = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

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


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    host = os.environ.get("CREASE_HOST", host)
    port = int(os.environ.get("PORT", port))
    _start_auto_exit()
    if not PUBLIC:  # the online copy gets new models by upload, not by downloading and retraining itself
        # a test copy (its own history file, or CREASE_NO_AUTO_UPDATE=1) never downloads or rebuilds the real data
        if os.environ.get("CREASE_NO_AUTO_UPDATE") != "1" and not os.environ.get("CRICKET_HISTORY_PATH"):
            UPDATE_SERVICE.start_auto_updates()
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

    threading.Thread(target=practice_run, daemon=True, name="practice-run").start()
    server = ThreadingHTTPServer((host, port), PredictorHandler)
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

