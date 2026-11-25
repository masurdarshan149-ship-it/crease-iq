"""Track forecasts made at the innings break and score them after Cricsheet publishes."""

from __future__ import annotations

import math
import os
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from . import ml_model, tracking
from .ml_features import FORMAT_MAX_BALLS

DATA = Path(__file__).resolve().parents[1] / "data"
ROWS_PATH = DATA / "ml" / "training_rows.csv.gz"
VARIANTS = ("first_innings", "chase_start", "blend")
COMPETITIONS = ("IPL", "T20I", "ODI")
FinishedFixtures = set[tuple[str, str, frozenset[str]]]


class Fixture(NamedTuple):
    competition: str
    batting: str
    chasing: str


class Checkpoint(NamedTuple):
    fixture: Fixture
    runs: int
    wickets: int
    balls: int


def database_path() -> Path | None:
    configured = os.environ.get("CREASE_INNINGS_TRIAL_PATH")
    if configured:
        return Path(configured)
    if os.environ.get("CRICKET_HISTORY_PATH"):  # alternate app copies need an explicit trial path
        return None
    return DATA / "innings_break_trial.sqlite3"


def competition(mode: str, fmt: str) -> str:
    return "IPL" if mode == "ipl" else "ODI" if fmt == "odi" else "T20I"


def _days(day: date) -> tuple[str, ...]:
    # Cricsheet uses venue dates, which can differ from the computer's date around midnight.
    return tuple((day + timedelta(days=offset)).isoformat() for offset in (0, -1, 1))


def _finished_fixtures() -> FinishedFixtures:
    archived, _ = tracking._results()
    return {
        (m["date"], m["format"], frozenset(ml_model._team_key(m[k]) for k in ("team1", "team2")))
        for m in archived + tracking._live()
        if m.get("date") and m.get("format") and m.get("team1") and m.get("team2")
    }


def _is_finished(finished: FinishedFixtures, day: str, fixture: Fixture) -> bool:
    fmt = "odi" if fixture.competition == "ODI" else "t20"
    teams = frozenset((fixture.batting, fixture.chasing))
    return any((d, fmt, teams) in finished for d in _days(date.fromisoformat(day)))


def record(path: Path, now: datetime, snapshot: Checkpoint, first: float, chase: float,
           win_version: str | None, chase_version: str | None) -> None:
    """Freeze the first forecast for this exact score; both probabilities are for the batting-first side."""
    fixture = snapshot.fixture
    if not (fixture.batting and fixture.chasing and fixture.batting != fixture.chasing):
        return
    if not all(0 <= p <= 1 for p in (first, chase)):
        return
    day = now.date().isoformat()
    if _is_finished(_finished_fixtures(), day, fixture):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=1)) as db, db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS forecasts (
                day TEXT, competition TEXT, batting TEXT, chasing TEXT,
                runs INTEGER, wickets INTEGER, balls INTEGER, captured_at REAL,
                first_innings REAL, chase_start REAL, blend REAL,
                win_version TEXT, chase_version TEXT,
                PRIMARY KEY (day, competition, batting, chasing, runs, wickets, balls)
            )
        """)
        db.execute("""
            INSERT OR IGNORE INTO forecasts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (day, *fixture, snapshot.runs, snapshot.wickets, snapshot.balls, now.timestamp(),
              first, chase, (first + chase) / 2, win_version, chase_version))


@lru_cache(maxsize=1)
def _archive(path: Path, _mtime_ns: int, _size: int) -> dict[tuple[str, Checkpoint], dict[str, int]]:
    """Use the builder's full-length, decided games and match the exact first-innings score."""
    import pandas as pd

    columns = ("match_id", "date", "fam", "batting_team", "chasing_team", "label_batting_first_won",
               "runs", "wickets", "balls", "is_ipl", "is_league")
    df = pd.read_csv(path, usecols=columns, dtype={"match_id": str})
    full = df["balls"].ge(df["fam"].map(FORMAT_MAX_BALLS))
    terminal = df.loc[df["is_league"].eq(0) & (full | df["wickets"].ge(10)), list(columns)]
    results = defaultdict(dict)
    for row in terminal.itertuples(index=False):
        fixture = Fixture(competition("ipl" if row.is_ipl else "international", row.fam),
                          row.batting_team, row.chasing_team)
        key = (row.date, Checkpoint(fixture, row.runs, row.wickets, row.balls))
        results[key][row.match_id] = int(row.label_batting_first_won)
    return results


def _scores(samples: list[tuple[sqlite3.Row, int]]) -> dict:
    result = {"matches": len(samples)}
    for variant in VARIANTS:
        right = 0
        loss = 0.0
        for row, won in samples:
            prob = min(0.9999, max(0.0001, row[variant]))
            right += (prob >= 0.5) == bool(won)
            loss -= math.log(prob if won else 1 - prob)
        result[variant] = {"right": right, "log_loss": round(loss / len(samples), 4) if samples else None}
    return result


def report(path: Path | None) -> dict:
    """Score each verified fixture once, using the earliest matching forecast."""
    rows = []
    if path is not None and path.is_file():
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=1)) as db:
            db.row_factory = sqlite3.Row
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='forecasts'").fetchone():
                rows = db.execute("SELECT * FROM forecasts ORDER BY captured_at, rowid").fetchall()
    archive = {}
    if rows and ROWS_PATH.is_file():
        stat = ROWS_PATH.stat()
        archive = _archive(ROWS_PATH, stat.st_mtime_ns, stat.st_size)
    latest = max((day for day, _ in archive), default="")
    finished = _finished_fixtures() if rows else set()
    samples = defaultdict(list)
    seen = set()
    waiting = excluded = 0
    for row in rows:
        fixture = Fixture(row["competition"], row["batting"], row["chasing"])
        snapshot = Checkpoint(fixture, row["runs"], row["wickets"], row["balls"])
        matches = {}
        days = _days(date.fromisoformat(row["day"]))
        for d in days:
            matches.update(archive.get((d, snapshot), {}))
        if len(matches) == 1:
            match_id, won = next(iter(matches.items()))
            if match_id in seen:
                excluded += 1
            else:
                seen.add(match_id)
                samples["All matches"].append((row, won))
                samples[fixture.competition].append((row, won))
        elif len(matches) > 1:
            excluded += 1
        elif _is_finished(finished, row["day"], fixture):
            # A live result without an archived innings could still become eligible on the next update.
            if latest > max(days):
                excluded += 1
            else:
                waiting += 1
        else:
            waiting += 1
    return {
        "recorded": len(rows), "waiting": waiting, "excluded": excluded,
        "groups": {key: _scores(samples[key]) for key in ("All matches", *COMPETITIONS)},
    }
