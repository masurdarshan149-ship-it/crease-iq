"""Live chase predictions (second innings), from data/ml/chase_model.joblib.

Uses the same team ratings, playing-XI records and venue par as the first-innings
model (via ml_model.build_features), plus the chase equation: target, runs,
wickets and balls.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import ml_model
from .ml_features import FORMAT_MAX_BALLS, add_chase_derived, app_lineup, app_lineup_known, crease_set, expected_set
from .models import MatchContext
from . import player_ratings
from .once import locked_cache

MODEL_PATH = Path(__file__).resolve().parents[1] / "data" / "ml" / "chase_model.joblib"
LABELS = {"ensemble_lr_lgbm": "LightGBM + logistic regression", "lightgbm": "LightGBM", "logistic_regression": "logistic regression"}


@locked_cache  # one shared load even when several requests ask at once (see once.py)
def _load() -> dict[str, Any] | None:
    if not MODEL_PATH.exists():
        return None
    try:
        import joblib

        return joblib.load(MODEL_PATH)
    except Exception:
        return None


def reload() -> None:
    _load.cache_clear()


def is_available() -> bool:
    return _load() is not None


def _probabilities(rows: list[dict[str, Any]]) -> tuple[list[float], list[float]]:
    import pandas as pd

    bundle = _load()
    X = pd.DataFrame(rows)
    full = X[bundle["features"]]
    gbm = bundle["model"].predict_proba(full)[:, 1]
    lr = bundle["logreg"].predict_proba(full)[:, 1]
    chosen = bundle.get("chosen", "ensemble_lr_lgbm")
    probs = gbm if chosen == "lightgbm" else lr if chosen == "logistic_regression" else (gbm + lr) / 2
    simple = bundle["simple"].predict_proba(X[bundle["simple_features"]])[:, 1]
    clip = lambda p: float(min(0.995, max(0.005, p)))  # noqa: E731
    return [clip(p) for p in probs], [clip(p) for p in simple]


def balls_from_overs(overs: float, max_balls: int) -> int:
    whole = int(overs)
    part = int(round((overs - whole) * 10))
    return max(0, min(max_balls, whole * 6 + min(part, 5)))


def _row(first: dict[str, Any], target: int, runs: int, wickets: int, balls: int) -> dict[str, Any]:
    row = {
        "is_odi": first["is_odi"], "is_club": first["is_club"], "is_ipl": first["is_ipl"], "target": target, "runs": runs, "wickets": wickets,
        "balls": balls, "venue_avg": first["venue_avg"], "elo_diff": first["elo_diff"],
        "kal_diff": first.get("kal_diff", 0.0), "kal_unc": first.get("kal_unc", 1.4142),
        **{c: first[c] for c in player_ratings.COLUMNS if c in first},
        **{k: first[k] for k in ("bat_xi_bat", "bat_xi_bowl_econ", "bat_xi_exp", "chase_xi_bat", "chase_xi_bowl_econ", "chase_xi_exp",
                                  "bat_xi_form_bat", "bat_xi_form_econ", "chase_xi_form_bat", "chase_xi_form_econ")},
    }
    fam = "odi" if first["is_odi"] else "t20"
    known = first.get("_chase_known") or []
    ordered = bool(first.get("_chase_ordered"))
    if known:
        lineup = app_lineup_known(first.get("_chase_stats") or [], [s for s, _ in known], wickets, fam, ordered)
    else:
        lineup = app_lineup(first.get("_chase_stats") or [], wickets, fam, ordered)
    row["chase_crease"], row["chase_next3"] = lineup["crease"], lineup["next3"]
    balls_known = [b for _, b in known if b is not None]
    row["chase_crease_set"] = (crease_set(balls_known) if len(balls_known) == 2
                               else expected_set(first.get("_set_table") or {}, fam, balls, wickets))
    row["home_diff"], row["venue_bf_rate"] = first.get("home_diff", 0), first.get("venue_bf_rate", 0.5)
    for k in ("bat_xi_death_sr", "bat_xi_death_econ", "chase_xi_death_sr", "chase_xi_death_econ"):
        row[k] = first.get(k)
    return add_chase_derived(row)


def scenarios(context: MatchContext, target: int, runs: int, wickets: int, overs: float) -> dict[str, Any]:
    """'What they need': the chasing side's win chance after the next ball / next over, for different outcomes.

    Decided outcomes are exact (target reached = 100%, all out or overs gone = 0%, level = 50%).
    """
    fam = context.format
    max_balls = FORMAT_MAX_BALLS.get(fam, 120)
    balls = balls_from_overs(overs, max_balls)
    if runs >= target or wickets >= 10 or balls >= max_balls:
        return {"live": False}
    built = ml_model.build_features(context)
    if built is None or not is_available():
        return {"live": False}
    first, _ = built
    over_balls = min(6, max_balls - balls)  # the next over (or what's left of the innings)

    def outcome(add_runs: int, add_wkts: int, add_balls: int) -> tuple[str, dict[str, Any] | float]:
        r, w, b = runs + add_runs, wickets + add_wkts, balls + add_balls
        if r >= target:
            return "fixed", 100.0
        if w >= 10 or b >= max_balls:
            return "fixed", 50.0 if r == target - 1 else 0.0
        return "model", _row(first, target, r, w, b)

    cases: list[tuple[str, Any]] = []
    next_ball = [("dot", 0, 0), ("1 run", 1, 0), ("4", 4, 0), ("6", 6, 0), ("wicket", 0, 1)]
    for label, add_r, add_w in next_ball:
        cases.append((f"ball:{label}", outcome(add_r, add_w, 1)))
    grid_runs = list(range(0, 37, 2 if fam == "t20" else 2))
    for w in (0, 1, 2):
        for r in grid_runs:
            cases.append((f"over:{w}:{r}", outcome(r, w, over_balls)))
    rows = [c[1][1] for c in cases if c[1][0] == "model"]
    probs = iter(_probabilities(rows)[0] if rows else [])
    values: dict[str, float] = {}
    for key, (kind, val) in cases:
        values[key] = round(val if kind == "fixed" else next(probs) * 100, 1)

    now = predict(context, target, runs, wickets, overs)["chase_pct"]
    no_wkt = [(r, values[f"over:0:{r}"]) for r in grid_runs]
    reach_50 = next((r for r, p in no_wkt if p >= 50), None)
    return {
        "live": True,
        "now": now,
        "over_balls": over_balls,
        "next_ball": [{"label": label, "pct": values[f"ball:{label}"]} for label, _, _ in next_ball],
        "grid_runs": grid_runs,
        "grid": {str(w): [values[f"over:{w}:{r}"] for r in grid_runs] for w in (0, 1, 2)},
        "runs_for_50": reach_50,                      # fewest runs (no wicket) next over to be at 50%+
        "runs_needed": target - runs,
    }


def predict(context: MatchContext, target: int, runs: int, wickets: int, overs: float) -> dict[str, Any]:
    """Chasing side's win probability plus the chase equation and what drives it."""
    fam = context.format
    max_balls = FORMAT_MAX_BALLS.get(fam, 120)
    balls = balls_from_overs(overs, max_balls)
    runs_needed = target - runs
    balls_left = max_balls - balls
    equation = {
        "target": target, "runs": runs, "wickets": wickets, "balls": balls, "balls_left": balls_left,
        "runs_needed": max(0, runs_needed), "wickets_in_hand": 10 - wickets,
        "required_rate": round(runs_needed * 6 / balls_left, 2) if balls_left and runs_needed > 0 else None,
        "current_rate": round(runs * 6 / balls, 2) if balls else None,
        "overs_text": f"{balls // 6}.{balls % 6}",
    }
    # ---- the chase is already decided ----
    if runs_needed <= 0:
        return {"status": "won", "chase_pct": 100.0, "equation": equation}
    if wickets >= 10 or balls_left <= 0:
        status = "tied" if runs_needed == 1 else "lost"
        return {"status": status, "chase_pct": 50.0 if status == "tied" else 0.0, "equation": equation}

    built = ml_model.build_features(context)
    if built is None or not is_available():
        raise RuntimeError("The live chase model isn't available. Go to Data → Retrain model.")
    first, meta = built
    row = _row(first, target, runs, wickets, balls)
    neutral_elo = add_chase_derived(dict(row, elo_diff=0.0, kal_diff=0.0))
    neutral_xi = dict(row)
    for a, b in (("bat_xi_bat", "chase_xi_bat"), ("bat_xi_bowl_econ", "chase_xi_bowl_econ"), ("bat_xi_exp", "chase_xi_exp"), *player_ratings.PAIRS):
        if a in row and b in row:
            neutral_xi[a] = neutral_xi[b] = (row[a] + row[b]) / 2
    probs, simple = _probabilities([row, neutral_elo, neutral_xi])
    base = probs[0]
    bundle = _load()
    overall = (bundle.get("test_overall") or {}).get(bundle.get("chosen"), {})
    return {
        "status": "live",
        "chase_pct": round(base * 100, 1),
        "equation": equation,
        "simple_pct": round(simple[0] * 100, 1),
        "factors": {
            "team_ratings": round((base - probs[1]) * 100, 1),   # + means it helps the chasing side
            "playing_xi": round((base - probs[2]) * 100, 1),
        },
        "bat_elo": round(meta["bat_elo"]) if meta.get("bat_elo") is not None else None,
        "chase_elo": round(meta["chase_elo"]) if meta.get("chase_elo") is not None else None,
        "players_found": {"batting": [meta["bat_matched"], meta["bat_total"]], "chasing": [meta["chase_matched"], meta["chase_total"]]},
        "par": round(first["venue_avg"]),
        "model_label": LABELS.get(bundle.get("chosen"), bundle.get("chosen")),
        "test_accuracy": overall.get("accuracy"),
    }
