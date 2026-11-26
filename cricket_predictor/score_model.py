"""Projected first-innings total (with a likely range), from data/ml/score_model.joblib.

Uses the same match-state, venue-par, team and XI features as the win model
(via ml_model.build_features). The 10-90% band is widened by the factor that
made it cover 80% of the 2024 tuning season (see scripts/train_score_model.py).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import ml_model
from .models import MatchContext
from .once import locked_cache

MODEL_PATH = Path(__file__).resolve().parents[1] / "data" / "ml" / "score_model.joblib"


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


def project(context: MatchContext) -> dict[str, Any] | None:
    """{"mid", "low", "high", "current_rate", "par"} or None if the innings is over / no model."""
    bundle = _load()
    built = ml_model.build_features(context)
    if not bundle or not built:
        return None
    row, meta = built
    max_balls = meta["max_balls"]
    balls = meta["balls"]
    if balls >= max_balls or row["wickets"] >= 10:
        return None  # innings complete: nothing to project
    import pandas as pd

    X = pd.DataFrame([row])[bundle["features"]]
    raw = {k: max(0.0, float(m.predict(X)[0])) for k, m in bundle["models"].items()}
    mid = raw["mid"]
    lo, hi = min(raw["low"], mid), max(raw["high"], mid)
    widen = bundle.get("widen", 1.0)
    lo = max(0.0, mid - widen * (mid - lo))
    hi = mid + widen * (hi - mid)
    runs = row["runs"]
    left = max_balls - balls
    crr_total = runs + (runs / balls * left if balls else row["venue_avg"] * left / max_balls)
    # how far off the projection typically is at this stage of the innings (from the unseen test years)
    over = balls // 6
    if row["is_odi"]:
        stage = "ODI · overs 1–10" if over <= 10 else "ODI · overs 11–40" if over <= 40 else "ODI · overs 41–49"
    else:
        stage = "T20 · before the match" if balls == 0 else "T20 · overs 1–6" if over <= 6 else "T20 · overs 7–15" if over <= 15 else "T20 · overs 16–19"
    test = bundle.get("test") or {}
    acc = (test.get(stage) or test.get("All ODI states" if row["is_odi"] else "All T20 states") or {}).get("model", {})
    return {
        "mid": round(runs + mid), "low": round(runs + lo), "high": round(runs + hi),
        "current_rate": round(crr_total), "par": round(row["venue_avg"]),
        "balls_left": left, "typical_error": acc.get("mae"), "coverage": acc.get("coverage_80"), "stage": stage,
    }
