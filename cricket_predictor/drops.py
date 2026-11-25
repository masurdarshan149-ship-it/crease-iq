"""Dropped catches: you log them while watching (the Drop button in live scoring); the real catches for the same
match come from Cricsheet after the next update. drop % = drops / (drops + catches) over the matches you logged.

Until a team has enough logged matches with real data, the app shows an estimate instead (clearly marked):
the typical T20 drop rate, nudged by how many catches the team takes per match compared with the average.

Log file: data/drops_log.json (set CRICKET_DROPS_PATH for a test copy).
"""

from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

PATH = Path(os.environ.get("CRICKET_DROPS_PATH") or Path(__file__).resolve().parents[1] / "data" / "drops_log.json")
MIN_MATCHES = 2            # logged matches with real catch data before a measured % is shown
BASE_DROP = {"t20": 0.17, "odi": 0.15}   # typical share of catchable chances that go down (estimate baseline)
_lock = threading.Lock()


def _read() -> list[dict[str, Any]]:
    if not PATH.exists():
        return []
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _write(items: list[dict[str, Any]]) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(items, indent=1), encoding="utf-8")


def log(fielding: str, batting: str, fmt: str, mode: str, delta: int = 1, day: str | None = None) -> dict[str, Any]:
    """Add (or with delta=-1 take back) a dropped catch by `fielding` in today's match against `batting`."""
    day = day or date.today().isoformat()
    key = f"{day}|{fmt}|{fielding}|{batting}"
    with _lock:
        items = _read()
        entry = next((e for e in items if e["key"] == key), None)
        if entry is None:
            entry = {"key": key, "date": day, "format": fmt, "mode": mode, "fielding": fielding, "batting": batting,
                     "drops": 0, "logged_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
            items.append(entry)
        entry["drops"] = max(0, int(entry["drops"]) + int(delta))
        entry["logged_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        items = [e for e in items if e["drops"] > 0 or e is entry]
        _write(items)
    return {"fielding": fielding, "batting": batting, "date": day, "drops": entry["drops"]}


def today_count(fielding: str, batting: str, fmt: str) -> int:
    key = f"{date.today().isoformat()}|{fmt}|{fielding}|{batting}"
    return next((int(e["drops"]) for e in _read() if e["key"] == key), 0)


def _catches_for(entry: dict[str, Any], fielding_log: list[dict[str, Any]]) -> int | None:
    """Real catches by the fielding side in that match (Cricsheet), matched by teams and date (±1 day)."""
    d = date.fromisoformat(entry["date"])
    days = {(d + timedelta(days=k)).isoformat() for k in (-1, 0, 1)}
    hits = [r for r in fielding_log if r["team"] == entry["fielding"] and r["opponent"] == entry["batting"]
            and r["date"] in days and r["format"] == entry["format"]]
    return sum(r["catches"] for r in hits) if hits else None


def team_stats(team: str, fmt: str, fielding_log: list[dict[str, Any]]) -> dict[str, Any]:
    """Measured drop % from your logged matches: {matches, waiting, drops, catches, pct}."""
    mine = [e for e in _read() if e["fielding"] == team and e["format"] == fmt]
    drops = catches = matched = 0
    waiting = 0
    for e in mine:
        c = _catches_for(e, fielding_log)
        if c is None:
            waiting += 1
            continue
        matched += 1
        drops += int(e["drops"])
        catches += c
    pct = round(drops * 100 / (drops + catches), 1) if (drops + catches) and matched >= MIN_MATCHES else None
    return {"matches": matched, "waiting": waiting, "drops": drops, "catches": catches, "pct": pct, "min_matches": MIN_MATCHES}


def estimate(team_catches_pm: float | None, avg_catches_pm: float | None, fmt: str) -> dict[str, Any] | None:
    """Rough drop % when nothing is measured yet: fewer catches per match than average → more likely to drop.

    The grade compares the team with the average: A = clearly fewer drops expected ... E = clearly more.
    """
    if not team_catches_pm or not avg_catches_pm:
        return None
    ratio = avg_catches_pm / team_catches_pm            # >1: takes fewer catches than average
    est = max(0.08, min(0.30, BASE_DROP.get(fmt, 0.17) * ratio ** 1.5))
    rel = est / BASE_DROP.get(fmt, 0.17)
    grade = "A" if rel <= 0.85 else "B" if rel <= 0.95 else "C" if rel <= 1.05 else "D" if rel <= 1.15 else "E"
    return {"pct": round(est * 100, 1), "grade": grade}
