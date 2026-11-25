"""Suggested XI: the strongest balanced 11 from a squad, with a reason for every pick.

Each player gets two numbers, built from the same records the model and the Form tab use:
  batting  = half career batting index, half recent form (last 10 innings), nudged by how the player has
             done against the opposition's ticked bowlers (more balls faced against them = more weight)
  bowling  = runs per over conceded minus the value of wickets taken (a wicket ~ 10 runs in T20, 20 in ODIs);
             half career, half the last 10 spells, nudged by the record against the opposition's ticked batters
Players with little cricket rank a little below average (fading as they play more).
Numbers are shrunk toward average, so a player with little cricket is treated as average, not as a star.

Shape of the XI: 1 wicket-keeper, the 5 best bowling options (bowlers or all-rounders), then the
5 best remaining batters. IPL sides may pick at most 4 overseas players. Players not picked in the
recent window are only used if the recent squad is short.

This is a simple, explainable rule, not a trained model; the app shows the model's pre-match win
chance for the current XI and for the suggestion so the two can be compared.
"""

from __future__ import annotations

from typing import Any

from . import ml_model
from .ml_features import BOWL_PRIOR, normalize_name, PRIOR_BALLS_BOWLED, PRIOR_BALLS_FACED, player_bat_index, player_bowl_econ

FORM_WEIGHT = 0.5         # share of recent form vs career (default; the Tuning panel can change it)
MATCHUP_WEIGHT = 0.4      # most a matchup record can move the number (default)


def _weights() -> tuple[float, float]:
    from . import settings
    s = settings.load()["suggest"]
    return s["form_weight"] / 100.0, s["matchup_weight"] / 100.0
MATCHUP_BALLS = 60        # balls of matchup history for half of that weight
MIN_MATCHUP_BALLS = 12
BOWLING_OPTIONS = 5
OVERSEAS_LIMIT = 4
HOME_COUNTRY = "India"    # the IPL's home side for the overseas rule
BOWL_ROLES = {"bowler", "all_rounder"}
WICKET_RUNS = {"t20": 10.0, "odi": 20.0}        # a wicket is worth about this many runs saved
WICKETS_PER_BALL = {"t20": 1 / 20, "odi": 1 / 36}  # an average bowler: a wicket every 20 / 36 balls
# players with little cricket rank a bit below average (selectors pick proven players), fading with experience
UNPROVEN_BAT = 4.0        # batting-index points
UNPROVEN_BOWL = 0.8       # runs per over


def bowl_cost(balls: float, runs: float, wickets: float, fam: str) -> float:
    """Runs per over conceded, minus the value of the wickets taken (lower = better), shrunk toward average."""
    n = PRIOR_BALLS_BOWLED
    runs_s = runs + BOWL_PRIOR[fam]["econ"] / 6 * n
    wkts_s = wickets + WICKETS_PER_BALL[fam] * n
    return (runs_s - WICKET_RUNS[fam] * wkts_s) * 6 / (balls + n)


def _form_rows(pid: str | None, fam: str) -> tuple[list, list]:
    from . import insights

    entry = ((insights._load() or {}).get("form", {}).get(pid, {}) or {}).get(fam, {}) if pid else {}
    return entry.get("bat") or [], entry.get("bowl") or []


def _pairs(fam: str) -> dict[str, list]:
    from . import insights

    return (insights._load() or {}).get("pairs", {}).get(fam, {})


def foreign_players(national_squads: dict[str, list[str]], loaded: dict[str, Any]) -> set[str]:
    """Ids and folded names of players in another country's national squad (covers countries with no
    matches in the data, e.g. Afghanistan, whose players would otherwise look Indian)."""
    out: set[str] = set()
    for country, names in national_squads.items():
        if country == HOME_COUNTRY:
            continue
        for name in names:
            out.add(normalize_name(name))
            pid = ml_model._resolve_id(name, "t20", loaded, country)
            if pid:
                out.add(pid)
    return out


def _is_overseas(pid: str | None, store: dict[str, Any], name: str = "", foreign: set[str] | None = None) -> bool:
    """Has played for (or is in the squad of) a national team other than India (IPL overseas rule)."""
    if foreign and (normalize_name(name) in foreign or (pid and pid in foreign)):
        return True
    if not pid:
        return False
    types = store.get("team_types", {})
    nations = [t for t in store.get("player_teams", {}).get(pid, []) if types.get(t) == "international"]
    return bool(nations) and HOME_COUNTRY not in nations


def _rate(runs: float, balls: float) -> float | None:
    return round(runs * 100 / balls, 1) if balls else None


def score_player(name: str, team: str, role: str, fam: str, opp_bat_ids: list[str], opp_bowl_ids: list[str],
                 loaded: dict[str, Any], foreign: set[str] | None = None) -> dict[str, Any]:
    pid = ml_model._resolve_id(name, fam, loaded, team)
    career = loaded["store"]["players"].get(fam, {}).get(pid) if pid else None
    bat_rows, bowl_rows = _form_rows(pid, fam)
    form_bat = {"runs": sum(r[3] for r in bat_rows), "balls": sum(r[4] for r in bat_rows), "outs": sum(r[5] for r in bat_rows)}
    form_bowl = {"balls_bowled": sum(r[3] for r in bowl_rows), "runs_conceded": sum(r[4] for r in bowl_rows)}
    form_wkts = sum(r[5] for r in bowl_rows)

    c = career or {}
    FORM_W, MATCH_W = _weights()
    bat = (1 - FORM_W) * player_bat_index(career, fam) + FORM_W * player_bat_index(form_bat, fam)
    econ = (1 - FORM_W) * player_bowl_econ(career, fam) + FORM_W * player_bowl_econ(form_bowl, fam)
    cost = ((1 - FORM_W) * bowl_cost(c.get("balls_bowled", 0), c.get("runs_conceded", 0), c.get("wickets", 0), fam)
            + FORM_W * bowl_cost(form_bowl["balls_bowled"], form_bowl["runs_conceded"], form_wkts, fam))

    pairs = _pairs(fam)
    vs_bowl = [pairs.get(f"{pid}|{b}") for b in opp_bowl_ids] if pid else []
    vb = [sum(p[i] for p in vs_bowl if p) for i in range(3)]  # balls, runs, outs v their bowlers
    if vb[0] >= MIN_MATCHUP_BALLS:
        w = MATCH_W * vb[0] / (vb[0] + MATCHUP_BALLS)
        bat = (1 - w) * bat + w * player_bat_index({"balls": vb[0], "runs": vb[1], "outs": vb[2]}, fam)
    vs_bat = [pairs.get(f"{b}|{pid}") for b in opp_bat_ids] if pid else []
    vw = [sum(p[i] for p in vs_bat if p) for i in range(3)]  # balls, runs, dismissals v their batters
    if vw[0] >= MIN_MATCHUP_BALLS:
        w = MATCH_W * vw[0] / (vw[0] + MATCHUP_BALLS)
        econ = (1 - w) * econ + w * player_bowl_econ({"balls_bowled": vw[0], "runs_conceded": vw[1]}, fam)
        cost = (1 - w) * cost + w * bowl_cost(vw[0], vw[1], vw[2], fam)
    bat_rank = bat - UNPROVEN_BAT * PRIOR_BALLS_FACED / (PRIOR_BALLS_FACED + c.get("balls", 0))
    bowl_rank = cost + UNPROVEN_BOWL * PRIOR_BALLS_BOWLED / (PRIOR_BALLS_BOWLED + c.get("balls_bowled", 0))

    per_match_balls = (career or {}).get("balls_bowled", 0) / max(1, (career or {}).get("matches", 0) or 1)
    bowls = role in BOWL_ROLES or per_match_balls >= 9
    return {
        "name": name, "role": role, "pid": pid, "found": career is not None,
        "bat": round(bat, 2), "econ": round(econ, 2), "bowls": bowls,
        "bat_rank": round(bat_rank, 2), "bowl_rank": round(bowl_rank, 2),
        "overseas": _is_overseas(pid, loaded["store"], name, foreign),
        "form_bat": {"innings": len(bat_rows), "runs": form_bat["runs"], "sr": _rate(form_bat["runs"], form_bat["balls"]),
                     "avg": round(form_bat["runs"] / form_bat["outs"], 1) if form_bat["outs"] else None},
        "form_bowl": {"spells": len(bowl_rows), "wickets": form_wkts,
                      "econ": round(form_bowl["runs_conceded"] * 6 / form_bowl["balls_bowled"], 2) if form_bowl["balls_bowled"] else None},
        "vs_bowlers": {"balls": vb[0], "runs": vb[1], "outs": vb[2]} if vb[0] >= MIN_MATCHUP_BALLS else None,
        "vs_batters": {"balls": vw[0], "runs": vw[1], "wickets": vw[2]} if vw[0] >= MIN_MATCHUP_BALLS else None,
    }


def _reason(p: dict[str, Any], slot: str, opponent: str) -> str:
    fb, fw = p["form_bat"], p["form_bowl"]
    parts = []
    if slot == "bowl":
        if fw["spells"]:
            parts.append(f"{fw['wickets']} wkts, economy {fw['econ']} in last {fw['spells']} spells")
        if p["vs_batters"]:
            v = p["vs_batters"]
            parts.append(f"v {opponent} batters: {v['runs']} off {v['balls']} balls, {v['wickets']} out")
    else:
        if fb["innings"]:
            parts.append(f"{fb['runs']} runs" + (f", SR {fb['sr']}" if fb["sr"] else "") + f" in last {fb['innings']} inns")
        if p["vs_bowlers"]:
            v = p["vs_bowlers"]
            parts.append(f"v {opponent} bowlers: {v['runs']} off {v['balls']}, out {v['outs']}×")
    if not parts:
        parts.append("no recent record: counted as average" if not p["found"] else "best available option")
    return " · ".join(parts)


def pick(players: list[dict[str, Any]], is_ipl: bool) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Choose 11: keeper, 5 bowling options, 5 batters (overseas limit for IPL). Returns picks and the slot of each."""
    chosen: list[dict[str, Any]] = []
    slot: dict[str, str] = {}

    def allowed(p: dict[str, Any]) -> bool:
        return p["name"] not in slot and not (is_ipl and p["overseas"] and sum(c["overseas"] for c in chosen) >= OVERSEAS_LIMIT)

    def take(p: dict[str, Any], kind: str) -> None:
        chosen.append(p)
        slot[p["name"]] = kind

    keepers = sorted((p for p in players if p["role"] == "wicket_keeper"), key=lambda p: -p["bat_rank"])
    for p in keepers:
        if allowed(p):
            take(p, "keep")
            break
    for p in sorted((p for p in players if p["bowls"]), key=lambda p: p["bowl_rank"]):
        if sum(1 for c in chosen if slot[c["name"]] == "bowl") >= BOWLING_OPTIONS:
            break
        if allowed(p):
            take(p, "bowl")
    for p in sorted(players, key=lambda p: -p["bat_rank"]):
        if len(chosen) >= 11:
            break
        if allowed(p):
            take(p, "bat")
    return chosen, slot


def _resolved_ids(names: list[str], fam: str, team: str, loaded: dict[str, Any]) -> list[str]:
    return [pid for pid in (ml_model._resolve_id(n, fam, loaded, team) for n in names) if pid]


def suggest(squad: list[dict[str, Any]], team: str, opponent: str, opponent_xi: list[str], fam: str,
            is_ipl: bool, foreign: set[str] | None = None) -> dict[str, Any]:
    loaded = ml_model.load_store()
    if not loaded:
        return {"available": False}
    fam = fam if fam in ("t20", "odi") else "t20"
    opp_ids = _resolved_ids(opponent_xi, fam, opponent, loaded)
    scored = {p["name"]: score_player(p["name"], team, p.get("role", "batter"), fam, opp_ids, opp_ids, loaded, foreign if is_ipl else None)
              for p in squad}
    recent = [scored[p["name"]] for p in squad if p.get("recent", True)]
    pool = recent if len(recent) >= 11 else list(scored.values())
    chosen, slot = pick(pool, is_ipl)
    if len(chosen) < 11:  # recent squad couldn't fill the shape (e.g. overseas limit): widen to everyone
        chosen, slot = pick(list(scored.values()), is_ipl)
    order = {"keep": 0, "bat": 1, "bowl": 2}
    chosen.sort(key=lambda p: (order[slot[p["name"]]], -p["bat_rank"] if slot[p["name"]] != "bowl" else p["bowl_rank"]))
    slot_label = {"keep": "Keeper", "bat": "Batting", "bowl": "Bowling"}
    picks = [{"name": p["name"], "slot": slot_label[slot[p["name"]]], "overseas": p["overseas"], "found": p["found"],
              "bat": p["bat"], "econ": p["econ"], "reason": _reason(p, "bowl" if slot[p["name"]] == "bowl" else "bat", opponent)}
             for p in chosen]
    picked = {p["name"] for p in chosen}
    bench = sorted((p for p in pool if p["name"] not in picked), key=lambda p: min(-p["bat_rank"] / 10, p["bowl_rank"] if p["bowls"] else 99))
    left_out = [{"name": p["name"], "bat": p["bat"], "econ": p["econ"],
                 "reason": _reason(p, "bowl" if p["bowls"] and p["role"] == "bowler" else "bat", opponent)} for p in bench[:4]]
    return {
        "available": True, "team": team, "opponent": opponent, "format": fam,
        "xi": [p["name"] for p in chosen], "picks": picks, "left_out": left_out,
        "overseas": sum(p["overseas"] for p in chosen) if is_ipl else None,
        "bowling_options": sum(1 for p in chosen if p["bowls"]),
        "matchups_used": bool(opp_ids),
        "priors": {"bat": round(player_bat_index(None, fam), 1), "econ": BOWL_PRIOR[fam]["econ"]},
    }
