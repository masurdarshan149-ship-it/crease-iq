"""Prediction settings you can tune from the app (Data tab → Tuning). Saved in data/settings.json.

pitch    % change to the venue par for each pitch read                 (flat +8, green −6, dry −7, slow −9)
dew      points for the chasing side in a 50/50 match for each call    (light +3, heavy +6, slowing −4)
suggest  Suggested XI: how much recent form counts vs career (%), and the most a matchup record can move a rating (%)
"""

from __future__ import annotations

import json
import math
import threading
from pathlib import Path
from typing import Any

PATH = Path(__file__).resolve().parents[1] / "data" / "settings.json"
DEFAULTS: dict[str, dict[str, float]] = {
    "pitch": {"flat": 8.0, "green": -6.0, "dry": -7.0, "slow": -9.0},
    "dew": {"light": 3.0, "heavy": 6.0, "slowing": -4.0},
    "suggest": {"form_weight": 50.0, "matchup_weight": 40.0},
}
LIMITS = {"pitch": (-25.0, 25.0), "dew": (-15.0, 15.0), "suggest": (0.0, 100.0)}
_lock = threading.Lock()
_cache: dict[str, Any] = {"mtime": None, "value": None}


def load() -> dict[str, dict[str, float]]:
    """Current settings (defaults filled in for anything not saved)."""
    mtime = PATH.stat().st_mtime if PATH.exists() else None
    with _lock:
        if _cache["value"] is not None and _cache["mtime"] == mtime:
            return _cache["value"]
        saved: dict[str, Any] = {}
        if PATH.exists():
            try:
                saved = json.loads(PATH.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                saved = {}
        out = {group: {k: float((saved.get(group) or {}).get(k, v)) for k, v in vals.items()} for group, vals in DEFAULTS.items()}
        _cache.update(mtime=mtime, value=out)
        return out


def save(changes: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Merge and clamp changes; {"reset": "pitch"} / {"reset": "all"} restore defaults."""
    current = load()
    reset = changes.get("reset") if isinstance(changes, dict) else None
    if reset == "all":
        current = {g: dict(v) for g, v in DEFAULTS.items()}
    elif reset in DEFAULTS:
        current[reset] = dict(DEFAULTS[reset])
    for group, vals in (changes or {}).items():
        if group not in DEFAULTS or not isinstance(vals, dict):
            continue
        lo, hi = LIMITS[group]
        for k, v in vals.items():
            if k in DEFAULTS[group]:
                try:
                    current[group][k] = round(max(lo, min(hi, float(v))), 1)
                except (TypeError, ValueError):
                    pass
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(current, indent=1), encoding="utf-8")
    with _lock:
        _cache.update(mtime=None, value=None)
    return {**load(), "defaults": DEFAULTS}


def pitch_multiplier(key: str) -> float:
    if key == "balanced":
        return 1.0
    return 1.0 + load()["pitch"].get(key, 0.0) / 100.0


def dew_shift(key: str) -> float:
    """Points at 50/50 -> a shift in the chasing side's log-odds (so the effect shrinks when one side is far ahead)."""
    pts = load()["dew"].get(key, 0.0) if key != "none" else 0.0
    p = min(0.99, max(0.01, 0.5 + pts / 100.0))
    return math.log(p / (1 - p))
