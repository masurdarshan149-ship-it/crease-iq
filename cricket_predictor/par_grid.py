"""Par by wickets: for every point in the innings and every number of wickets down, the score at which the model
says the match is exactly 50/50.

First innings: the batting side's total-so-far that makes it an even game ("5 overs, 1 down: par 50; 2 down: 60;
3 down: 70"). Live chase: the score the chasing side needs by then to be on track for the target ("chasing 200,
after 15 overs with 7 down they need about 180").

It is the same model the app predicts with, asked "what if" for a grid of scores (nothing is saved). Everything
except the score, wickets and balls (teams, XIs, venue, your par / pitch) stays as you set it, so the par is for
these two teams at this ground. The search uses the fact that more runs never lower the batting side's chance.
"""

from __future__ import annotations

import math
import time
from typing import Any

from . import chase_model, ml_model
from .ml_features import FORMAT_MAX_BALLS, add_derived, app_lineup, app_lineup_known, expected_set

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _dew(prob_chase: float, shift: float) -> float:
    """Same log-odds move the app applies for your dew call (webapp._dew_shift)."""
    if not shift:
        return prob_chase
    p = min(max(prob_chase, 0.001), 0.999)
    return 1 / (1 + math.exp(-(math.log(p / (1 - p)) + shift)))


PAIRS = [("bat_xi_bat", "chase_xi_bat"), ("bat_xi_bowl_econ", "chase_xi_bowl_econ"), ("bat_xi_exp", "chase_xi_exp"),
         ("bat_xi_form_bat", "chase_xi_form_bat"), ("bat_xi_form_econ", "chase_xi_form_econ"),
         ("bat_xi_death_sr", "chase_xi_death_sr"), ("bat_xi_death_econ", "chase_xi_death_econ"),
         ("prb_sr", "prc_sr"), ("prb_bpd", "prc_bpd"), ("prb_ec", "prc_ec"), ("prb_wk", "prc_wk")]  # player ratings


def _even(base: dict[str, Any]) -> dict[str, Any]:
    """'Even teams': same rating and the same strength on both sides (the average of the two), no home edge."""
    row = dict(base)
    row["elo_diff"] = row["kal_diff"] = 0.0
    for a, b in PAIRS:
        if row.get(a) is not None and row.get(b) is not None:
            row[a] = row[b] = (float(row[a]) + float(row[b])) / 2
    row["home_diff"], row["venue_bf_rate"] = 0, 0.5
    if row.get("_chase_stats") is not None and row.get("_bat_stats") is not None:
        row["_chase_stats"] = row["_bat_stats"]  # who's in / next: the same depth for both sides
        row["_chase_ordered"] = row.get("_bat_ordered", False)
    return row


def _checkpoints(fam: str, max_balls: int) -> list[int]:
    step = 6 if fam == "t20" else 30  # every over in T20, every 5 overs in ODIs
    return list(range(step, max_balls, step))


def _first_variant(base: dict[str, Any], runs: int, wickets: int, balls: int, max_balls: int, fam: str) -> dict[str, Any]:
    row = {k: v for k, v in base.items() if not k.startswith("_")}
    row.update({"runs": runs, "wickets": wickets, "balls_left_frac": round((max_balls - balls) / max_balls, 4),
                "run_rate": round(runs * 6 / balls, 3) if balls else 0.0})
    return add_derived(row)


def _lineup(base: dict[str, Any], wickets: int, balls: int, fam: str) -> dict[str, float]:
    stats = base.get("_bat_stats") or []
    known = base.get("_bat_known") or []
    ordered = bool(base.get("_bat_ordered"))
    lineup = (app_lineup_known(stats, [s for s, _ in known], wickets, fam, ordered) if known
              else app_lineup(stats, wickets, fam, ordered))
    return {"bat_crease": lineup["crease"], "bat_next3": lineup["next3"],
            "bat_crease_set": expected_set(base.get("_set_table") or {}, fam, balls, wickets)}


def _crossing(runs_list: list[int], probs: list[float], want_high: bool) -> float | None:
    """Score where the chance crosses 50% (linear between grid points). want_high: chance rises with runs."""
    vals = [p if want_high else 1 - p for p in probs]
    if vals[0] >= 0.5:
        return float(runs_list[0])
    for i in range(1, len(vals)):
        if vals[i] >= 0.5:
            r0, r1, p0, p1 = runs_list[i - 1], runs_list[i], vals[i - 1], vals[i]
            return r0 + (r1 - r0) * ((0.5 - p0) / (p1 - p0) if p1 != p0 else 1.0)
    return None


def first_innings(context: Any, wickets_shown: int = 9, dew: float = 0.0, even: bool = False) -> dict[str, Any] | None:
    built = ml_model.build_features(context)
    if built is None:
        return None
    base, _ = built
    if even:
        base = _even(base)
    fam = context.format
    max_balls = FORMAT_MAX_BALLS[fam]
    par = float(base["venue_avg"])
    step = 3 if fam == "t20" else 5
    cells, rows = [], []
    for balls in _checkpoints(fam, max_balls) + [max_balls]:
        top = int(min(par * 1.9 + 40, par * 1.9 * balls / max_balls + 60))
        runs_list = list(range(0, top + step, step))
        for w in range(0, wickets_shown + 1):
            extra = _lineup(base, w, balls, fam)
            start = len(rows)
            for r in runs_list:
                row = _first_variant(base, r, w, balls, max_balls, fam)
                row.update(extra)
                rows.append(row)
            cells.append((balls, w, runs_list, start))
    probs = [1 - _dew(1 - p, dew) for p in ml_model.predict_probability(rows)]
    grid: dict[str, dict[str, int | None]] = {}
    for balls, w, runs_list, start in cells:
        x = _crossing(runs_list, probs[start:start + len(runs_list)], want_high=True)
        grid.setdefault(str(balls), {})[str(w)] = round(x) if x is not None else None
    return {"kind": "first", "even": even, "format": fam, "max_balls": max_balls, "venue_par": round(par), "grid": grid}


def chase(context: Any, target: int, wickets_shown: int = 9, dew: float = 0.0, even: bool = False) -> dict[str, Any] | None:
    if not chase_model.is_available():
        return None
    built = ml_model.build_features(context)
    if built is None:
        return None
    first, _ = built
    if even:
        first = _even(first)
    fam = context.format
    max_balls = FORMAT_MAX_BALLS[fam]
    step = 3 if fam == "t20" else 5
    cells, rows = [], []
    for balls in _checkpoints(fam, max_balls):
        runs_list = list(range(0, target, step))
        for w in range(0, wickets_shown + 1):
            start = len(rows)
            for r in runs_list:
                rows.append(chase_model._row(first, target, r, w, balls))
            cells.append((balls, w, runs_list, start))
    probs = chase_model._probabilities(rows)[0] if rows else []
    grid: dict[str, dict[str, int | None]] = {}
    for balls, w, runs_list, start in cells:
        shift = dew * max(0.0, 1 - balls / max_balls) ** 0.5  # fades through the chase, as in the app
        x = _crossing(runs_list, [_dew(p, shift) for p in probs[start:start + len(runs_list)]], want_high=True)
        grid.setdefault(str(balls), {})[str(w)] = round(x) if x is not None else None
    return {"kind": "chase", "even": even, "format": fam, "max_balls": max_balls, "target": target, "grid": grid}


_INFLIGHT: dict[str, Any] = {}
_LOCK = __import__("threading").Lock()


def is_fresh(key: str) -> bool:
    hit = _CACHE.get(key)
    return bool(hit and time.time() - hit[0] < 600)


def cached(key: str, make) -> dict[str, Any] | None:
    """Cached for 10 minutes. If the same grid is already being worked out (e.g. the background warm-up started
    when you pressed Predict), wait for it instead of doing the work twice."""
    import threading

    if is_fresh(key):
        return _CACHE[key][1]
    with _LOCK:
        ev = _INFLIGHT.get(key)
        mine = ev is None
        if mine:
            ev = _INFLIGHT[key] = threading.Event()
    if not mine:
        ev.wait(timeout=30)
        if is_fresh(key):
            return _CACHE[key][1]
    try:
        out = make()
        if out is not None:
            if len(_CACHE) > 40:
                _CACHE.clear()
            _CACHE[key] = (time.time(), out)
        return out
    finally:
        if mine:
            with _LOCK:
                _INFLIGHT.pop(key, None)
            ev.set()
