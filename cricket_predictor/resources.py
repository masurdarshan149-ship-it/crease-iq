"""Resources still to come in an innings: the batters yet to bat and the bowlers' overs left.

Everything comes from each player's record before today (the same feature store and player insights the model
and the Form tab use). The batting order is the model's own guess (usual batting position) unless the user said who
is at the crease. Bowlers' overs left are known only when the user taps who bowled each over; otherwise the
bowling list shows the attack and its phase numbers without a count.
"""

from __future__ import annotations

from typing import Any

from . import insights, ml_model
from .ml_features import typical_position

QUOTA = {"t20": 24, "odi": 60}            # legal balls one bowler may bowl
PHASE_ENDS = {"t20": (36, 90, 120), "odi": (60, 240, 300)}
PHASE_KEYS = ("pp", "mid", "death")
PHASE_NAMES = {"pp": "powerplay", "mid": "middle overs", "death": "death overs"}


def _phase_at(balls: int, fam: str) -> int:
    ends = PHASE_ENDS[fam]
    return next((i for i, e in enumerate(ends) if balls < e), len(ends) - 1)


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _batter(name: str, stats: dict | None, team: str, fam: str, phase_i: int) -> dict[str, Any]:
    balls = _num(stats.get("balls")) if stats else 0.0
    runs = _num(stats.get("runs")) if stats else 0.0
    outs = _num(stats.get("outs")) if stats else 0.0
    career_sr = round(runs * 100 / balls, 1) if balls >= 30 else None
    career_avg = round(runs / outs, 1) if outs >= 3 else None
    f = insights.form(name, team).get(fam) or {}
    recent = f.get("batting") or []
    rb = sum(x["balls"] for x in recent)
    rr = sum(x["runs"] for x in recent)
    bounds = sum(x.get("fours", 0) + x.get("sixes", 0) for x in recent)
    sixes = sum(x.get("sixes", 0) for x in recent)
    form_sr = round(rr * 100 / rb, 1) if rb >= 20 else None
    ph = (insights.phase_rows([name], team, fam) or [{}])[0].get("bat", {})
    upcoming = [k for k in PHASE_KEYS[phase_i:]]
    phase_sr = {k: (ph.get(k, {}).get("sr") if not ph.get(k, {}).get("small", True) else None) for k in PHASE_KEYS}
    tags = []
    real_batter = balls >= 300 and typical_position(stats) <= 7.5
    if real_batter and form_sr and career_sr and len(recent) >= 4:
        if form_sr >= career_sr * 1.15 and rr / max(1, len(recent)) >= 20:
            tags.append("in form")
        elif form_sr <= career_sr * 0.85 or rr / max(1, len(recent)) < 12:
            tags.append("out of touch")
    death_sr = phase_sr.get("death")
    if death_sr and death_sr >= (185 if fam == "t20" else 130):
        tags.append("finisher")
    if rb >= 30 and bounds * 100 / rb >= 22:
        tags.append("big hitter")
    return {
        "name": name, "found": bool(stats), "career_sr": career_sr, "career_avg": career_avg,
        "form_innings": len(recent), "form_runs": rr, "form_sr": form_sr,
        "boundary_pct": round(bounds * 100 / rb, 1) if rb >= 30 else None, "form_sixes": sixes,
        "phase_sr": phase_sr, "next_phase": upcoming[0] if upcoming else "death", "tags": tags,
    }


def _bowler(name: str, stats: dict | None, team: str, fam: str, bowled: int | None, phase_i: int) -> dict[str, Any]:
    balls = _num(stats.get("balls_bowled")) if stats else 0.0
    conceded = _num(stats.get("runs_conceded")) if stats else 0.0
    wkts = _num(stats.get("wickets")) if stats else 0.0
    f = insights.form(name, team).get(fam) or {}
    spells = f.get("bowling") or []
    sb = sum(x["balls"] for x in spells)
    sr_ = sum(x["runs"] for x in spells)
    ph = (insights.phase_rows([name], team, fam) or [{}])[0].get("bowl", {})
    phase_econ = {k: (ph.get(k, {}).get("econ") if not ph.get(k, {}).get("small", True) else None) for k in PHASE_KEYS}
    career_econ = round(conceded * 6 / balls, 2) if balls >= 60 else None
    form_econ = round(sr_ * 6 / sb, 2) if sb >= 30 else None
    tags = []  # "best at the death" / "best in the powerplay" are added across the attack in resources()
    if form_econ and career_econ and len(spells) >= 4:
        if form_econ <= career_econ - 0.75:
            tags.append("in form")
        elif form_econ >= career_econ + 1.5:
            tags.append("expensive lately")
    quota = QUOTA[fam]
    return {
        "name": name, "found": bool(stats), "career_balls": int(balls), "career_econ": career_econ,
        "career_wkts": int(wkts), "form_spells": len(spells), "form_econ": form_econ,
        "form_wkts": sum(x["wickets"] for x in spells), "phase_econ": phase_econ, "tags": tags,
        "bowled": bowled, "left": (max(0, quota - bowled) if bowled is not None else None), "quota": quota,
    }


def resources(app: Any, payload: dict[str, Any], team_name) -> dict[str, Any]:
    mode = app._mode_key(payload.get("mode"))
    fam = payload.get("format") if payload.get("format") in {"t20", "odi"} else "t20"
    chase = payload.get("side") == "chase"
    bat_code, field_code = (payload.get("chasing"), payload.get("batting")) if chase else (payload.get("batting"), payload.get("chasing"))
    bat_xi = [str(n) for n in (payload.get("chasing_xi" if chase else "batting_xi") or [])][:12]
    field_xi = [str(n) for n in (payload.get("batting_xi" if chase else "chasing_xi") or [])][:12]
    bat_team, field_team = team_name(app, mode, bat_code), team_name(app, mode, field_code)
    wickets = max(0, min(10, int(_num(payload.get("wickets")))))
    balls = max(0, int(_num(payload.get("balls"))))
    phase_i = _phase_at(balls, fam)
    loaded = ml_model.load_store()

    def stats_of(name: str, team: str) -> dict | None:
        if not loaded:
            return None
        pid = ml_model.resolve_id(name, fam, team)
        return loaded["store"]["players"][fam].get(pid) if pid else None

    # batting order: the order the user dragged the XI into, else the model's guess from usual batting positions;
    # the user's crease (if given) overrides who is in
    bat_stats = {n: stats_of(n, bat_team) for n in bat_xi}
    crease = [n for n in (payload.get("crease") or []) if n in bat_stats][:2]
    order_set = bool(payload.get("chasing_order_set" if chase else "batting_order_set"))
    rest = [n for n in bat_xi if n not in crease]
    order = rest if order_set else sorted(rest, key=lambda n: typical_position(bat_stats[n]))
    if crease:
        gone, rest = order[:wickets], order[wickets:]
        at_crease = crease
    else:
        gone, at_crease, rest = order[:wickets], order[wickets:wickets + 2], order[wickets + 2:]
    batters = ([{**_batter(n, bat_stats[n], bat_team, fam, phase_i), "status": "in"} for n in at_crease]
               + [{**_batter(n, bat_stats[n], bat_team, fam, phase_i), "status": "next" if i < 3 else "later"} for i, n in enumerate(rest)])

    # bowlers: the most-used bowlers of the fielding XI, plus anyone the user logged as bowling
    bowled = {str(k): int(_num(v)) for k, v in (payload.get("bowled") or {}).items() if str(k) in field_xi}
    tracked = bool(bowled)
    field_stats = {n: stats_of(n, field_team) for n in field_xi}
    by_use = sorted(field_xi, key=lambda n: _num((field_stats[n] or {}).get("balls_bowled")), reverse=True)
    names = [n for n in by_use[:6] if _num((field_stats[n] or {}).get("balls_bowled")) >= 60 or n in bowled]
    names += [n for n in bowled if n not in names]
    bowlers = [_bowler(n, field_stats[n], field_team, fam, (bowled.get(n, 0) if tracked else None), phase_i) for n in names]
    for key, label in (("death", "best at the death"), ("pp", "best in the powerplay")):
        ranked = [b for b in bowlers if b["phase_econ"].get(key) is not None]
        if len(ranked) >= 2:
            min(ranked, key=lambda b: b["phase_econ"][key])["tags"].insert(0, label)
    if tracked:
        bowlers.sort(key=lambda b: (-(b["left"] or 0), b["phase_econ"].get("death") or b["career_econ"] or 99))
    logged = sum(bowled.values())
    # matchup alert: the two batters in and the next one against the bowler of the current over (from "Who bowled?")
    bowler_now = str(payload.get("bowler") or "")
    matchups = []
    if bowler_now and bowler_now in field_xi:
        for b in [x for x in batters if x["status"] in ("in", "next")][:3]:
            h = insights.head_to_head(b["name"], bat_team, bowler_now, field_team)
            st = h.get(fam) if h.get("available") else None
            matchups.append({"batter": b["name"], "status": b["status"], "found": bool(st and st.get("balls")),
                             **({k: st[k] for k in ("balls", "runs", "outs", "fours", "sixes", "dots", "strike_rate", "dot_pct", "edge", "matches")}
                                if st and st.get("balls") else {})})
    return {
        "format": fam, "phase": PHASE_KEYS[phase_i], "phase_name": PHASE_NAMES[PHASE_KEYS[phase_i]],
        "batting_team": bat_team, "fielding_team": field_team, "wickets": wickets, "balls": balls,
        "order_guessed": not crease and not order_set, "order_set": order_set, "out": gone, "batters": batters, "bowlers": bowlers,
        "tracked": tracked, "logged_balls": logged, "quota": QUOTA[fam],
        "field_xi": field_xi, "attack": names, "bowler_now": bowler_now or None, "matchups": matchups,  # attack: fixed order (most-used first) for the "Who bowled?" chips
    }
