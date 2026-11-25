"""Kalman-filter (state-space) team ratings: each team's strength is a hidden number that drifts over time, plus how
sure we are of it. Replaced Elo as the win and chase models' team-strength input on 10 Nov 2026
(scripts/kalman_experiment.py: better log loss at every stage, on the 2024 tuning season and on unseen 2025-26).

Units: log-odds of winning. A team's uncertainty grows by DRIFT per day without a game (capped at a year, so an IPL
off-season counts but a five-year gap doesn't explode) and shrinks after each result; unsure teams move more.

Ratings are rebuilt from data/ml/training_rows.csv.gz (the same matches the models learn from) whenever a model is
trained, and the final state is saved to data/ml/kalman_ratings.json for the app.
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .once import locked_cache

ROOT = Path(__file__).resolve().parents[1]
ROWS_PATH = ROOT / "data" / "ml" / "training_rows.csv.gz"
STATE_PATH = ROOT / "data" / "ml" / "kalman_ratings.json"

DRIFT = 0.001        # variance added per day without a game (picked on the 2024 tuning season)
START_VAR = 1.0      # a new team's uncertainty (also the ceiling)
MAX_GAP_DAYS = 365


def _drifted(var: float, days: int) -> float:
    return min(var + DRIFT * min(max(days, 0), MAX_GAP_DAYS), START_VAR)


def run(matches: Iterable[tuple[Any, int, str, str, str, int]]) -> tuple[dict[Any, tuple[float, float]], dict[str, dict[str, list[float]]]]:
    """matches: (match_id, day ordinal, fam, batting-first team, chasing team, 1 if batting first won), oldest first.

    Returns the pre-match (rating gap bat - chase, uncertainty) per match and the final state {fam: {team: [mean, var, day]}}.
    """
    mean: dict[tuple[str, str], float] = {}
    var: dict[tuple[str, str], float] = {}
    last: dict[tuple[str, str], int] = {}
    out: dict[Any, tuple[float, float]] = {}
    for match_id, day, fam, bat, chase, bat_won in matches:
        a, b = (fam, bat), (fam, chase)
        for t in (a, b):
            if t not in mean:
                mean[t], var[t], last[t] = 0.0, START_VAR, day
            else:
                var[t] = _drifted(var[t], day - last[t])
                last[t] = day
        d = mean[a] - mean[b]
        out[match_id] = (d, math.sqrt(var[a] + var[b]))
        p = 1.0 / (1.0 + math.exp(-d))
        h = p * (1.0 - p)
        s = h * h * (var[a] + var[b]) + h
        ka, kb = var[a] * h / s, var[b] * h / s
        err = float(bat_won) - p
        mean[a] += ka * err
        mean[b] -= kb * err
        var[a] *= 1.0 - ka * h
        var[b] *= 1.0 - kb * h
    state: dict[str, dict[str, list[float]]] = {}
    for (fam, team), m in mean.items():
        state.setdefault(fam, {})[team] = [round(m, 5), round(var[(fam, team)], 6), last[(fam, team)]]
    return out, state


def from_training_rows(save: bool = False) -> dict[Any, tuple[float, float]]:
    """Per-match pre-match ratings for every match in the training rows (optionally saving the final state)."""
    import pandas as pd

    cols = ["match_id", "date", "fam", "batting_team", "chasing_team", "label_batting_first_won"]
    df = pd.read_csv(ROWS_PATH, usecols=cols)
    first = df.sort_values(["date", "match_id"]).groupby("match_id", sort=False).first().reset_index()
    seq = ((r.match_id, date.fromisoformat(str(r.date)[:10]).toordinal(), r.fam, r.batting_team, r.chasing_team,
            int(r.label_batting_first_won)) for r in first.itertuples(index=False))
    per_match, state = run(seq)
    if save:
        STATE_PATH.write_text(json.dumps({"drift": DRIFT, "start_var": START_VAR, "teams": state}), encoding="utf-8")
        load_state.cache_clear()
    return per_match


def add_columns(df, per_match: dict[Any, tuple[float, float]]):
    """kal_diff / kal_unc columns for a frame of match states (by match_id)."""
    df["kal_diff"] = df["match_id"].map(lambda i: per_match.get(i, (0.0, 0.0))[0])
    df["kal_unc"] = df["match_id"].map(lambda i: per_match.get(i, (0.0, math.sqrt(2 * START_VAR)))[1])
    return df


@locked_cache
def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def team_rating(fam: str, team: str, day: int | None = None) -> tuple[float, float] | None:
    """(rating, uncertainty variance) for a team today (drift since its last game added); None if never seen."""
    entry = (load_state().get("teams", {}).get(fam) or {}).get(team)
    if not entry:
        return None
    m, v, last = entry
    return m, _drifted(v, (day or date.today().toordinal()) - int(last))


def gap(fam: str, bat: str, chase: str, day: int | None = None) -> tuple[float, float]:
    """(rating gap bat - chase, uncertainty) for a match today, the same way training measured it."""
    a = team_rating(fam, bat, day) or (0.0, START_VAR)
    b = team_rating(fam, chase, day) or (0.0, START_VAR)
    return a[0] - b[0], math.sqrt(a[1] + b[1])
