"""Which match a link is about, from the link's own text (ESPNcricinfo, Cricbuzz and most cricket sites put the teams
and the match in the address). The website itself is never read: only the words in the link.

    espncricinfo.com/series/england-in-australia-2026-1499000/australia-vs-england-2nd-t20i-1499012/full-scorecard
    cricbuzz.com/live-cricket-scores/112233/aus-vs-eng-2nd-t20i-england-tour-of-australia-2026
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote, urlparse

# short forms used in links -> the team's name
SHORT = {
    "aus": "Australia", "eng": "England", "ind": "India", "nz": "New Zealand", "sa": "South Africa", "rsa": "South Africa",
    "pak": "Pakistan", "sl": "Sri Lanka", "ban": "Bangladesh", "wi": "West Indies", "afg": "Afghanistan", "ire": "Ireland",
    "zim": "Zimbabwe", "sco": "Scotland", "ned": "Netherlands", "nep": "Nepal", "uae": "United Arab Emirates", "oma": "Oman",
    "usa": "United States of America", "nam": "Namibia", "can": "Canada",
    "csk": "Chennai Super Kings", "mi": "Mumbai Indians", "rcb": "Royal Challengers Bengaluru", "kkr": "Kolkata Knight Riders",
    "srh": "Sunrisers Hyderabad", "dc": "Delhi Capitals", "pbks": "Punjab Kings", "rr": "Rajasthan Royals",
    "gt": "Gujarat Titans", "lsg": "Lucknow Super Giants",
    "six": "Sydney Sixers", "sys": "Sydney Sixers", "thu": "Sydney Thunder", "syt": "Sydney Thunder", "prs": "Perth Scorchers",
    "str": "Adelaide Strikers", "ads": "Adelaide Strikers", "hea": "Brisbane Heat", "brh": "Brisbane Heat",
    "hur": "Hobart Hurricanes", "hbh": "Hobart Hurricanes", "ren": "Melbourne Renegades", "mlr": "Melbourne Renegades",
    "sta": "Melbourne Stars", "mls": "Melbourne Stars",
}
MATCH = re.compile(r"(\d+(?:st|nd|rd|th))-(t20i|odi|test|t20|match)|(final|semi-final|qualifier-\d|qualifier|eliminator)")
FORMAT = re.compile(r"\b(t20i|odi|test|t20)\b")


def _slug(url: str) -> str:
    """The match part of the link: the path segment holding 'vs' (or 'v')."""
    u = unquote(str(url or "").strip())
    if "://" not in u:
        u = "https://" + u
    parts = [p for p in urlparse(u).path.lower().split("/") if p]
    for p in parts:
        if re.search(r"(^|-)(vs|v)-", p):
            return p
    return "-".join(parts)


def _team(words: list[str], names: list[str]) -> str | None:
    """A team from the words on one side of 'vs': a short form (aus) or the name spelt out (new-zealand-women)."""
    words = [w for w in words if w not in ("women", "w", "men", "u19")]
    if not words:
        return None
    text = " ".join(words)
    by_slug = {re.sub(r"[^a-z ]", "", n.lower()): n for n in names}
    for k in sorted(by_slug, key=len, reverse=True):  # the longest name that the words start or end with
        if text == k or text.startswith(k + " ") or text.endswith(" " + k):
            return by_slug[k]
    for w in (words[0], words[-1]):
        if w in SHORT and SHORT[w] in names:
            return SHORT[w]
        if w.endswith("w") and w[:-1] in SHORT and SHORT[w[:-1]] in names:  # Cricbuzz women's short forms: ausw, brhw
            return SHORT[w[:-1]]
    return None


def parse(url: str, names: list[str]) -> dict[str, Any]:
    """{teams: [a, b] or None, match: '2nd T20I' / 'Final' / None, format: 't20'/'odi'/None, women: bool, words: slug}."""
    slug = _slug(url)
    women = bool(re.search(r"(^|-)(women|w)(-|$)", slug)) or "wbbl" in slug or "womens" in slug
    m = re.search(r"(?:^|-)(vs|v)-", slug)
    teams = None
    if m:
        left = slug[:m.start()].split("-")
        right_all = slug[m.end():].split("-")
        a = _team(left[-4:], names) or _team(left, names)
        b = None
        for n in range(min(5, len(right_all)), 0, -1):  # the right side runs on into the match words: try 5, 4 … 1 words
            b = _team(right_all[:n], names)
            if b:
                break
        if a and b and a != b:
            teams = [a, b]
    hit = MATCH.search(slug)
    match = None
    if hit:
        if hit.group(1):
            kind = {"t20i": "T20I", "odi": "ODI", "test": "Test", "t20": "T20", "match": "Match"}[hit.group(2)]
            match = f"{hit.group(1)} {kind}"
        else:
            match = hit.group(3).replace("-", " ").title()
    fm = FORMAT.search(slug.replace("-", " "))
    fmt = None if not fm else ("odi" if fm.group(1) == "odi" else "test" if fm.group(1) == "test" else "t20")
    return {"teams": teams, "match": match, "format": fmt, "women": women, "words": slug}


def find(info: dict[str, Any], matches: list[dict[str, Any]], key=lambda s: s, check_women: bool = True) -> dict[str, Any] | None:
    """The CricketData match for a parsed link: same two teams (and men's / women's), the same match number when the
    link has one, the right format; the most recent if several fit."""
    if not info.get("teams"):
        return None
    want = {key(t) for t in info["teams"]}
    fits = []
    for m in matches:
        if {key(m.get("team1", "")), key(m.get("team2", ""))} != want or (check_women and bool(m.get("women")) != info["women"]):
            continue
        name = str(m.get("name", "")).lower()
        if info.get("match") and info["match"].lower() not in name:
            continue
        if info.get("format") in ("t20", "odi") and m.get("format") and m["format"] != info["format"]:
            continue
        fits.append(m)
    return max(fits, key=lambda m: m.get("date", "")) if fits else None
