"""Head-to-head (batter v bowler) and recent form, from data/ml/player_insights.json.

Built by scripts/build_training_data.py from every ball in the Cricsheet archives.
T20 figures include T20 internationals, the IPL and other T20 leagues (BBL, PSL, CPL, SA20, Blast, Syed Mushtaq Ali, ...).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import ml_model
from .once import locked_cache

PATH = Path(__file__).resolve().parents[1] / "data" / "ml" / "player_insights.json"
FAMS = ("t20", "odi")


@locked_cache  # one shared load even when several requests ask at once (see once.py)
def _load() -> dict[str, Any] | None:
    if not PATH.exists():
        return None
    return json.loads(PATH.read_text(encoding="utf-8"))


def reload() -> None:
    _load.cache_clear()


def _pid(name: str, team: str | None) -> str | None:
    for fam in FAMS:
        pid = ml_model.resolve_id(name, fam, team)
        if pid:
            return pid
    return None


def _pair_stats(raw: list | None) -> dict[str, Any] | None:
    if not raw:
        return None
    balls, runs, outs, fours, sixes, dots, matches, last = raw
    return {
        "balls": balls, "runs": runs, "outs": outs, "fours": fours, "sixes": sixes, "dots": dots, "matches": matches,
        "last": last,
        "strike_rate": round(runs * 100 / balls, 1) if balls else None,
        "average": round(runs / outs, 1) if outs else None,
        "dot_pct": round(dots * 100 / balls) if balls else None,
    }


def _combine(parts: list[dict[str, Any] | None]) -> dict[str, Any] | None:
    parts = [p for p in parts if p]
    if not parts:
        return None
    raw = [sum(p[k] for p in parts) for k in ("balls", "runs", "outs", "fours", "sixes", "dots", "matches")]
    return _pair_stats(raw + [max(p["last"] for p in parts)])


def head_to_head(batter: str, batter_team: str | None, bowler: str, bowler_team: str | None) -> dict[str, Any]:
    data = _load()
    if not data:
        return {"available": False}
    bat_id, bowl_id = _pid(batter, batter_team), _pid(bowler, bowler_team)
    out: dict[str, Any] = {"available": True, "batter": batter, "bowler": bowler,
                           "batter_found": bat_id is not None, "bowler_found": bowl_id is not None}
    if not bat_id or not bowl_id:
        return {**out, "t20": None, "odi": None, "all": None}
    per = {fam: _pair_stats(data["pairs"].get(fam, {}).get(f"{bat_id}|{bowl_id}")) for fam in FAMS}
    for fam in FAMS:
        if per[fam]:
            per[fam]["edge"] = edge(per[fam], fam)
    return {**out, **per, "all": _combine(list(per.values()))}


def edge(stats: dict[str, Any], fam: str) -> str:
    """Who has had the better of it: 'batter', 'bowler' or 'even'."""
    fast, slow = (150, 110) if fam == "t20" else (95, 70)
    sr = stats["strike_rate"] or 0
    avg = stats["average"]
    if sr >= fast and (stats["outs"] == 0 or (avg or 0) >= 30):
        return "batter"
    if (stats["outs"] >= 2 and ((avg or 99) < 20 or sr < slow)) or (stats["outs"] >= 1 and sr < slow and stats["balls"] >= 12):
        return "bowler"
    return "even"


def warm_up() -> None:
    """Load the data in the background so the first click is instant."""
    import threading

    threading.Thread(target=lambda: (_load(), ml_model._load()), daemon=True, name="insights-warmup").start()


def key_battles(batters: list[str], batting_team: str, bowlers: list[str], bowling_team: str, fam: str, min_balls: int = 6) -> list[dict[str, Any]]:
    """Every pairing between one side's batters and the other side's bowlers that has history."""
    data = _load()
    if not data:
        return []
    table = data["pairs"].get(fam, {})
    bat_ids = [(n, _pid(n, batting_team)) for n in batters]
    bowl_ids = [(n, _pid(n, bowling_team)) for n in bowlers]
    rows = []
    for bat_name, bat_id in bat_ids:
        if not bat_id:
            continue
        for bowl_name, bowl_id in bowl_ids:
            stats = _pair_stats(table.get(f"{bat_id}|{bowl_id}")) if bowl_id else None
            if stats and stats["balls"] >= min_balls:
                rows.append({"batter": bat_name, "bowler": bowl_name, "edge": edge(stats, fam), **stats})
    rows.sort(key=lambda r: -r["balls"])
    return rows


PHASES = ("pp", "mid", "death")
MIN_BAT_BALLS = 30   # below this a phase number is shown but flagged as a small sample
MIN_BOWL_BALLS = 36


def phase_rows(names: list[str], team: str | None, fam: str) -> list[dict[str, Any]]:
    """Strike rate / average by phase for batting, economy / wickets by phase for bowling."""
    data = _load() or {}
    fields = data.get("phase_fields", [])
    table = data.get("phase_stats", {}).get(fam, {})
    rows = []
    for name in names:
        pid = _pid(name, team)
        v = dict(zip(fields, table.get(pid, []))) if pid else {}
        bat, bowl = {}, {}
        for ph in PHASES:
            b = v.get(f"bat_{ph}_balls", 0)
            r = v.get(f"bat_{ph}_runs", 0)
            o = v.get(f"bat_{ph}_outs", 0)
            bat[ph] = {"balls": b, "runs": r, "outs": o, "sr": round(r * 100 / b, 1) if b else None,
                       "avg": round(r / o, 1) if o else None, "small": b < MIN_BAT_BALLS}
            bb = v.get(f"bowl_{ph}_balls", 0)
            rc = v.get(f"bowl_{ph}_runs", 0)
            wk = v.get(f"bowl_{ph}_wickets", 0)
            bowl[ph] = {"balls": bb, "runs": rc, "wickets": wk, "econ": round(rc * 6 / bb, 2) if bb else None,
                        "small": bb < MIN_BOWL_BALLS}
        rows.append({"name": name, "found": bool(v), "bat": bat, "bowl": bowl,
                     "bats": any(bat[p]["balls"] for p in PHASES), "bowls": any(bowl[p]["balls"] for p in PHASES)})
    return rows


def phase_callouts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Best powerplay / death hitter (strike rate) and best powerplay / death bowler (economy), with enough balls."""
    out = {}
    for ph in ("pp", "death"):
        hitters = [r for r in rows if r["bat"][ph]["sr"] is not None and not r["bat"][ph]["small"]]
        bowlers = [r for r in rows if r["bowl"][ph]["econ"] is not None and not r["bowl"][ph]["small"]]
        if hitters:
            h = max(hitters, key=lambda r: r["bat"][ph]["sr"])
            out[f"{ph}_hitter"] = {"name": h["name"], "sr": h["bat"][ph]["sr"], "balls": h["bat"][ph]["balls"]}
        if bowlers:
            b = min(bowlers, key=lambda r: r["bowl"][ph]["econ"])
            out[f"{ph}_bowler"] = {"name": b["name"], "econ": b["bowl"][ph]["econ"], "wickets": b["bowl"][ph]["wickets"], "balls": b["bowl"][ph]["balls"]}
    return out


def form(name: str, team: str | None) -> dict[str, Any]:
    """Last 10 innings and bowling spells per format, newest first, plus simple summaries."""
    data = _load()
    pid = _pid(name, team)
    if not data or not pid:
        return {"name": name, "found": False}
    entry = data["form"].get(pid, {})
    result: dict[str, Any] = {"name": name, "found": True}
    for fam in FAMS:
        bat = [dict(zip(data["bat_fields"], row)) for row in entry.get(fam, {}).get("bat", [])][::-1]
        bowl = [dict(zip(data["bowl_fields"], row)) for row in entry.get(fam, {}).get("bowl", [])][::-1]
        runs = sum(b["runs"] for b in bat)
        balls = sum(b["balls"] for b in bat)
        outs = sum(b["out"] for b in bat)
        w_balls = sum(b["balls"] for b in bowl)
        w_runs = sum(b["runs"] for b in bowl)
        wkts = sum(b["wickets"] for b in bowl)
        result[fam] = {
            "batting": bat,
            "bowling": bowl,
            "bat_summary": {"innings": len(bat), "runs": runs, "average": round(runs / outs, 1) if outs else None,
                            "strike_rate": round(runs * 100 / balls, 1) if balls else None,
                            "fifties": sum(1 for b in bat if b["runs"] >= 50)} if bat else None,
            "bowl_summary": {"spells": len(bowl), "wickets": wkts, "economy": round(w_runs * 6 / w_balls, 2) if w_balls else None,
                             "average": round(w_runs / wkts, 1) if wkts else None} if bowl else None,
        }
    return result
