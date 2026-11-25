"""Team head-to-head and recent form, from the match log in data/ml/feature_store.json."""

from __future__ import annotations

from typing import Any

from . import ml_model


def _log() -> list[dict[str, Any]]:
    loaded = ml_model.load_store()
    if not loaded:
        return []
    store = loaded["store"]
    fields = store.get("match_log_fields") or []
    cache = loaded.setdefault("_match_log", None)
    if cache is None:
        cache = [dict(zip(fields, r)) for r in store.get("match_log", [])]
        loaded["_match_log"] = cache
    return cache


def _score_text(innings: list) -> list[dict[str, Any]]:
    return [{"team": t, "runs": r, "wickets": w, "text": f"{r}/{w}" if w < 10 else f"{r}"} for t, r, w in innings]


def _result_for(match: dict[str, Any], team: str) -> str:
    if not match["winner"]:
        return "T" if "tie" in (match["margin"] or "").lower() else "NR"
    return "W" if match["winner"] == team else "L"


def head_to_head(team_a: str, team_b: str, fam: str, venue_key: str | None = None, last: int = 10) -> dict[str, Any]:
    a, b = ml_model._team_key(team_a), ml_model._team_key(team_b)
    meetings = [m for m in _log() if {m["team1"], m["team2"]} == {a, b} and m["format"] == fam]
    decided = [m for m in meetings if m["winner"]]
    bat_first_won = sum(1 for m in decided if m["innings"] and m["innings"][0][0] == m["winner"])
    at_ground = [m for m in meetings if venue_key and m["venue_key"] == venue_key]
    recent = list(reversed(meetings))[:last]
    return {
        "teams": [a, b],
        "format": fam,
        "played": len(meetings),
        "wins": {a: sum(1 for m in meetings if m["winner"] == a), b: sum(1 for m in meetings if m["winner"] == b)},
        "no_result": len(meetings) - len(decided),
        "bat_first_won": bat_first_won,
        "decided": len(decided),
        "first_met": meetings[0]["date"] if meetings else None,
        "at_ground": {"played": len(at_ground), a: sum(1 for m in at_ground if m["winner"] == a),
                      b: sum(1 for m in at_ground if m["winner"] == b)},
        "last_n": {a: sum(1 for m in recent if m["winner"] == a), b: sum(1 for m in recent if m["winner"] == b), "n": len(recent)},
        "meetings": [{
            "date": m["date"], "venue": m["venue"], "city": m["city"], "winner": m["winner"], "margin": m["margin"],
            "rain_rule": m["rain_rule"], "innings": _score_text(m["innings"]),
        } for m in recent],
    }


def form(team: str, fam: str, last: int = 10) -> dict[str, Any]:
    t = ml_model._team_key(team)
    games = [m for m in _log() if t in (m["team1"], m["team2"]) and m["format"] == fam]
    recent = list(reversed(games))[:last]
    rows = [{
        "date": m["date"], "opponent": m["team2"] if m["team1"] == t else m["team1"], "result": _result_for(m, t),
        "margin": m["margin"], "venue": m["venue"], "innings": _score_text(m["innings"]),
    } for m in recent]
    wins = sum(1 for r in rows if r["result"] == "W")
    decided = sum(1 for r in rows if r["result"] in ("W", "L"))
    return {"team": t, "games": rows, "wins": wins, "decided": decided,
            "win_pct": round(wins * 100 / decided) if decided else None}
