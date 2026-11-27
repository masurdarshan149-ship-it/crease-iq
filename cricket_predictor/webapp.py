"""JSON API + static files for the app's page (web/index.html).

main.py serves the page and forwards these routes here (the old server-made pages were removed on 26 Nov 2026):
  GET  /                      new app shell (web/index.html)
  GET  /static/<file>         CSS / JS
  GET  /api/config?mode=ipl   teams, squads, venues, model info
  POST /api/predict           JSON match input -> prediction
  GET  /api/history           recent predictions        POST /api/history/clear
  GET  /api/accuracy          model accuracy report + version history
  GET  /api/status            data + model status       POST /api/retrain
The `app` argument is the running main module (so we reuse its team banks,
form parser and history helpers without importing main.py a second time).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime  # noqa: F811
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlencode

from . import ml_model, settings
from .ml_features import FORMAT_MAX_BALLS

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
ML_DIR = ROOT / "data" / "ml"
STATIC_TYPES = {".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8",
                ".svg": "image/svg+xml", ".html": "text/html; charset=utf-8",
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".avif": "image/avif",
                ".webmanifest": "application/manifest+json"}

ROLE_LABELS = {"batter": "Batter", "bowler": "Bowler", "all_rounder": "All-rounder", "wicket_keeper": "Keeper"}


# --------------------------------------------------------------------------- static
def static_file(path: str) -> tuple[bytes, str] | None:
    name = path.removeprefix("/static/")
    target = (WEB_DIR / name).resolve()
    if WEB_DIR.resolve() not in target.parents or not target.is_file():
        return None
    return target.read_bytes(), STATIC_TYPES.get(target.suffix, "application/octet-stream")


def index_html() -> bytes:
    return (WEB_DIR / "index.html").read_bytes()


# --------------------------------------------------------------------------- config
def _venue_payload(app: ModuleType, mode: str, code: str, venue: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "code": code, "name": venue["name"], "city": venue.get("city", ""), "country": venue.get("country", ""),
        "matches": venue.get("_matches", 0), "last": venue.get("_last"), "from_data": bool(venue.get("_from_data")),
    }
    for fmt in ("t20", "odi"):
        recent = app._venue_recent_average(venue, fmt)
        out[f"par_{fmt}"] = round(app._venue_average_score(venue, fmt))
        if recent and recent.get("n"):
            out[f"par_{fmt}_note"] = f"Average of last {recent['n']} games here (latest {recent['last']})"
        elif recent:
            out[f"par_{fmt}_note"] = "No recent games here, so the recent format average is used"
        else:
            out[f"par_{fmt}_note"] = "Preset value"
    return out


XI_SHAPE = (("wicket_keeper", 1), ("batter", 4), ("all_rounder", 2), ("bowler", 4))


def default_xi(squad: list[dict[str, Any]]) -> list[str]:
    """A balanced XI (1 keeper, 4 batters, 2 all-rounders, 4 bowlers) of the most experienced players.

    Squads are listed batters-first, so simply taking the first 11 names gave an XI with no bowlers.
    """
    ranked = sorted(squad, key=lambda p: -(p.get("matches") or 0))  # stable: keeps squad order on ties
    picked: list[str] = []
    for role, count in XI_SHAPE:
        picked += [p["name"] for p in ranked if p["role"] == role][:count]
    for p in ranked:  # fill any role shortfall with the next most experienced players
        if len(picked) >= 11:
            break
        if p["name"] not in picked:
            picked.append(p["name"])
    order = {p["name"]: i for i, p in enumerate(squad)}
    return sorted(picked[:11], key=order.get)


def _custom_par(mode: str) -> dict[str, int | None]:
    """Recent average first-innings score for each format, used for grounds not in the data."""
    loaded = ml_model.load_store()
    groups = (loaded or {}).get("store", {}).get("group_recent", {})
    t20_group = "t20|club" if mode == "ipl" else "t20|international"
    out: dict[str, int | None] = {}
    for fmt, group in (("t20", t20_group), ("odi", "odi|international")):
        value = groups.get(group)
        out[fmt] = round(value) if value else {"t20": 165, "odi": 260}[fmt]
    return out


def _team_default_xi(app: ModuleType, mode: str, code: str | None) -> list[str]:
    preset = app._team_bank(mode).get(code or "")
    if not preset:
        return []
    latest = preset.get("_latest_xi", {}).get("t20", {}).get("xi")
    if latest:
        return latest
    squad = [{**p, "matches": ml_model.player_matches(p["name"], "t20", preset["name"])} for p in preset.get("squad", [])]
    return default_xi(squad)


def config(app: ModuleType, mode: str) -> dict[str, Any]:
    mode = app._mode_key(mode)
    teams = []
    for code, preset in app._team_bank(mode).items():
        squad = []
        for p in preset.get("squad", []):
            matches = ml_model.player_matches(p["name"], "t20", preset["name"])
            squad.append({
                "name": p["name"],
                "role": p["role"],
                "role_label": ROLE_LABELS.get(p["role"], p["role"]),
                "in_data": matches is not None,
                "matches": matches,
                "recent": p.get("recent", True),
                "games": p.get("games", 0),
                "added": bool(p.get("added")),  # you added this player (Update squad)
                # usual batting position per format: the Selected XI list starts in this order (the model's guess)
                "pos": {f: ml_model.player_position(p["name"], f, preset["name"]) for f in ("t20", "odi")},
            })
        latest = preset.get("_latest_xi", {})
        balanced = default_xi(squad)
        teams.append({
            "code": code,
            "name": preset["name"],
            "squad": squad,
            "squad_window": preset.get("_window"),
            "latest_xi": latest,  # {"t20": {"date", "opponent", "venue", "xi"}, "odi": {...}}
            # the XI that actually played most recently (T20), else a balanced pick
            "default_xi": latest.get("t20", {}).get("xi") or balanced,
            "balanced_xi": balanced,
        })
    venues = [_venue_payload(app, mode, code, v) for code, v in app._venue_bank(mode).items()]
    bat, chase = app._default_team_codes(mode)
    info = _model_head()
    return {
        "mode": mode,
        "teams": teams,
        "venues": venues,
        "defaults": {"batting": bat, "chasing": chase, "venue": _home_ground(app, mode, bat)},
        "custom_par": _custom_par(mode),
        "max_balls": FORMAT_MAX_BALLS,
        "model": {
            "available": bool(info),
            "label": ml_model.MODEL_LABELS.get(info.get("chosen", ""), info.get("chosen")),
            "trained_at": info.get("trained_at"),
            "data_through": info.get("data_through"),
        },
    }


# --------------------------------------------------------------------------- predict
def _clean_overs(value: Any, fmt: str) -> float:
    try:
        overs = float(value)
    except (TypeError, ValueError):
        overs = FORMAT_MAX_BALLS.get(fmt, 120) / 6
    whole = int(overs)
    balls = min(5, int(round((overs - whole) * 10)))
    max_overs = FORMAT_MAX_BALLS.get(fmt, 120) // 6
    if whole >= max_overs:
        return float(max_overs)
    return whole + balls / 10


def chase(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """Live chase: chasing side's win chance from target, runs, wickets and overs."""
    from . import chase_model

    try:
        _warm_par(app, payload, "chase")
    except Exception:  # noqa: BLE001 - only a speed-up
        pass

    mode = app._mode_key(payload.get("mode"))
    fmt = payload.get("format") if payload.get("format") in {"t20", "odi"} else "t20"
    target = max(1, min(800, int(payload.get("target") or 1)))
    runs = max(0, min(800, int(payload.get("runs") or 0)))
    wickets = max(0, min(10, int(payload.get("wickets") or 0)))
    overs = _clean_overs(payload.get("overs"), fmt)
    # the team / venue / XI context is built exactly like a first-innings prediction
    context_payload = {**payload, "runs": target - 1, "wickets": 10, "overs": FORMAT_MAX_BALLS[fmt] / 6, "save": False}
    context, form = _build_context(app, context_payload)
    out = chase_model.predict(context, target, runs, wickets, overs)
    bat, chase_team = context.batting_first_team.name, context.chasing_team.name
    _pk, dew_key = _conditions(payload)
    dew_info = None
    if out["status"] == "live" and settings.dew_shift(dew_key):
        left = out["equation"]["balls_left"] / FORMAT_MAX_BALLS[fmt]
        shift = settings.dew_shift(dew_key) * left ** 0.5  # full effect at the start, fading to nothing at the end
        before = out["chase_pct"]
        out["chase_pct"] = round(_dew_shift(before / 100, shift) * 100, 1)
        dew_info = {"key": dew_key, "label": DEW[dew_key][0], "chase_pts": round(out["chase_pct"] - before, 1)}
    out["conditions"] = {"dew": dew_info, "pitch": _pk if _pk != "balanced" else None}
    pct = out["chase_pct"]
    if out["status"] == "won":
        verdict, winner = f"{chase_team} have won", chase_team
    elif out["status"] == "lost":
        verdict, winner = f"{bat} have won", bat
    elif out["status"] == "tied":
        verdict, winner = "Scores level: tie (super over)", None
    else:
        lead = min(99.0, max(pct, 100 - pct))  # while the chase is live, nothing is certain
        verdict = ("Too close to call" if lead < 55 else "Slight edge" if lead < 62 else "Clear favourite" if lead < 75 else "Strong favourite") + f" · {lead:.0f}% chance"
        winner = chase_team if pct >= 50 else bat
    if payload.get("save"):
        eq = out["equation"]
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "type": "chase", "format": fmt.upper(),
            "batting_first_team": bat, "chasing_team": chase_team, "first_innings_score": target - 1,
            "chase_score": f"{runs}/{wickets} ({eq['overs_text']})", "target": target,
            "predicted_winner": winner or "Tie", "batting_first_win_probability": round(100 - pct, 2),
            "chasing_win_probability": pct, "confidence": round(abs(pct - 50) * 2, 2),
            "model": f"ML chase ({out.get('model_label', '')})", "mode": mode, "stage": "chase",
            "pitch": _pk, "dew": dew_key, "setup": _setup(payload),
        }
        items = app._read_history()
        items.insert(0, entry)
        app._write_history(items[: app.HISTORY_LIMIT])
    trust = None
    if out["status"] == "live":
        mb = FORMAT_MAX_BALLS.get(fmt, 120)
        done = (out.get("equation") or {}).get("balls_bowled")
        if done is None:
            done = mb - int((out.get("equation") or {}).get("balls_left") or mb)
        frac = done / mb
        phase = "start" if done <= 0 else "early" if frac <= 0.3 else "middle" if frac <= 0.75 else "late"
        trust = trust_level("chase", phase, mode, max(pct, 100 - pct))
        verdict = verdict_for_trust(verdict, trust)
    return {**out, "batting_team": bat, "chasing_team": chase_team, "batting_code": form["batting_first_team_code"],
            "chasing_code": form["chasing_team_code"], "verdict": verdict, "winner": winner, "format": fmt, "trust": trust}


def chase_scenarios(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """'What they need': win chance after the next ball / next over for different outcomes."""
    from . import chase_model

    fmt = payload.get("format") if payload.get("format") in {"t20", "odi"} else "t20"
    target = max(1, min(800, int(payload.get("target") or 1)))
    context, _ = _build_context(app, {**payload, "runs": target - 1, "wickets": 10, "overs": FORMAT_MAX_BALLS[fmt] / 6})
    out = chase_model.scenarios(
        context, target, max(0, int(payload.get("runs") or 0)), max(0, min(10, int(payload.get("wickets") or 0))),
        _clean_overs(payload.get("overs"), fmt),
    )
    _pk, dew_key = _conditions(payload)
    if out.get("live") and settings.dew_shift(dew_key):
        balls = chase_model.balls_from_overs(_clean_overs(payload.get("overs"), fmt), FORMAT_MAX_BALLS[fmt])
        shift = settings.dew_shift(dew_key) * max(0.0, 1 - balls / FORMAT_MAX_BALLS[fmt]) ** 0.5
        adj = lambda v: v if v in (0.0, 50.0, 100.0) else round(_dew_shift(v / 100, shift) * 100, 1)  # noqa: E731
        out["now"] = adj(out["now"])
        for item in out["next_ball"]:
            item["pct"] = adj(item["pct"])
        out["grid"] = {w: [adj(v) for v in row] for w, row in out["grid"].items()}
        no_wkt = list(zip(out["grid_runs"], out["grid"]["0"]))
        out["runs_for_50"] = next((r for r, p in no_wkt if p >= 50), None)
    return out


def _side_players(app: ModuleType, mode: str, payload: dict[str, Any], side: str) -> list[str]:
    """The ticked XI plus the impact player (IPL), who joins as a 12th name: the model then picks the best
    7 batters and 5 bowlers from all 12, which is exactly the extra depth an impact substitute gives."""
    xi = list(payload.get(f"{side}_xi") or [])[:11] or _team_default_xi(app, mode, payload.get(side))
    impact = payload.get(f"{side}_impact") or {}
    sub = str(impact.get("in") or "").strip() if isinstance(impact, dict) else ""
    if sub and sub not in xi and mode == "ipl":
        xi = xi + [sub]
    return xi


def _attach_crease(payload: dict[str, Any], context: Any) -> None:
    """Batters at the crease from the optional 'At the crease' input (names + balls faced)."""
    out = {}
    for side, key in (("bat", "batting_crease"), ("chase", "chasing_crease")):
        rows = [r for r in (payload.get(key) or []) if isinstance(r, dict) and str(r.get("name") or "").strip()][:2]
        if rows:
            out[side] = [{"name": str(r["name"]).strip(), "balls": (max(0, int(r["balls"])) if r.get("balls") not in (None, "") else None)}
                         for r in rows]
    context.crease = out or None
    context.order = _batting_orders(payload)


def _batting_orders(payload: dict[str, Any]) -> dict[str, list[str] | None]:
    """The batting order the user set by dragging the Selected XI (the XI list in that order), per side; None when
    they didn't touch it, so the model keeps guessing from usual positions."""
    out = {}
    for side, key in (("bat", "batting"), ("chase", "chasing")):
        names = [str(n) for n in (payload.get(f"{key}_xi") or [])][:12]
        out[side] = names if payload.get(f"{key}_order_set") and names else None
    return out


def _attach_venue(app: ModuleType, mode: str, code: Any, context: Any) -> None:
    """Tell the model which ground this is (for home advantage and how often batting first wins there)."""
    venue = app._venue_bank(mode).get(str(code or "")) if code else None
    if venue and venue.get("_key"):
        context.venue = {"key": venue["_key"], "kind": venue.get("_kind") or ("club" if mode == "ipl" else "international"),
                         "name": venue.get("name", ""), "city": venue.get("city", "")}


def _build_context(app: ModuleType, payload: dict[str, Any]):
    mode = app._mode_key(payload.get("mode"))
    fmt = payload.get("format") if payload.get("format") in {"t20", "odi"} else "t20"
    payload, _pitch = _apply_pitch(app, mode, fmt, payload)
    form: dict[str, Any] = {
        "mode": mode,
        "format": fmt,
        "venue_code": payload.get("venue") or app._default_venue_code(mode),
        "batting_first_team_code": payload.get("batting"),
        "chasing_team_code": payload.get("chasing"),
        "first_innings_score": max(0, min(700, int(payload.get("runs") or 0))),
        "wickets_lost": max(0, min(10, int(payload.get("wickets") or 0))),
        "overs_faced": _clean_overs(payload.get("overs"), fmt),
        "batting_first_playing": _side_players(app, mode, payload, "batting"),
        "chasing_playing": _side_players(app, mode, payload, "chasing"),
    }
    if str(payload.get("venue") or "").startswith("custom:"):  # a ground that isn't in the data yet
        form["venue_code"] = app._default_venue_code(mode)
        if not payload.get("par"):
            payload = {**payload, "par": _custom_par(mode).get(fmt)}
    if payload.get("par"):
        form["average_first_innings_score"] = float(payload["par"])
    context = app.parse_form_body(urlencode(form, doseq=True).encode("utf-8"))
    _attach_venue(app, mode, payload.get("venue"), context)
    _attach_crease(payload, context)
    return context, form


# ---- conditions you set from the pitch report (not in the match data, so these are sensible settings, not learned)
PITCH = {  # multiplier on the par score
    "balanced": ("Balanced", 1.0), "flat": ("Flat / batting", 1.08), "green": ("Green / grassy", 0.94),
    "dry": ("Dry / turning", 0.93), "slow": ("Slow / low", 0.91),
}
DEW = {  # shift in the chasing side's log-odds: +0.25 is about +6 points in a 50/50 match
    "none": ("No effect", 0.0), "light": ("Light dew", 0.12), "heavy": ("Heavy dew", 0.25),
    "slowing": ("Pitch will slow down / no dew", -0.17),
}


def _conditions(payload: dict[str, Any]) -> tuple[str, str]:
    pitch = payload.get("pitch") if payload.get("pitch") in PITCH else "balanced"
    dew = payload.get("dew") if payload.get("dew") in DEW else "none"
    return pitch, dew


def _apply_pitch(app: ModuleType, mode: str, fmt: str, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """A typed par always wins; otherwise the venue's par is scaled by the pitch you chose."""
    pitch, _ = _conditions(payload)
    if pitch == "balanced" or payload.get("par"):
        return payload, None
    code = str(payload.get("venue") or "")
    if code.startswith("custom:"):
        base = _custom_par(mode).get(fmt)
    else:
        venue = app._venue_bank(mode).get(code)
        base = round(app._venue_average_score(venue, fmt)) if venue else None
    if not base:
        return payload, None
    par = round(base * settings.pitch_multiplier(pitch))
    return {**payload, "par": par}, {"key": pitch, "label": PITCH[pitch][0], "par_from": base, "par": par}


def _dew_shift(prob_chase: float, shift: float) -> float:
    """Move the chasing side's chance by `shift` on the log-odds scale (bigger effect near 50%, small near 0/100)."""
    import math
    p = min(max(prob_chase, 0.001), 0.999)
    return 1 / (1 + math.exp(-(math.log(p / (1 - p)) + shift)))


_TRUST_CACHE: dict[str, Any] = {}
TRUST_STAGE_LABEL = {"pre_match": "before the match", "mid_innings": "during the first innings", "innings_break": "at the innings break",
                     "start": "at the start of a chase", "early": "early in a chase", "middle": "in the middle of a chase",
                     "late": "late in a chase"}


# ---- an honest note on very sure ODI calls at the innings break: in 2022-24 they were right about as often as the
# model said, but in 2025-26 noticeably less (scripts/odi_confidence_experiment.py; softening the model didn't pass,
# so the model is unchanged and the note says how such calls really went)
SURE = 90.0
_SURE_CACHE: dict[str, Any] = {}


def sure_odi_note(fmt: str, stage: str, fav_pct: float) -> dict[str, Any] | None:
    if fmt != "odi" or stage != "innings_break" or fav_pct < SURE:
        return None
    try:
        from . import replay
        index = replay._quick_index() or []
        key = (len(index), (ML_DIR / "odi_confidence_experiment.json").stat().st_mtime
               if (ML_DIR / "odi_confidence_experiment.json").exists() else 0)
        if _SURE_CACHE.get("key") != key:
            recent = [m for m in index if m.get("m") and m["competition"] == "odi" and m["date"] >= replay.TEST_START
                      and m["m"]["brk_conf"] >= SURE]
            now = None
            if recent:
                now = {"n": len(recent), "said": round(sum(m["m"]["brk_conf"] for m in recent) / len(recent)),
                       "right": round(sum(1 for m in recent if not m["m"]["brk_wrong"]) * 100 / len(recent))}
            before = None
            try:
                seasons = json.loads((ML_DIR / "odi_confidence_experiment.json").read_text(encoding="utf-8"))["seasons"]
                old = [s["sure_90"]["model"] for k, s in seasons.items() if k != "2025-26" and s["sure_90"]["model"].get("n")]
                n = sum(s["n"] for s in old)
                if n:
                    before = {"n": n, "said": round(sum(s["said"] * s["n"] for s in old) / n),
                              "right": round(sum(s["right"] * s["n"] for s in old) / n)}
            except (OSError, ValueError, KeyError):
                pass
            _SURE_CACHE.update(key=key, now=now, before=before)
        now, before = _SURE_CACHE["now"], _SURE_CACHE["before"]
    except Exception:  # noqa: BLE001 - a note, never in the way of a prediction
        return None
    if not now:
        return None
    text = (f"ODI calls this sure at the innings break were right {now['right']}% of the time in 2025-26 "
            f"({now['n']} matches, the model said {now['said']}% on average)")
    if before:
        text += f"; in 2022-24 they were right {before['right']}% ({before['n']} matches)"
    text += ". A big first-innings total in an ODI can still be chased, so treat this as likely, not certain."
    return {"text": text, "right": now["right"], "matches": now["n"]}


_VERDICT_RANK = {"Too close to call": 0, "Slight edge": 1, "Clear favourite": 2, "Strong favourite": 3}


def verdict_for_trust(verdict: str, trust: dict[str, Any] | None) -> str:
    """The heading never sounds surer than the trust badge under it: with a Lean badge (e.g. an IPL call before the
    match, capped at Lean) "Clear / Strong favourite" becomes "Lean pick"; with a Toss-up badge anything above "Slight
    edge" becomes "Toss-up". Any " · 73% chance" ending is kept."""
    if not trust:
        return verdict
    head, sep, tail = verdict.partition(" · ")
    rank = _VERDICT_RANK.get(head)
    if rank is None:
        return verdict
    if trust.get("level") == "lean" and rank >= 2:
        head = "Lean pick"
    elif trust.get("level") == "toss-up" and rank >= 2:
        head = "Toss-up"
    return head + sep + tail


def trust_level(model: str, stage: str, mode: str, fav_pct: float) -> dict[str, Any] | None:
    """Strong / Lean / Toss-up for a prediction, with how often that level was right in unseen matches like it
    (scripts/trust_levels.py, rebuilt with every retrain). The competition's own figure is used; with few matches it
    says so, and with very few it falls back to all competitions."""
    path = ML_DIR / "trust_levels.json"
    try:
        key = str(path.stat().st_mtime)
        if _TRUST_CACHE.get("key") != key:
            _TRUST_CACHE.update(key=key, data=json.loads(path.read_text(encoding="utf-8")))
        t = _TRUST_CACHE["data"]
    except (OSError, ValueError):
        return None
    band = "strong" if fav_pct >= t["strong_from"] else "lean" if fav_pct >= t["lean_from"] else "toss-up"
    groups = (t.get(model) or {}).get(stage) or {}
    comp = "ipl" if mode == "ipl" else "international"
    cell = (groups.get(comp) or {}).get(band) or {}
    whole = (groups.get("all") or {}).get(band) or {}
    if comp == "ipl" and stage == "pre_match" and band == "strong":
        # IPL before the match is close to a coin flip season after season (45-55% right in 2022-2025/26), so it is
        # never called a "Strong pick" there: at most a Lean, with the record of all its confident calls together
        lean, strong = (groups.get("ipl") or {}).get("lean") or {}, cell
        n_l, n_s = lean.get("matches") or 0, strong.get("matches") or 0
        band = "lean"
        whole = (groups.get("all") or {}).get("lean") or {}
        cell = ({"matches": n_l + n_s, "right_pct": (n_l * lean["right_pct"] + n_s * strong["right_pct"]) / (n_l + n_s)}
                if n_l + n_s and lean.get("right_pct") is not None and strong.get("right_pct") is not None else lean)
    if whole.get("right_pct") is None:
        return None
    n = cell.get("matches") or 0
    if n and cell.get("right_pct") is not None:
        # a small group (e.g. ~40 IPL matches) leans on all competitions; a big one speaks for itself
        right, used = (n * cell["right_pct"] + 50 * whole["right_pct"]) / (n + 50), comp
    else:
        right, used, n = whole["right_pct"], "all", whole.get("matches") or 0
    return {"level": band, "label": {"strong": "Strong pick", "lean": "Lean", "toss-up": "Toss-up"}[band],
            "right_pct": round(right, 1), "matches": n, "few": n < t.get("min_matches", 25),
            "competition": {"ipl": "IPL", "international": "international", "all": "unseen"}[used],
            "stage_text": TRUST_STAGE_LABEL.get(stage, ""), "test_from": t.get("test_from", "")[:4]}


SETUP_KEYS = ("mode", "format", "batting", "chasing", "venue", "par", "pitch", "dew", "pitch_report", "batting_xi", "chasing_xi",
              "batting_impact", "chasing_impact", "batting_order_set", "chasing_order_set", "runs", "wickets", "overs", "target")


def _setup(payload: dict[str, Any]) -> dict[str, Any]:
    """What the Predict page had set (teams, ground, format, conditions, par, XIs, score), so History can reopen it."""
    out = {k: payload.get(k) for k in SETUP_KEYS if payload.get(k) not in (None, "", [])}
    for k in ("batting_xi", "chasing_xi"):
        if isinstance(out.get(k), list):
            out[k] = [str(x) for x in out[k]][:12]
    if "pitch_report" in out:  # the report you read, kept with the prediction (so a record of real reports builds up)
        out["pitch_report"] = str(out["pitch_report"])[:600]
    return out


def _stage_of(overs: float, wickets: int, fmt: str) -> str:
    balls = int(overs) * 6 + round((overs % 1) * 10)
    if balls <= 0:
        return "pre_match"
    if wickets >= 10 or balls >= FORMAT_MAX_BALLS.get(fmt, 120):
        return "innings_break"
    return "mid_innings"


def _tag_latest(app: ModuleType, extra: dict[str, Any]) -> None:
    """Add details to the prediction that was just saved (stage, competition…) for the History tracker."""
    items = app._read_history()
    if items:
        items[0].update({k: v for k, v in extra.items() if v is not None})
        app._write_history(items)


def _track_innings_break(context, result, mode: str, dew_key: str, now: datetime) -> None:
    """Record the paired forecasts without changing the prediction or History."""
    from dataclasses import replace

    from . import chase_model, innings_trial

    path = innings_trial.database_path()
    if path is None or (result.details or {}).get("engine") != "ml":
        return
    chase_version = chase_model._load()
    if not chase_version:
        return
    fixture = innings_trial.Fixture(
        innings_trial.competition(mode, context.format),
        ml_model._team_key(result.batting_first_team),
        ml_model._team_key(result.chasing_team),
    )
    balls = chase_model.balls_from_overs(context.overs_faced, FORMAT_MAX_BALLS[context.format])
    checkpoint = innings_trial.Checkpoint(fixture, context.first_innings_score, context.wickets_lost, balls)
    # The chase has yet to start, so do not carry crease entries from a previous chase.
    opening = chase_model.predict(replace(context, crease=None), context.first_innings_score + 1, 0, 0, 0)
    chasing_pct = opening["chase_pct"]
    shift = settings.dew_shift(dew_key)
    if shift:
        chasing_pct = round(_dew_shift(chasing_pct / 100, shift) * 100, 1)
    innings_trial.record(
        path, now, checkpoint, result.batting_first_win_probability / 100, (100 - chasing_pct) / 100,
        (ml_model.model_info() or {}).get("trained_at"), chase_version.get("trained_at"),
    )


def predict(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    trial_requested = not getattr(app, "PUBLIC", False) and (
        payload.get("save") is True or payload.get("track_innings_break") is True
    )
    trial_time = datetime.now().astimezone() if trial_requested else None
    try:
        _warm_par(app, payload, "first")  # start the par-by-wickets grid now, so the page doesn't wait for it
    except Exception:  # noqa: BLE001 - only a speed-up
        pass
    mode = app._mode_key(payload.get("mode"))
    fmt = payload.get("format") if payload.get("format") in {"t20", "odi"} else "t20"
    payload, pitch_info = _apply_pitch(app, mode, fmt, payload)
    _pitch_key, dew_key = _conditions(payload)
    form: dict[str, Any] = {
        "mode": mode,
        "format": fmt,
        "venue_code": payload.get("venue") or app._default_venue_code(mode),
        "batting_first_team_code": payload.get("batting"),
        "chasing_team_code": payload.get("chasing"),
        "first_innings_score": max(0, min(700, int(payload.get("runs") or 0))),
        "wickets_lost": max(0, min(10, int(payload.get("wickets") or 0))),
        "overs_faced": _clean_overs(payload.get("overs"), fmt),
        "batting_first_playing": _side_players(app, mode, payload, "batting"),
        "chasing_playing": _side_players(app, mode, payload, "chasing"),
    }
    custom_venue = str(payload.get("venue") or "").startswith("custom:")
    if custom_venue:  # a ground that isn't in the data yet: use the recent format average as par
        form["venue_code"] = app._default_venue_code(mode)
        if not payload.get("par"):
            payload = {**payload, "par": _custom_par(mode).get(fmt)}
    if payload.get("par"):
        form["average_first_innings_score"] = float(payload["par"])
    context = app.parse_form_body(urlencode(form, doseq=True).encode("utf-8"))
    _attach_venue(app, mode, payload.get("venue"), context)
    _attach_crease(payload, context)
    result = app.predict_match_winner(context)
    dew_info = None
    if settings.dew_shift(dew_key):  # your dew call moves the chasing side's chance
        before = result.chasing_win_probability
        after = round(_dew_shift(before / 100, settings.dew_shift(dew_key)) * 100, 2)
        result.chasing_win_probability = after
        result.batting_first_win_probability = round(100 - after, 2)
        result.predicted_winner = result.chasing_team if after >= 50 else result.batting_first_team
        result.confidence = round(abs(after - 50) * 2, 2)
        dew_info = {"key": dew_key, "label": DEW[dew_key][0], "chase_pts": round(after - before, 1)}
    stage = _stage_of(context.overs_faced, context.wickets_lost, fmt)
    if payload.get("save", True):
        app._save_prediction(context, result)
        _tag_latest(app, {"pitch": _pitch_key, "dew": dew_key, "setup": _setup(payload)})
        _tag_latest(app, {"mode": mode, "venue": (app._venue_bank(mode).get(str(payload.get("venue") or "")) or {}).get("name"),
                          "wickets": context.wickets_lost, "overs": context.overs_faced,
                          "stage": stage})
    if trial_time is not None and stage == "innings_break":
        try:
            _track_innings_break(context, result, mode, dew_key, trial_time)
        except Exception:
            logging.getLogger(__name__).warning("Could not record the innings-break trial forecast", exc_info=True)
    bat_pct = result.batting_first_win_probability
    margin = abs(bat_pct - 50)
    verdict = "Too close to call" if margin < 5 else "Slight edge" if margin < 12 else "Clear favourite" if margin < 25 else "Strong favourite"
    trust = trust_level("win", stage, mode, max(bat_pct, 100 - bat_pct)) if "ML" in str(result.model_used) else None
    verdict = verdict_for_trust(verdict, trust)
    return {
        "batting_team": result.batting_first_team,
        "chasing_team": result.chasing_team,
        "batting_code": form["batting_first_team_code"],
        "chasing_code": form["chasing_team_code"],
        "batting_pct": bat_pct,
        "chasing_pct": result.chasing_win_probability,
        "winner": result.predicted_winner,
        "verdict": verdict,
        "trust": trust,
        "sure_note": sure_odi_note(fmt, stage, max(bat_pct, 100 - bat_pct)) if "ML" in str(result.model_used) else None,
        "model_used": result.model_used,
        "explanation": result.explanation,
        "details": result.details,
        "input": {"runs": form["first_innings_score"], "wickets": form["wickets_lost"], "overs": form["overs_faced"],
                  "format": fmt, "par": round(context.pitch_report.average_first_innings_score)},
        "projection": _projection(context),
        "conditions": {"pitch": pitch_info, "dew": dew_info},
    }


def _projection(context) -> dict[str, Any] | None:
    from . import score_model

    try:
        return score_model.project(context)
    except Exception:  # a projection problem must never break the prediction
        return None


# --------------------------------------------------------------------------- matchups & form
FIELDING_WINDOWS = {"ipl": (1, 2, 3), "international": (10, 20, 30)}
FIELDING_DEFAULT = {"ipl": 2, "international": 20}


def _fielding_sum(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    tot = {k: sum(r[k] for r in rows) for k in ("catches", "run_outs", "stumpings", "wickets", "balls")}
    return {
        "matches": n, **tot,
        "catches_pm": round(tot["catches"] / n, 2) if n else None,
        "run_outs_pm": round(tot["run_outs"] / n, 2) if n else None,
        "stumpings_pm": round(tot["stumpings"] / n, 2) if n else None,
        "wickets_pm": round(tot["wickets"] / n, 2) if n else None,
        "catch_share": round(tot["catches"] * 100 / tot["wickets"], 1) if tot["wickets"] else None,
        "first": rows[0]["date"] if rows else None, "last": rows[-1]["date"] if rows else None,
    }


def log_drop(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """The Drop button: +1 (or -1 to undo) dropped catch by the fielding side in today's match. delta 0 = just read."""
    from . import drops

    mode = app._mode_key(payload.get("mode"))
    fmt = payload.get("format") if payload.get("format") in {"t20", "odi"} else "t20"
    fielding_t = ml_model._team_key(_team_name(app, mode, payload.get("fielding")))
    batting_t = ml_model._team_key(_team_name(app, mode, payload.get("batting")))
    delta = int(payload.get("delta") or 0)
    if not delta:
        return {"fielding": fielding_t, "drops": drops.today_count(fielding_t, batting_t, fmt)}
    return drops.log(fielding_t, batting_t, fmt, mode, max(-1, min(1, delta)))


def fielding(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """Team fielding card: catches, run-outs and stumpings per match over a recent window.

    IPL: the last 1-3 seasons (default 2). International: each team's last 10/20/30 matches in this format (default 20).
    Dropped catches are not in Cricsheet: the drop % comes from drops you log with the Drop button (matched with the
    real catches after the next update), with an estimate shown until there are enough logged matches.
    """
    from . import drops
    mode = app._mode_key(payload.get("mode"))
    fmt = "t20" if mode == "ipl" else (payload.get("format") if payload.get("format") in {"t20", "odi"} else "t20")
    loaded = ml_model.load_store() or {}
    store = loaded.get("store", {})
    fields = store.get("fielding_fields", [])
    log = [dict(zip(fields, r)) for r in store.get("fielding_log", [])]
    windows = FIELDING_WINDOWS[mode]
    try:
        window = int(payload.get("window") or FIELDING_DEFAULT[mode])
    except (TypeError, ValueError):
        window = FIELDING_DEFAULT[mode]
    window = window if window in windows else FIELDING_DEFAULT[mode]
    names = {side: _team_name(app, mode, payload.get(key)) for side, key in (("bat", "batting"), ("chase", "chasing"))}
    out: dict[str, Any] = {"available": bool(log), "mode": mode, "format": fmt, "window": window, "windows": list(windows),
                           "note": "Dropped catches aren't recorded in the ball-by-ball data, so this shows catches taken, "
                                   "run-outs and stumpings, compared with the average side. Drop % is measured from drops "
                                   "you log with the Drop button while watching; until then it's an estimate.", "teams": {}}
    if not log:
        return out
    if mode == "ipl":
        rows = [r for r in log if r["kind"] == "club" and r["format"] == "t20"]
        seasons = sorted({r["season"] for r in rows}, reverse=True)[:window]
        rows = [r for r in rows if r["season"] in seasons]
        out["window_label"] = f"IPL {min(seasons)}–{max(seasons)}" if len(seasons) > 1 else f"IPL {seasons[0]}" if seasons else ""
        ipl_teams = {ml_model._team_key(p["name"]): code for code, p in app._team_bank("ipl").items()}
        by_team: dict[str, list] = {}
        for r in rows:
            if r["team"] in ipl_teams:
                by_team.setdefault(r["team"], []).append(r)
        table = [{"team": t, "code": ipl_teams[t], **_fielding_sum(rs)} for t, rs in by_team.items()]
        table.sort(key=lambda x: -(x["catches_pm"] or 0))
        for i, row in enumerate(table, 1):
            row["rank"] = i
        out["table"] = table
        out["benchmark"] = _fielding_sum([r for t, rs in by_team.items() for r in rs])
        out["benchmark_label"] = "IPL average"
        for side, name in names.items():
            key = ml_model._team_key(name)
            out["teams"][side] = {"name": name, **_fielding_sum(by_team.get(key, [])),
                                  "rank": next((x["rank"] for x in table if x["team"] == key), None), "of": len(table)}
        for row in table:
            row["drop_estimate"] = drops.estimate(row["catches_pm"], out["benchmark"]["catches_pm"], fmt)
    else:
        rows = [r for r in log if r["kind"] == "international" and r["format"] == fmt]
        for side, name in names.items():
            key = ml_model._team_key(name)
            mine = [r for r in rows if r["team"] == key][-window:]
            out["teams"][side] = {"name": name, **_fielding_sum(mine)}
        # the yardstick: every full member's last `window` matches in this format
        from .ml_features import FULL_MEMBERS
        bench = []
        for team in FULL_MEMBERS:
            bench += [r for r in rows if r["team"] == team][-window:]
        out["benchmark"] = _fielding_sum(sorted(bench, key=lambda r: r["date"]))
        out["benchmark_label"] = "Full-member average"
        out["window_label"] = f"Last {window} {fmt.upper()} matches"
    # dropped catches: measured from your logged matches, else an estimate (clearly marked)
    for side, t in out["teams"].items():
        key = ml_model._team_key(t["name"])
        t["drops"] = drops.team_stats(key, fmt, log)
        t["drop_estimate"] = drops.estimate(t.get("catches_pm"), (out.get("benchmark") or {}).get("catches_pm"), fmt)
    return out


def _team_name(app: ModuleType, mode: str, code: str | None) -> str:
    preset = app._team_bank(mode).get(code or "")
    return preset["name"] if preset else (code or "")


def player_insights(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """Form for both XIs plus every batter-v-bowler pairing with history (both directions)."""
    from . import insights

    mode = app._mode_key(payload.get("mode"))
    fmt = payload.get("format") if payload.get("format") in {"t20", "odi"} else "t20"
    bat_team = _team_name(app, mode, payload.get("batting"))
    chase_team = _team_name(app, mode, payload.get("chasing"))
    bat_xi = list(payload.get("batting_xi") or [])[:11]
    chase_xi = list(payload.get("chasing_xi") or [])[:11]
    return {
        "format": fmt,
        "batting_team": bat_team,
        "chasing_team": chase_team,
        "form": {
            "bat": [insights.form(n, bat_team) for n in bat_xi],
            "chase": [insights.form(n, chase_team) for n in chase_xi],
        },
        "battles": {
            "bat_v_chase": insights.key_battles(bat_xi, bat_team, chase_xi, chase_team, fmt),
            "chase_v_bat": insights.key_battles(chase_xi, chase_team, bat_xi, bat_team, fmt),
        },
    }


def compare_players(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """Two players side by side: career, last 10, phases, record at the selected ground, and against each other."""
    from . import insights

    mode = app._mode_key(payload.get("mode"))
    fmt = payload.get("format") if payload.get("format") in {"t20", "odi"} else "t20"
    loaded = ml_model.load_store() or {}
    store = loaded.get("store", {})
    venue = app._venue_bank(mode).get(str(payload.get("venue") or "")) or {}
    vkey = venue.get("_key")
    data = insights._load() or {}
    vfields = data.get("venue_player_fields", [])
    vtable = data.get("venue_players", {}).get(fmt, {})

    def one(spec: dict[str, Any]) -> dict[str, Any]:
        name = str(spec.get("name") or "")
        team = _team_name(app, mode, spec.get("team"))
        pid = ml_model.resolve_id(name, fmt, team)
        c = store.get("players", {}).get(fmt, {}).get(pid) if pid else None
        out: dict[str, Any] = {"name": name, "team": team, "team_code": spec.get("team"), "found": bool(c)}
        if c:
            out["career"] = {
                "matches": c.get("matches", 0), "runs": c.get("runs", 0), "balls": c.get("balls", 0),
                "average": round(c["runs"] / c["outs"], 1) if c.get("outs") else None,
                "strike_rate": round(c["runs"] * 100 / c["balls"], 1) if c.get("balls") else None,
                "wickets": c.get("wickets", 0), "overs": round(c.get("balls_bowled", 0) / 6, 1),
                "economy": round(c["runs_conceded"] * 6 / c["balls_bowled"], 2) if c.get("balls_bowled") else None,
                "bowl_avg": round(c["runs_conceded"] / c["wickets"], 1) if c.get("wickets") else None,
                "usual_position": round(c["pos_sum"] / c["pos_n"], 1) if c.get("pos_n") else None,
            }
        f = insights.form(name, team)
        out["form"] = {k: (f.get(fmt) or {}).get(k) for k in ("bat_summary", "bowl_summary")} if f.get("found") else None
        ph = insights.phase_rows([name], team, fmt)[0]
        out["phases"] = {"bat": ph["bat"], "bowl": ph["bowl"], "bats": ph["bats"], "bowls": ph["bowls"]}
        raw = vtable.get(f"{pid}|{vkey}") if pid and vkey else None
        out["venue"] = dict(zip(vfields, raw)) if raw else None
        return out

    # each player is {"name", "team"} (the page); a plain name is accepted too
    a, b = ({"name": str(x)} if isinstance(x, str) else x if isinstance(x, dict) else {} for x in (payload.get("a"), payload.get("b")))
    pa, pb = one(a), one(b)
    vs = {
        "a_bats": insights.head_to_head(pa["name"], pa["team"], pb["name"], pb["team"]).get(fmt),
        "b_bats": insights.head_to_head(pb["name"], pb["team"], pa["name"], pa["team"]).get(fmt),
    }
    return {"format": fmt, "venue": venue.get("name"), "a": pa, "b": pb, "vs": vs,
            "phase_labels": (["Powerplay", "Middle", "Death"])}


def venue_report(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """Everything about the selected ground: results, scoring by phase, toss, and the XIs' records there."""
    from . import insights

    mode = app._mode_key(payload.get("mode"))
    fmt = payload.get("format") if payload.get("format") in {"t20", "odi"} else "t20"
    code = str(payload.get("venue") or "")
    if code.startswith("custom:"):
        return {"available": False, "name": code[7:], "reason": "This ground isn't in the match data yet."}
    venue = app._venue_bank(mode).get(code)
    if not venue:
        return {"available": False, "name": code, "reason": "Unknown ground."}
    key = venue.get("_key")
    kind = venue.get("_kind") or ("club" if mode == "ipl" else "international")
    if mode == "ipl" and fmt == "odi":
        kind = "international"  # IPL grounds' ODI history comes from internationals
    loaded = ml_model.load_store()
    store = (loaded or {}).get("store", {})
    stats = store.get("venue_stats", {}).get(kind, {}).get(key or "", {}).get(fmt)
    base = {"name": venue["name"], "city": venue.get("city", ""), "country": venue.get("country", ""),
            "format": fmt, "competition": "IPL" if kind == "club" else "internationals"}
    if not stats:
        return {**base, "available": False, "reason": f"No {fmt.upper()} {base['competition']} at this ground in the data yet."}

    n = stats["matches"]
    pf = store["venue_stats_fields"]["phase"]
    ph = dict(zip(pf, stats["phase"]))
    labels = ("Powerplay (1–6)", "Middle (7–15)", "Death (16–20)") if fmt == "t20" else ("Powerplay (1–10)", "Middle (11–40)", "Death (41–50)")
    phases = [{"label": labels[i], "runs": round(ph[f"{p}_runs"] / n, 1), "wickets": round(ph[f"{p}_wkts"] / n, 1)}
              for i, p in enumerate(("pp", "mid", "death"))]
    recent = [dict(zip(store["venue_stats_fields"]["recent"], r)) for r in reversed(stats["recent"])]

    # the ticked XIs' records at this ground
    data = insights._load() or {}
    fields = data.get("venue_player_fields", [])
    table = data.get("venue_players", {}).get(fmt, {})

    def player_rows(names: list[str], team_code: str | None) -> list[dict[str, Any]]:
        team_name = _team_name(app, mode, team_code)
        rows = []
        for name in names:
            pid = ml_model.resolve_id(name, fmt, team_name) or ml_model.resolve_id(name, "t20" if fmt == "odi" else "odi", team_name)
            raw = table.get(f"{pid}|{key}") if pid else None
            r = dict(zip(fields, raw)) if raw else None
            rows.append({
                "name": name,
                "played": bool(r),
                "innings": r["innings"] if r else 0,
                "runs": r["runs"] if r else 0,
                "average": round(r["runs"] / r["outs"], 1) if r and r["outs"] else None,
                "strike_rate": round(r["runs"] * 100 / r["balls"], 1) if r and r["balls"] else None,
                "best": r["best"] if r else None,
                "fifties": r["fifties"] if r else 0,
                "wickets": r["wickets"] if r else 0,
                "economy": round(r["runs_conceded"] * 6 / r["balls_bowled"], 2) if r and r["balls_bowled"] else None,
                "bowl_spells": r["spells"] if r else 0,
            })
        return rows

    return {
        **base,
        "available": True,
        "matches": n,
        "bat_first_win_pct": round(stats["bat_first_won"] * 100 / stats["decided"], 1) if stats["decided"] else None,
        "chase_win_pct": round((stats["decided"] - stats["bat_first_won"]) * 100 / stats["decided"], 1) if stats["decided"] else None,
        "avg_first": round(stats["first_total_sum"] / n),
        "par": round(app._venue_average_score(venue, fmt)),
        "highest": stats["highest"],
        "lowest_defended": stats["lowest_defended"],
        "highest_chased": stats["highest_chased"],
        "toss": {
            "winner_won_pct": round(stats["toss_winner_won"] * 100 / stats["toss_decided"], 1) if stats["toss_decided"] else None,
            "chose_bowl_pct": round(stats["toss_chose_bowl"] * 100 / stats["toss_decided"], 1) if stats["toss_decided"] else None,
        },
        "phases": phases,
        "recent": recent,
        "players": {
            "bat": player_rows(list(payload.get("batting_xi") or [])[:11], payload.get("batting")),
            "chase": player_rows(list(payload.get("chasing_xi") or [])[:11], payload.get("chasing")),
        },
        "teams": {"bat": _team_name(app, mode, payload.get("batting")), "chase": _team_name(app, mode, payload.get("chasing"))},
    }


def phase_stats(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """Powerplay / middle / death numbers for both ticked XIs, plus 'best at…' callouts."""
    from . import insights

    mode = app._mode_key(payload.get("mode"))
    fmt = payload.get("format") if payload.get("format") in {"t20", "odi"} else "t20"
    out: dict[str, Any] = {"format": fmt, "labels": (["Powerplay (1–6)", "Middle (7–15)", "Death (16–20)"] if fmt == "t20"
                                                    else ["Powerplay (1–10)", "Middle (11–40)", "Death (41–50)"]),
                           "min_bat_balls": insights.MIN_BAT_BALLS, "min_bowl_balls": insights.MIN_BOWL_BALLS, "teams": {}}
    for side, key, xi_key in (("bat", "batting", "batting_xi"), ("chase", "chasing", "chasing_xi")):
        team = _team_name(app, mode, payload.get(key))
        rows = insights.phase_rows(list(payload.get(xi_key) or [])[:11], team, fmt)
        out["teams"][side] = {"name": team, "rows": rows, "callouts": insights.phase_callouts(rows)}
    return out


def xi_read(app: ModuleType, payload: dict[str, Any], picture: bool = False) -> dict[str, Any]:
    """Playing XIs from a team sheet (pasted text, or a picture read by Windows): see xi_reader.py."""
    from . import pitch_report, xi_reader

    mode = app._mode_key(payload.get("mode"))
    fmt = payload.get("format") if payload.get("format") in {"t20", "odi"} else "t20"
    want = "chase" if payload.get("side") == "chase" else "bat"
    bank = app._team_bank(mode)
    teams = {}
    for side, key in (("bat", "batting"), ("chase", "chasing")):
        code = str(payload.get(key) or "")
        t = bank.get(code)
        if t:
            teams[side] = {"code": code, "name": t.get("name", code), "squad": [p["name"] for p in t.get("squad", [])]}
    if want not in teams:
        raise ValueError("Pick the team first.")
    text = pitch_report.image_text(str(payload.get("image") or "")) if picture else str(payload.get("text") or "")[:6000]
    if not text.strip():
        raise ValueError("Paste the team list first." if not picture else "No text found in that picture.")
    store = (ml_model.load_store() or {}).get("store") or {}

    def lookup(name: str, side: str) -> str | None:  # a player in the match data, outside this squad
        pid = ml_model.resolve_id(name, fmt, teams[side]["name"])
        return (store.get("player_names") or {}).get(pid) if pid else None

    out = xi_reader.read(text, teams, want, lookup)
    out["text"] = text
    out["from_picture"] = picture
    out["teams"] = {s: teams[s]["name"] for s in out["sides"]}
    out["codes"] = {s: teams[s]["code"] for s in out["sides"]}
    out["can_save_squad"] = False  # Big Bash keeps club squads you save from a team sheet
    return out


def toss_advice(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """Bat or bowl first? The model's pre-match chance for each team batting first and chasing (your pitch and dew
    calls included), plus how batting first has gone at this ground."""
    mode = app._mode_key(payload.get("mode"))
    a, b = payload.get("batting"), payload.get("chasing")
    base = {k: v for k, v in payload.items() if k not in ("batting_crease", "chasing_crease", "runs", "wickets", "overs", "save")}
    swapped = {**base, "batting": b, "chasing": a, "batting_xi": base.get("chasing_xi"), "chasing_xi": base.get("batting_xi"),
               "batting_impact": base.get("chasing_impact"), "chasing_impact": base.get("batting_impact"),
               "batting_order_set": base.get("chasing_order_set"), "chasing_order_set": base.get("batting_order_set")}
    _pk, dew_key = _conditions(payload)
    dew = settings.dew_shift(dew_key) or 0.0

    def bat_first(p: dict[str, Any]) -> float | None:
        v = _pre_match_chance(app, p)  # batting-first side's chance (pitch already in the par)
        if v is None:
            return None
        if dew:  # your dew call helps the chasing side, as in every prediction
            v = round(100 - _dew_shift(1 - v / 100, dew) * 100, 1)
        return v

    a_bat, b_bat = bat_first(base), bat_first(swapped)
    if a_bat is None or b_bat is None:
        return {"available": False}
    a_chase, b_chase = round(100 - b_bat, 1), round(100 - a_bat, 1)
    a_name, b_name = _team_name(app, mode, a), _team_name(app, mode, b)

    def pick(bat: float, chase: float) -> dict[str, Any]:
        edge = round(bat - chase, 1)
        return {"choice": "bat" if edge > 0 else "bowl", "edge": abs(edge), "close": abs(edge) < 2.0}

    venue = None
    try:
        v = venue_report(app, payload)
        if v.get("available"):
            venue = {"name": v.get("name"), "matches": v.get("matches"), "bat_first_win_pct": v.get("bat_first_win_pct"),
                     "chase_win_pct": v.get("chase_win_pct"), "toss": v.get("toss")}
    except Exception:  # noqa: BLE001 - the ground's record is extra context
        pass
    return {"available": True, "teams": {"a": {"code": a, "name": a_name, "bat": a_bat, "chase": a_chase, **pick(a_bat, a_chase)},
                                          "b": {"code": b, "name": b_name, "bat": b_bat, "chase": b_chase, **pick(b_bat, b_chase)}},
            "dew": DEW[dew_key][0] if dew else None, "venue": venue}


def _pre_match_chance(app: ModuleType, payload: dict[str, Any]) -> float | None:
    """Model's pre-match batting-first win chance (%) for the XIs in the payload."""
    try:
        context, _ = _build_context(app, {**payload, "runs": 0, "wickets": 0, "overs": 0, "par": payload.get("par")})
        built = ml_model.build_features(context)
        if built is None:
            return None
        return round(ml_model.predict_probability([built[0]])[0] * 100, 1)
    except Exception:  # noqa: BLE001 - the comparison is a nice-to-have
        return None


def suggest_xi(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """Strongest balanced XI for one side, with reasons, and the model's view of the change."""
    from . import selection

    mode = app._mode_key(payload.get("mode"))
    fmt = payload.get("format") if payload.get("format") in {"t20", "odi"} else "t20"
    side = "chase" if payload.get("side") == "chase" else "bat"
    own_key, opp_key = ("chasing", "batting") if side == "chase" else ("batting", "chasing")
    own_xi_key, opp_xi_key = ("chasing_xi", "batting_xi") if side == "chase" else ("batting_xi", "chasing_xi")
    preset = app._team_bank(mode).get(str(payload.get(own_key) or ""))
    if not preset:
        return {"available": False}
    opponent = _team_name(app, mode, payload.get(opp_key))
    opp_xi = list(payload.get(opp_xi_key) or [])[:11] or _team_default_xi(app, mode, payload.get(opp_key))
    foreign = None
    if mode == "ipl":
        national = {t["name"]: [p["name"] for p in t.get("squad", [])] for t in app._team_bank("international").values()}
        foreign = selection.foreign_players(national, ml_model.load_store() or {})
    out = selection.suggest(preset.get("squad", []), preset["name"], opponent, opp_xi, fmt, is_ipl=mode == "ipl", foreign=foreign)
    if not out.get("available"):
        return out
    current = list(payload.get(own_xi_key) or [])[:11]
    out["side"] = side
    out["same_as_current"] = sorted(current) == sorted(out["xi"])
    out["changes"] = {"in": [n for n in out["xi"] if n not in current], "out": [n for n in current if n not in out["xi"]]}
    base = {**payload, opp_xi_key: opp_xi}
    now = _pre_match_chance(app, base) if len(current) == 11 else None
    new = _pre_match_chance(app, {**base, own_xi_key: out["xi"]})
    flip = (lambda v: None if v is None else round(100 - v, 1)) if side == "chase" else (lambda v: v)
    out["model_check"] = {"current": flip(now), "suggested": flip(new)}
    return out


def _par_key(payload: dict[str, Any]) -> str:
    return json.dumps({k: v for k, v in payload.items() if k not in ("runs", "wickets", "overs", "save")}, sort_keys=True, default=str)


def _warm_par(app: ModuleType, payload: dict[str, Any], kind: str) -> None:
    """Start working out the par-by-wickets grid as soon as a prediction comes in, so the page doesn't wait for it."""
    from . import par_grid as pg

    if payload.get("_no_warm"):  # the start-up practice run only loads things; it mustn't start heavy grid work
        return
    base = {k: v for k, v in payload.items() if k not in ("runs", "wickets", "overs", "save")}
    todo = [{**base, "kind": kind, "even": even} for even in (False, True)]
    todo = [r for r in todo if not pg.is_fresh(_par_key(r))]
    if todo:
        threading.Thread(target=lambda: [par_grid(app, r) for r in todo], daemon=True, name="par-warm").start()


def par_grid(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """Par by wickets: the 50/50 score for every over and number of wickets down (first innings or chase)."""
    from . import par_grid as pg

    fmt = payload.get("format") if payload.get("format") in {"t20", "odi"} else "t20"
    kind = "chase" if payload.get("kind") == "chase" else "first"
    _pk, dew_key = _conditions(payload)
    dew = settings.dew_shift(dew_key) or 0.0
    if kind == "chase":
        target = max(1, min(800, int(payload.get("target") or 1)))
        ctx_payload = {**payload, "runs": target - 1, "wickets": 10, "overs": FORMAT_MAX_BALLS[fmt] / 6, "save": False}
    else:
        target = None
        ctx_payload = {**payload, "runs": 0, "wickets": 0, "overs": 0, "save": False}
    key = _par_key(payload)

    def make():
        context, _ = _build_context(app, ctx_payload)
        even = bool(payload.get("even"))
        return pg.chase(context, target, dew=dew, even=even) if kind == "chase" else pg.first_innings(context, dew=dew, even=even)

    out = pg.cached(key, make)
    return out or {"kind": kind, "grid": None}


def resources(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """Batters still to come and the bowlers' overs left, for the result panels."""
    from . import resources as res
    return res.resources(app, payload, _team_name)


def scorecard(app: ModuleType) -> dict[str, Any]:
    """Home-page scorecard: per competition and season on unseen matches, plus your saved predictions' record."""

    try:
        out = json.loads((ML_DIR / "scorecard.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        out = {"groups": {}}
    try:
        _items, summary = _with_model_checks(app)
        out["yours"] = summary.get("all")
    except Exception:  # noqa: BLE001 - your record is a nice-to-have
        out["yours"] = None
    return out


def phase_par() -> dict[str, Any]:
    """Over-by-over par curves (scripts/phase_par.py): share of the total and wickets down after each over."""
    path = ROOT / "data" / "ml" / "phase_par.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"groups": {}}


def photos() -> dict[str, str]:
    """Photos for the page: {"hero": url, "ipl:hero": url, "logo:CSK": url, ...}.

    Theme-edited copies (web/img/theme) win over files dropped straight into web/img. "ipl:" photos are shown
    while the IPL switch is on; "logo:" entries are the cut-out team logos (scripts/team_logos.py).
    """
    out: dict[str, str] = {}
    ipl = WEB_DIR / "img" / "theme" / "ipl"
    if ipl.is_dir():
        for f in sorted(ipl.glob("*.jpg")):
            out[f"ipl:{f.stem.lower()}"] = f"/static/img/theme/ipl/{f.name}"
    logos = WEB_DIR / "img" / "logos"
    if logos.is_dir():
        for f in sorted(logos.glob("*.png")):
            out[f"logo:{f.stem.upper()}"] = f"/static/img/logos/{f.name}"
    # theme-edited copies (web/img/theme) first, then anything dropped straight into web/img
    for folder, prefix in ((WEB_DIR / "img" / "theme", "/static/img/theme/"), (WEB_DIR / "img", "/static/img/")):
        if not folder.is_dir():
            continue
        for ext in (".jpg", ".jpeg", ".webp", ".png", ".avif"):
            for f in sorted(folder.glob(f"*{ext}")):
                out.setdefault(f.stem.lower(), prefix + f.name)
    return out


def top_teams(app: ModuleType, mode: str) -> dict[str, Any]:
    """Home page: teams ranked by rating (Elo) with their last five T20 results."""
    from . import teams as team_data

    mode = app._mode_key(mode)
    loaded = ml_model.load_store()
    elo = ((loaded or {}).get("store", {}).get("elo", {}) or {}).get("t20", {})
    rows = []
    for code, preset in app._team_bank(mode).items():
        key = ml_model._team_key(preset["name"])
        if key not in elo:
            continue
        form = team_data.form(preset["name"], "t20", last=5)
        latest = preset.get("_latest_xi", {}).get("t20", {})
        rows.append({"code": code, "name": preset["name"], "elo": round(elo[key]),
                     "last5": [g["result"] for g in form["games"]], "win_pct": form["win_pct"],
                     "last_match": latest.get("date"), "squad": len(preset.get("squad", []))})
    rows.sort(key=lambda r: -r["elo"])
    return {"mode": mode, "teams": rows[:10]}


def team_record(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """Team head-to-head (all meetings in this format) plus each side's last 10 results."""
    from . import teams

    mode = app._mode_key(payload.get("mode"))
    fmt = payload.get("format") if payload.get("format") in {"t20", "odi"} else "t20"
    bat = _team_name(app, mode, payload.get("batting"))
    chase = _team_name(app, mode, payload.get("chasing"))
    venue = app._venue_bank(mode).get(str(payload.get("venue") or "")) or {}
    return {
        "h2h": teams.head_to_head(bat, chase, fmt, venue.get("_key")),
        "form": {"bat": teams.form(bat, fmt), "chase": teams.form(chase, fmt)},
        "venue": venue.get("name"),
        "format": fmt,
    }


def head_to_head(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    from . import insights

    mode = app._mode_key(payload.get("mode"))
    return insights.head_to_head(
        str(payload.get("batter") or ""), _team_name(app, mode, payload.get("batter_team")),
        str(payload.get("bowler") or ""), _team_name(app, mode, payload.get("bowler_team")),
    )


# --------------------------------------------------------------------------- history
def history(app: ModuleType) -> dict[str, Any]:
    """Saved predictions, each checked against the real result where one is known."""

    items, summary = _with_model_checks(app)  # your predictions + the model's checked matches, one per match
    # the model's own score on unseen matches, for comparison with yours
    bench: dict[str, float] = {}
    try:
        rep = json.loads((ML_DIR / "accuracy_report.json").read_text(encoding="utf-8"))
        allm = rep["by_competition"]["All matches"]
        for stage in ("pre_match", "mid_innings", "innings_break"):
            bench[stage] = round(allm[stage][rep["chosen"]]["accuracy"] * 100, 1)
        ch = json.loads((ML_DIR / "chase_accuracy.json").read_text(encoding="utf-8"))
        bench["chase"] = round(ch["overall"][ch["chosen"]]["accuracy"] * 100, 1)
    except (OSError, KeyError, ValueError):
        pass
    summary["tracker"]["model_pct"] = bench
    try:  # your pitch calls against what the first innings actually made
        from . import pitch_report
        summary["pitch"] = pitch_report.checks(items, lambda e: _usual_par(app, e))
    except Exception:  # noqa: BLE001 - an extra; History works without it
        logging.getLogger(__name__).warning("Pitch-call check failed", exc_info=True)
    return {"items": items, "summary": summary}


def _usual_par(app: ModuleType, entry: dict[str, Any]) -> int | None:
    """The ground's usual first-innings score for a saved prediction (before any pitch adjustment)."""
    setup = entry.get("setup") or {}
    mode = app._mode_key(setup.get("mode") or entry.get("mode"))
    fmt = str(setup.get("format") or entry.get("format") or "t20").lower()
    if fmt not in {"t20", "odi"}:
        return None
    code = str(setup.get("venue") or "")
    if not code:
        return None
    if code.startswith("custom:"):
        return _custom_par(mode).get(fmt)
    venue = app._venue_bank(mode).get(code)
    return round(app._venue_average_score(venue, fmt)) if venue else None


def set_result(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """Set (or clear) the real result of one saved prediction, found by its timestamp."""
    stamp = str(payload.get("timestamp") or "")
    winner = payload.get("winner")  # a team name, "No result", or None to clear and use the data again
    items = app._read_history()
    for entry in items:
        if entry.get("timestamp") == stamp:
            if winner:
                entry["actual"] = {"winner": str(winner), "note": "Result entered by you"}
            else:
                entry.pop("actual", None)
            break
    else:
        raise ValueError("That prediction wasn't found in your history.")
    app._write_history(items)
    return history(app)


def set_practice(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """Mark a saved prediction (and so its match) as a practice run, not counted, or as a real match."""
    stamp = str(payload.get("timestamp") or "")
    items = app._read_history()
    for entry in items:
        if entry.get("timestamp") == stamp:
            entry["practice"] = bool(payload.get("practice"))
            break
    else:
        raise ValueError("That prediction wasn't found in your history.")
    app._write_history(items)
    return history(app)


def delete_entry(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """Delete one saved prediction (found by its timestamp). The removed entry and its place in the list are sent
    back, so the page can offer Undo (restore_entries)."""
    stamp = str(payload.get("timestamp") or "")
    items = app._read_history()
    for i, entry in enumerate(items):
        if entry.get("timestamp") == stamp:
            del items[i]
            app._write_history(items)
            return {**history(app), "removed": [{"index": i, "entry": entry}]}
    raise ValueError("That prediction wasn't found in your history (maybe it was already deleted).")


def restore_entries(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """Undo for delete / clear: put the removed entries back where they were (skipping any already there)."""
    removed = payload.get("removed")
    if not isinstance(removed, list):
        raise ValueError("Nothing to restore.")
    items = app._read_history()
    have = {e.get("timestamp") for e in items}
    good = [r for r in removed[: app.HISTORY_LIMIT] if isinstance(r, dict) and isinstance(r.get("entry"), dict)
            and isinstance(r["entry"].get("timestamp"), str)]
    for r in sorted(good, key=lambda r: int(r.get("index") or 0)):
        entry = r["entry"]
        if entry["timestamp"] in have:
            continue
        idx = min(max(int(r.get("index") or 0), 0), len(items))
        items.insert(idx, entry)
        have.add(entry["timestamp"])
    app._write_history(items[: app.HISTORY_LIMIT])
    return history(app)


def history_backups(app: ModuleType) -> dict[str, Any]:
    """Saved copies of the predictions file, newest first (none in the online copy: its history lives in the browser)."""
    if getattr(app, "PUBLIC", False):
        return {"backups": []}
    folder = app.HISTORY_BACKUP_DIR
    out = []
    for f in sorted(folder.glob("history_*.json"), key=lambda x: x.stat().st_mtime, reverse=True) if folder.is_dir() else []:
        try:
            items = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(items, list):
            continue
        parts = f.stem.split("_")  # history_<date>[_<time>]_<why>
        why = {"daily": "Daily copy", "clear": "Before Clear all", "restore": "Before a restore"}.get(parts[-1], "Copy")
        when = parts[1] + (f" {parts[2][:2]}:{parts[2][2:4]}" if len(parts) > 3 and parts[2].isdigit() else "")
        out.append({"name": f.name, "when": when, "why": why, "count": len(items),
                    "latest": max((str(e.get("timestamp", "")) for e in items), default="")})
    return {"backups": out}


def restore_backup(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """Put a backup back as the saved predictions (the current list is backed up first, so this can be undone too)."""
    name = str(payload.get("name") or "")
    known = {b["name"] for b in history_backups(app)["backups"]}
    if name not in known:  # only a file from the list: never a path from the page
        raise ValueError("That backup wasn't found.")
    items = json.loads((app.HISTORY_BACKUP_DIR / name).read_text(encoding="utf-8"))
    app._backup_history(reason="before_restore")
    app._write_history(items[: app.HISTORY_LIMIT])
    return {**history(app), **history_backups(app), "restored": len(items)}


def clear_history(app: ModuleType) -> dict[str, Any]:
    items = app._read_history()
    app._write_history([])
    return {"items": [], "removed": [{"index": i, "entry": e} for i, e in enumerate(items)]}


# --------------------------------------------------------------------------- accuracy
def accuracy() -> dict[str, Any]:
    report_path = ML_DIR / "accuracy_report.json"
    history_path = ML_DIR / "accuracy_history.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
    versions = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else []
    chase_path = ML_DIR / "chase_accuracy.json"
    chase = json.loads(chase_path.read_text(encoding="utf-8")) if chase_path.exists() else None
    score_path = ML_DIR / "score_accuracy.json"
    score = json.loads(score_path.read_text(encoding="utf-8")) if score_path.exists() else None
    return {"report": report, "versions": versions, "chase": chase, "score": score}


# --------------------------------------------------------------------------- data status + retrain
class Retrainer:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.state: dict[str, Any] = {"state": "idle", "step": "", "log": [], "started_at": None, "finished_at": None}

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {**self.state, "log": self.state["log"][-12:]}

    def start(self, download: bool = False, label: str = "Retrained from the app") -> dict[str, Any]:
        """download=True: fetch the newest Cricsheet files first, and stop there if nothing is new."""
        if download:
            try:  # the app's own daily download writes the same files: don't run both at once
                from .update_service import UPDATE_SERVICE
                if UPDATE_SERVICE._state.state == "running":
                    return {**self.snapshot(), "error": "A data download is already running; try again in a minute."}
            except Exception:  # noqa: BLE001
                pass
        with self.lock:
            if self.state["state"] == "running":
                return {**self.state, "log": self.state["log"][-12:]}
            first = "Downloading the newest matches" if download else "Building training data"
            self.state = {"state": "running", "step": first, "log": [], "started_at": time.time(), "finished_at": None,
                          "mode": "update" if download else "retrain"}
        threading.Thread(target=self._run, args=(download, label), daemon=True, name="retrain").start()
        return self.snapshot()

    def _run(self, download: bool = False, label_text: str = "Retrained from the app") -> None:
        steps = [
            ("Building training data (a few minutes)", [sys.executable, str(ROOT / "scripts" / "build_training_data.py")]),
            ("Rating every player before every match (a few minutes)", [sys.executable, str(ROOT / "scripts" / "build_player_ratings.py")]),
            ("Measuring phase par (how innings are built, over by over)", [sys.executable, str(ROOT / "scripts" / "phase_par.py")]),
            ("Training and testing the first-innings model (about a minute)", [sys.executable, str(ROOT / "scripts" / "train_win_model.py"), label_text]),
            ("Training and testing the live chase model (about a minute)", [sys.executable, str(ROOT / "scripts" / "train_chase_model.py"), label_text]),
            ("Training and testing the projected-score model (about a minute)", [sys.executable, str(ROOT / "scripts" / "train_score_model.py"), label_text]),
            ("Scoring the models on unseen matches, season by season", [sys.executable, str(ROOT / "scripts" / "scorecard.py")]),
            ("Measuring how often each trust level was right", [sys.executable, str(ROOT / "scripts" / "trust_levels.py")]),
        ]
        if download:
            steps.insert(0, ("Downloading the newest matches from Cricsheet", [sys.executable, str(ROOT / "scripts" / "download_data.py")]))
        # step_no / steps let the Data page show "Step 5 of 8" and a bar of the steps done (step_no = steps + 1 while
        # the new models are loaded at the end)
        for no, (label, cmd) in enumerate(steps, 1):
            with self.lock:
                self.state.update(step=label, step_no=no, steps=len(steps))
            proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    with self.lock:
                        self.state["log"].append(line)
            if proc.wait() != 0:
                with self.lock:
                    self.state.update(state="error", step=f"Failed: {label}", finished_at=time.time())
                return
            if download and cmd[-1].endswith("download_data.py"):
                with self.lock:
                    unchanged = any(line.strip() == "CHANGED 0" for line in self.state["log"])
                if unchanged and (ROOT / "data" / "ml" / "win_model.joblib").exists():
                    with self.lock:
                        self.state.update(state="done", step="Already up to date: no new matches on Cricsheet", finished_at=time.time())
                    return
        with self.lock:
            self.state.update(step="Loading the new models into the app", step_no=len(steps) + 1)
        ml_model.reload()
        try:
            from . import player_ratings
            player_ratings.reload()
        except Exception:  # noqa: BLE001
            pass
        try:  # the Replay archive and its lists are prepared again for the new data / models, in the background
            from . import replay
            replay.refresh()
        except Exception:  # noqa: BLE001
            pass
        from . import chase_model, insights, score_model

        insights.reload()
        chase_model.reload()
        score_model.reload()
        with self.lock:
            self.state.update(state="done", step="Model retrained and loaded", finished_at=time.time())


RETRAINER = Retrainer()

# ---- automatic updates (Windows Task Scheduler runs scripts/auto_update.py every few days)
AUTO_TASK = "Crease IQ auto update"
AUTO_EVERY_DAYS = 3
AUTO_TIME = "07:30"
_auto_cache: dict[str, Any] = {"at": 0.0, "value": None}


def _pythonw() -> str:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def auto_schedule(force: bool = False) -> dict[str, Any]:
    """Is the scheduled task on, when does it run next, and how did the last run go?"""
    if not force and _auto_cache["value"] is not None and time.time() - _auto_cache["at"] < 30:
        return _auto_cache["value"]
    out: dict[str, Any] = {"supported": sys.platform == "win32", "enabled": False, "every_days": AUTO_EVERY_DAYS, "time": AUTO_TIME}
    if out["supported"]:
        try:
            q = subprocess.run(["schtasks", "/Query", "/TN", AUTO_TASK, "/FO", "LIST"], capture_output=True, text=True, timeout=15)
            if q.returncode == 0:
                out["enabled"] = True
                for line in q.stdout.splitlines():
                    if line.lower().startswith("next run time:"):
                        out["next_run"] = line.split(":", 1)[1].strip()
                    if line.lower().startswith("status:"):
                        out["task_status"] = line.split(":", 1)[1].strip()
        except (OSError, subprocess.SubprocessError):
            pass
    last = ROOT / "data" / "auto_update.json"
    if last.exists():
        try:
            out["last"] = json.loads(last.read_text(encoding="utf-8"))
        except ValueError:
            pass
    _auto_cache.update(at=time.time(), value=out)
    return out


def set_auto_schedule(enable: bool) -> dict[str, Any]:
    if sys.platform != "win32":
        return {**auto_schedule(True), "error": "Automatic updates use Windows Task Scheduler"}
    if enable:
        command = f'"{_pythonw()}" "{ROOT / "scripts" / "auto_update.py"}"'
        r = subprocess.run(["schtasks", "/Create", "/TN", AUTO_TASK, "/TR", command, "/SC", "DAILY", "/MO", str(AUTO_EVERY_DAYS),
                            "/ST", AUTO_TIME, "/F"], capture_output=True, text=True, timeout=30)
    else:
        r = subprocess.run(["schtasks", "/Delete", "/TN", AUTO_TASK, "/F"], capture_output=True, text=True, timeout=30)
    result = auto_schedule(True)
    if r.returncode != 0:
        result["error"] = (r.stderr or r.stdout).strip()
    return result


def _file_info(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    stat = path.stat()
    return {"name": path.name, "size_mb": round(stat.st_size / 1_048_576, 1),
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")}


def get_settings() -> dict[str, Any]:
    return {**settings.load(), "defaults": settings.DEFAULTS}


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    return settings.save(payload or {})


_ROWS_CACHE: dict[str, Any] = {}


_LIGHT_CACHE: dict[str, Any] = {}


def _players_tracked() -> int | None:
    """Count of players with a form record. Only counted once the 19 MB player file is loaded anyway (the
    background warm-up does that); until then the last count is reused, so the page never waits for it."""
    from . import insights
    if insights._load.cache_info().currsize:  # already in memory: free to count
        _LIGHT_CACHE["players"] = len((insights._load() or {}).get("form", {})) or None
    return _LIGHT_CACHE.get("players")


def _store_head() -> dict[str, Any]:
    """Match / state counts from the 9 MB feature store, read once per file version (not on every page load)."""
    path = ML_DIR / "feature_store.json"
    if not path.exists():
        return {}
    key = f"{path.stat().st_mtime}"
    if _LIGHT_CACHE.get("store_key") != key:
        try:
            with path.open(encoding="utf-8") as fh:
                head = json.load(fh)
            _LIGHT_CACHE["store"] = {"matches": head.get("built_from_matches"), "latest_match": head.get("latest_match_date"),
                                     "states": head.get("training_rows") or _count_rows(ML_DIR / "training_rows.csv.gz")}
        except (OSError, json.JSONDecodeError):
            _LIGHT_CACHE["store"] = {}
        _LIGHT_CACHE["store_key"] = key
    return _LIGHT_CACHE["store"]


def _home_ground(app, mode: str, team_code: str | None) -> str:
    """Starting ground for the Predict page: the busiest ground in the batting side's country that has hosted a match
    in the last three years (international only), else the fixed default."""
    fallback = app._default_venue_code(mode)
    if app._mode_key(mode) != "international" or not team_code:
        return fallback
    try:
        team = (app._team_bank(mode).get(team_code) or {}).get("name")
        bank = app._venue_bank(mode)
        lasts = [str(v.get("_last") or "") for v in bank.values() if v.get("_last")]
        if not team or not lasts:
            return fallback
        newest = max(lasts)
        cutoff = f"{int(newest[:4]) - 3}{newest[4:]}"
        home = [(v.get("_matches") or 0, code) for code, v in bank.items()
                if v.get("country") == team and str(v.get("_last") or "") >= cutoff]
        return max(home)[1] if home else fallback
    except Exception:  # noqa: BLE001 - only a nicer starting point
        return fallback


def _model_head() -> dict[str, Any]:
    """Which model, when trained, data up to: from the small accuracy report, so the page doesn't wait for the models
    to load (falls back to the loaded model only if the report is missing)."""
    try:
        rep_ = json.loads((ML_DIR / "accuracy_report.json").read_text(encoding="utf-8"))
        return {"chosen": rep_.get("chosen"), "trained_at": rep_.get("trained_at"), "data_through": rep_.get("data_through")}
    except (OSError, ValueError):
        return ml_model.model_info() or {}


def _count_rows(path: Path) -> int | None:
    """Match states in the training file (counted once per file version)."""
    if not path.exists():
        return None
    key = f"{path}|{path.stat().st_mtime}"
    if key not in _ROWS_CACHE:
        import gzip
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                count = max(0, sum(1 for _ in fh) - 1)
        except (OSError, EOFError):  # half-written file (an update was interrupted): no count, but the page still loads
            return None
        _ROWS_CACHE.clear()
        _ROWS_CACHE[key] = count
    return _ROWS_CACHE[key]


_HEALTH_CACHE: dict[str, Any] = {}


def _gz_lines(path: Path) -> tuple[bool, str]:
    """Is this .csv.gz complete? (Read to the end; the answer is kept until the file changes.)"""
    if not path.exists():
        return False, "missing"
    key = f"{path}|{path.stat().st_size}|{path.stat().st_mtime}"
    if key not in _HEALTH_CACHE:
        import gzip
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                n = sum(1 for _ in fh) - 1
            _HEALTH_CACHE[key] = (n > 0, f"{n:,} rows" if n > 0 else "empty")
        except (OSError, EOFError):
            _HEALTH_CACHE[key] = (False, "damaged (half-written: an update was interrupted)")
    return _HEALTH_CACHE[key]


def health() -> dict[str, Any]:
    """Data page health check: is every file the app needs present, complete and consistent? What to do if not."""
    from . import chase_model, score_model

    items: list[dict[str, Any]] = []

    def add(label: str, ok: bool, detail: str, key: str) -> None:
        items.append({"key": key, "label": label, "ok": bool(ok), "detail": detail})

    for key, label, name in (("rows", "Match history (first innings)", "training_rows.csv.gz"), ("chase_rows", "Match history (chases)", "chase_rows.csv.gz")):
        ok, detail = _gz_lines(ML_DIR / name)
        add(label, ok, detail, key)
    store = _store_head()
    add("Player and team records", bool(store.get("matches")), f"{int(store['matches']):,} matches, up to {store.get('latest_match')}" if store.get("matches") else "missing or unreadable", "store")
    try:
        k = json.loads((ML_DIR / "kalman_ratings.json").read_text(encoding="utf-8"))
        n_teams = sum(len(v) for v in k.get("teams", {}).values())
        add("Team ratings", n_teams > 0, f"{n_teams} teams rated", "ratings")
    except (OSError, ValueError):
        add("Team ratings", False, "missing or unreadable", "ratings")
    try:
        from . import player_ratings
        st = player_ratings.load_state()
        n_players = sum(len(v) for v in (st.get("players") or {}).values())
        ok_pr = player_ratings.MATCHES_PATH.exists() and n_players > 0
        add("Player ratings", ok_pr, f"{n_players:,} players rated" if ok_pr else "missing (Repair builds them)", "player_ratings")
    except Exception:  # noqa: BLE001
        add("Player ratings", False, "unreadable", "player_ratings")
    for key, label, mod in (("win", "Win model", ml_model), ("chase", "Live-chase model", chase_model), ("score", "Score projection model", score_model)):
        path = mod.MODEL_PATH
        if not path.exists():
            add(label, False, "missing", key)
            continue
        try:
            loaded = bool(mod.is_available()) if hasattr(mod, "is_available") else True
        except Exception:  # noqa: BLE001
            loaded = False
        add(label, loaded, f"trained {datetime.fromtimestamp(path.stat().st_mtime):%Y-%m-%d %H:%M}" if loaded else "won't load", key)
    leftovers = [f.name for f in ML_DIR.glob("*.tmp")]
    add("No interrupted update left behind", not leftovers, "clean" if not leftovers else "leftover files: " + ", ".join(leftovers[:3]), "leftovers")
    rt = RETRAINER.snapshot()
    bad = [i for i in items if not i["ok"]]
    # an interrupted build's leftover file is harmless by itself; anything else needs the rebuild
    need = [i for i in bad if i["key"] != "leftovers"]
    return {"ok": not bad, "needs_repair": bool(need), "items": items, "problems": len(bad),
            "running": rt.get("state") == "running", "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M")}


def status(update_snapshot: dict[str, Any]) -> dict[str, Any]:
    store_info = _store_head()
    info = _model_head()
    archives = [_file_info(ROOT / "data" / name) for name in ("cricsheet_ipl.zip", "cricsheet_t20s.zip", "cricsheet_odis.zip")]
    newest_archive = max((a["modified"] for a in archives if a), default=None)
    needs_retrain = bool(newest_archive and info.get("trained_at") and newest_archive > info["trained_at"])
    from . import backup
    return {
        "backup": backup.last(),  # the OneDrive copy of your personal files (Data page)
        "archives": [a for a in archives if a],
        "store": store_info,
        "model": {"label": ml_model.MODEL_LABELS.get(info.get("chosen", ""), info.get("chosen")),
                  "trained_at": info.get("trained_at"), "data_through": info.get("data_through"), "available": bool(info)},
        "needs_retrain": needs_retrain,
        "update": update_snapshot,
        "retrain": RETRAINER.snapshot(),
        "auto": auto_schedule(),
        "players_tracked": _players_tracked(),
        "cricsheet": _cricsheet_check(),
        "live": _live_status(),
    }


def _live_status() -> dict[str, Any]:
    try:
        from . import live_results
        return live_results.status(_known_teams())
    except Exception:  # noqa: BLE001 - optional extra
        return {"enabled": False}


def _known_teams() -> set[str] | None:
    """Team names in the app's IPL and international lists (so the Data page skips domestic and minor-league games)."""
    import sys

    app = sys.modules.get("__main__")
    bank = getattr(app, "_team_bank", None)
    if not bank:
        return None
    try:
        return {t["name"] for mode in ("ipl", "international") for t in bank(mode).values() if t.get("name")}
    except Exception:  # noqa: BLE001
        return None


def replay_recent(app: ModuleType, newest: str | None, query: str = "", competition: str = "") -> list[dict[str, Any]]:
    """Matches newer than the replay archive, from CricketData's results (only the result, no ball-by-ball, so they
    can't be replayed yet): shown as cards at the top of Replay's Latest list until Cricsheet publishes them."""
    try:
        from . import live_results
        rows = live_results.load().get("matches", [])
        ipl = {t["name"] for t in app._team_bank("ipl").values()}
        intl = {t["name"] for t in app._team_bank("international").values()}
    except Exception:  # noqa: BLE001 - optional extra
        return []
    words = [w for w in str(query or "").lower().split() if w]
    out = []
    for m in rows:
        if m.get("women") or (newest and m["date"] <= newest):
            continue
        pair = {m["team1"], m["team2"]}
        comp = "ipl" if pair <= ipl else ("odi" if m.get("format") == "odi" else "t20i" if m.get("format") == "t20" else "") if pair <= intl else ""
        if not comp or (competition and comp != competition):
            continue
        text = f"{m['team1']} {m['team2']} {m['date']} {m.get('name', '')}".lower()
        if any(w not in text for w in words):
            continue
        out.append({"id": m.get("id") or "", "date": m["date"], "competition": comp, "team1": m["team1"], "team2": m["team2"],
                    "winner": m.get("winner"), "result": m.get("status") or "", "venue": m.get("venue") or "",
                    "name": m.get("name") or "", "has_check": bool(live_results.scorecard(m.get("id") or "")),
                    "shortened": bool(m.get("shortened"))})
    return sorted(out, key=lambda r: r["date"], reverse=True)[:20]


# ---- model check at the innings break, for a match newer than Cricsheet (from a CricketData scorecard)
def _fold(s: str) -> str:
    return " ".join("".join(ch for ch in str(s).lower() if ch.isalpha() or ch == " ").split())


def _match_player(name: str, squad: list[str]) -> str | None:
    """CricketData's 'Mitchell Marsh' -> the app's 'MR Marsh' (full name first, then surname + first initial)."""
    f = _fold(name)
    exact = [s for s in squad if _fold(s) == f]
    if exact:
        return exact[0]
    parts = f.split()
    if not parts:
        return None
    sur, ini = parts[-1], parts[0][0]
    close = [s for s in squad if _fold(s).split()[-1:] == [sur] and _fold(s)[:1] == ini]
    return close[0] if len(close) == 1 else None


def _xi_from_card(app: ModuleType, mode: str, fmt: str, code: str, players: list[str]) -> tuple[list[str], list[str], list[str]]:
    """(the XI in app names, CricketData names we couldn't match, players filled in from the team's latest XI)."""
    t = app._team_bank(mode).get(code) or {}
    squad = [p["name"] for p in t.get("squad", [])]
    xi, missing = [], []
    for n in players:
        m = _match_player(n, squad)
        if m and m not in xi:
            xi.append(m)
        elif not m and n not in missing:
            missing.append(n)
    latest = ((t.get("_latest_xi") or {}).get(fmt) or (t.get("_latest_xi") or {}).get("t20") or {}).get("xi") or _team_default_xi(app, mode, code)
    filled = [n for n in latest if n not in xi][: max(0, 11 - len(xi))]
    return (xi + filled)[:11], missing, filled


def innings_break_check(app: ModuleType, match_id: str) -> dict[str, Any]:
    """What the model said at the innings break of a recent match (first-innings total, both XIs, the ground), and
    whether it was right. Uses a saved CricketData scorecard only, so it costs no calls."""
    from . import live_results
    card = live_results.scorecard(match_id)
    if not card or len(card.get("innings") or []) < 2:
        return {"available": False}
    first, second = card["innings"][0], card["innings"][1]
    bat_name, chase_name = first["title"], second["title"]
    mode = None
    for md in ("ipl", "international"):
        names = {t["name"]: c for c, t in app._team_bank(md).items()}
        if bat_name in names and chase_name in names:
            mode, bat, chs = md, names[bat_name], names[chase_name]
            break
    if not mode:
        return {"available": False, "reason": "These teams aren't in the app"}
    fmt = "odi" if " odi" in card["name"].lower() or ", odi" in card["name"].lower() else "t20"
    max_overs = 50 if fmt == "odi" else 20
    venue = next((c for c, v in app._venue_bank(mode).items()
                  if v.get("name") and v["name"].lower() in str(card.get("venue") or "").lower()), None)
    bat_xi, bat_miss, bat_fill = _xi_from_card(app, mode, fmt, bat, [b["name"] for b in first["batting"]] + [w["name"] for w in second["bowling"]])
    chs_xi, chs_miss, chs_fill = _xi_from_card(app, mode, fmt, chs, [b["name"] for b in second["batting"]] + [w["name"] for w in first["bowling"]])
    wk = int(first.get("wickets") or 0)
    overs = first.get("overs") or max_overs
    if wk >= 10 or float(overs) >= max_overs:  # innings over: the "innings break" state
        overs = max_overs if wk < 10 else overs
    payload = {"mode": mode, "format": fmt, "batting": bat, "chasing": chs, "venue": venue or "", "save": False,
               "runs": int(first.get("runs") or 0), "wickets": min(10, wk), "overs": str(overs),
               "batting_xi": bat_xi, "chasing_xi": chs_xi, "_no_warm": True}
    r = predict(app, payload)
    bat_pct = float(r.get("batting_pct") or 50)
    pick = bat_name if bat_pct >= 50 else chase_name
    winner = card.get("winner") or ""
    return {
        "available": True, "format": fmt, "mode": mode, "batting": bat_name, "chasing": chase_name,
        "score": f"{first.get('runs')}/{first.get('wickets')}", "overs": first.get("overs"),
        "venue": card.get("venue") or "", "venue_found": bool(venue),
        "pick": pick, "pick_pct": round(max(bat_pct, 100 - bat_pct), 1), "bat_pct": round(bat_pct, 1),
        "winner": winner, "result": card.get("status") or "",
        "right": (pick.lower() == winner.lower()) if winner else None,
        "xi": {"bat": bat_xi, "chase": chs_xi},
        "filled": {"bat": bat_fill, "chase": chs_fill}, "unmatched": {"bat": bat_miss, "chase": chs_miss},
        "codes": {"mode": mode, "bat": bat, "chase": chs, "venue": venue or ""},  # for Open in Predict
        "toss": card.get("toss") or "", "wickets": min(10, wk),
        "second": {"title": second.get("title"), "runs": second.get("runs"), "wickets": second.get("wickets"),
                   "overs": second.get("overs")},
    }


def _is_shortened(match_id: str) -> bool:
    """Overs cut by rain (DLS / VJD targets, 'reduced to', 'N overs game'), from the result or the saved scorecard."""
    from . import live_results
    m = next((x for x in live_results.load().get("matches", []) if x.get("id") == str(match_id)), None)
    card = live_results.scorecard(match_id) or {}
    return bool((m and m.get("shortened")) or live_results.shortened(card.get("status")))


def cached_check(app: ModuleType, match_id: str) -> dict[str, Any]:
    """innings_break_check, saved per match and model version (rerun only after a retrain)."""
    from . import live_results
    if _is_shortened(match_id):  # rain-shortened: the models are for full-length matches (even if a check was saved)
        return {"available": False, "reason": "shortened"}
    stamp = str((_model_head() or {}).get("trained_at") or "")
    got = live_results.saved_check(match_id, stamp)
    if got:
        return got
    chk = innings_break_check(app, match_id)
    if chk.get("available"):
        live_results.save_check(match_id, chk, stamp)
    return chk


def model_check_entries(app: ModuleType, user_items: list[dict[str, Any]], include_archive: bool = True) -> list[dict[str, Any]]:
    """The model's checked matches (Last 5 / Check the model / the daily auto-check) as History entries: one per
    match, and none for a match you predicted yourself (your own prediction counts for that match instead)."""
    from datetime import timedelta as _td

    from . import live_results, ml_model, tracking
    try:
        matches = [m for m in live_results.load().get("matches", []) if m.get("winner") and live_results.scorecard(m["id"])]
    except Exception:  # noqa: BLE001 - optional extra
        return []
    key = ml_model._team_key

    def yours(m: dict[str, Any]) -> bool:
        played = tracking._d(m["date"])
        teams = {key(m["team1"]), key(m["team2"])}
        for e in user_items:
            made = tracking._d(e.get("timestamp"))
            if (made and played and {key(e.get("batting_first_team", "")), key(e.get("chasing_team", ""))} == teams
                    and made - _td(days=tracking.WINDOW_BEFORE) <= played <= made + _td(days=tracking.WINDOW_AFTER)):
                return True
        return False

    out, seen = [], set()
    for m in matches:
        if m["id"] in seen or yours(m):
            continue
        c = cached_check(app, m["id"])
        if not c.get("available") or c.get("right") is None:
            continue
        seen.add(m["id"])
        bat_pct = float(c.get("bat_pct") or 50)
        out.append({
            "timestamp": f"{m['date']} 00:00:00", "auto": True, "match_id": m["id"], "mode": c["mode"],
            "format": str(c["format"]).upper(), "batting_first_team": c["batting"], "chasing_team": c["chasing"],
            "first_innings_score": c["score"], "stage": "innings_break", "model": "Model check at the innings break",
            "predicted_winner": c["pick"], "batting_first_win_probability": round(bat_pct, 1),
            "chasing_win_probability": round(100 - bat_pct, 1),
            "actual": {"winner": c["winner"], "note": f"{c['result']} · model check, result from CricketData"},
        })
    if include_archive:  # matches you fetched from the downloaded data ("Fetch older matches into History")
        ids = set(_archive_ids())
        if ids:
            try:
                pool = [m for m in _archive_pool(app) if str(m["id"]) in ids]
            except Exception:  # noqa: BLE001 - the archive is an extra; History works without it
                pool = []
            mine = [e for e in user_items if not e.get("auto")]
            cd = list(out)
            for m in pool:
                e = _archive_entry(m)
                if not any(_same_match(e, x) for x in cd) and not any(_same_match(e, x) for x in mine):
                    out.append(e)
    return out


# which part of History the page is showing: "both" (default), "yours" (your own predictions) or "model" (the model's
# checks). Set per request from the page's switch, so the record, tracker and pies follow it.
_VIEW = threading.local()


def set_view(source: Any) -> None:
    _VIEW.source = source if source in ("yours", "model") else "both"


def _with_model_checks(app: ModuleType) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Your saved predictions plus the model's checked matches, through the same record (one per match)."""
    from . import tracking
    user = app._read_history()
    source = getattr(_VIEW, "source", "both")
    checks = [] if source == "yours" else model_check_entries(app, user)
    items, summary = tracking.enrich((user if source != "model" else []) + checks)
    summary["view"] = source
    for e in items:
        if e.get("auto"):
            e["outcome"] = {**e["outcome"], "source": "model"}
    summary["model_checks"] = sum(1 for e in items if e.get("auto"))
    return items, summary


AUTO_RESERVE = 20  # the daily auto-check stops 20 calls short of the app's limit, leaving those for your own clicks


def auto_check(app: ModuleType) -> dict[str, Any]:
    """Once a day: find the matches played since the ball-by-ball data ends (from each tour / league's schedule) and
    check the unchecked ones against the model, newest first, while the day's calls allow (about 10 each)."""
    from . import live_results, replay
    if not live_results.has_key():
        return {"note": "no key"}
    found = replay.search("", "", limit=1)
    if not found.get("ready"):
        return {"note": "archive not ready"}
    newest = found.get("newest") or "2000-01-01"
    wanted = {t["name"] for t in app._team_bank("international").values()} | {"indian premier league"}
    live_results.discover(newest, wanted)
    checked = 0
    for m in replay_recent(app, newest, "", ""):  # every competition, newest first
        if live_results._hits_left() < live_results.SCORECARD_COST + AUTO_RESERVE:
            break
        if m.get("winner") and not m.get("has_check") and not m.get("shortened"):
            if live_results.fetch_scorecard(m["id"]).get("card"):
                checked += 1
    for m in replay_recent(app, newest, "", ""):  # work out the checks now, so History opens quickly
        if m.get("has_check"):
            cached_check(app, m["id"])
    return {"note": f"checked {checked} new match{'es' if checked != 1 else ''}"}


def start_auto_check(app: ModuleType) -> None:
    """Run auto_check about a minute after the app starts and then every hour (it spends calls at most once a day
    per new match, and stops short of the daily limit)."""
    import os
    import threading as _th
    from . import live_results
    if os.environ.get("CREASE_NO_LIVE_RESULTS") or not live_results.has_key():
        return

    def loop() -> None:
        time.sleep(60)
        while True:
            try:
                auto_check(app)
            except Exception:  # noqa: BLE001 - a background helper never takes the app down
                pass
            time.sleep(3600)

    _th.Thread(target=loop, daemon=True, name="cricketdata-auto-check").start()


LAST5_KINDS = {"odi": "ODIs", "t20i": "T20 internationals", "ipl": "IPL"}


def last5(app: ModuleType, kind: str, fetch: bool = False) -> dict[str, Any]:
    """The model's innings-break call on the 5 most recent finished matches of one kind (ODIs, T20 internationals or
    IPL), and whether it was right. Matches in the ball-by-ball data cost nothing (the replay archive has the call);
    newer ones come from CricketData. fetch=True first looks for new matches (once a day) and checks the unchecked
    ones while the daily call budget allows (about 10 calls each)."""
    from . import live_results, replay
    kind = kind if kind in LAST5_KINDS else "odi"
    found = replay.search("", kind, limit=12)
    if not found.get("ready"):
        return {"ready": False}
    newest = found.get("newest")
    note = ""
    if fetch and live_results.has_key():
        wanted = ({"indian premier league"} if kind == "ipl"
                  else {t["name"] for t in app._team_bank("international").values()})
        note = live_results.discover(newest or "2000-01-01", wanted).get("note", "")
    recent = replay_recent(app, newest, "", kind)  # newer than the archive (CricketData), newest first
    if fetch:
        for m in recent[:5]:
            if not live_results.scorecard(m["id"]) and live_results._hits_left() >= live_results.SCORECARD_COST:
                got = live_results.fetch_scorecard(m["id"])
                note = got.get("error") or note
        recent = replay_recent(app, newest, "", kind)
    rows: list[dict[str, Any]] = []
    for m in recent:
        if len(rows) >= 5:
            break
        if not m.get("winner") or m.get("shortened"):  # abandoned / no result / rain-shortened: not checked, so it doesn't take one of the 5 places
            continue
        row = {"date": m["date"], "team1": m["team1"], "team2": m["team2"], "result": m["result"], "source": "cricketdata",
               "id": m["id"], "abandoned": not m.get("winner")}
        if m.get("has_check"):
            c = cached_check(app, m["id"])
            if c.get("available"):
                row.update({"bat": c["batting"], "score": c["score"], "pick": c["pick"], "pct": c["pick_pct"],
                            "winner": c["winner"], "right": c["right"]})
        rows.append(row)
    for m in found["matches"]:
        if len(rows) >= 5:
            break
        try:
            d = replay.replay(m["id"])
        except Exception:  # noqa: BLE001
            continue
        call = next((c for c in d.get("calls", []) if "innings break" in str(c.get("stage", "")).lower()), None)
        rows.append({"date": m["date"], "team1": m["bat"], "team2": m["chase"], "result": m["result"], "source": "archive",
                     "replay_id": m["id"], "bat": m["bat"], "score": str(m["total"]), "winner": m["winner"],
                     "pick": call and call["team"], "pct": call and call["pct"], "right": call and call["right"]})
    checked = [r for r in rows if r.get("right") is not None]
    st = live_results.status()
    return {"ready": True, "kind": kind, "label": LAST5_KINDS[kind], "rows": rows, "newest": newest,
            "right": sum(1 for r in checked if r["right"]), "checked": len(checked),
            "unchecked": sum(1 for r in rows if r["source"] == "cricketdata" and r.get("right") is None and not r["abandoned"]),
            "cost": live_results.SCORECARD_COST, "hits_today": st["hits_today"], "budget": st["budget"],
            "enabled": st.get("enabled", False), "note": note}


# ---- "Fetch older matches into History": each press walks further back through one kind of match, newest first,
# skipping matches already in History. Matches in the downloaded ball-by-ball data cost no calls (the archive already
# has the live model's innings-break call for each); only matches newer than that data use CricketData calls.
def _archive_path() -> Path:
    """Which matches you have fetched into History. A test copy (its own history file) keeps its own list."""
    if os.environ.get("CREASE_ARCHIVE_CHECKS_PATH"):
        return Path(os.environ["CREASE_ARCHIVE_CHECKS_PATH"])
    hist = os.environ.get("CRICKET_HISTORY_PATH")
    if hist:
        return Path(hist).with_name(Path(hist).stem + "_archive_checks.json")
    return ROOT / "data" / "archive_checks.json"


FREE_PER_PRESS = 20  # free matches added per press (so each press is one step back, as asked)


def _archive_ids() -> list[str]:
    try:
        return [str(x) for x in json.loads(_archive_path().read_text(encoding="utf-8")).get("ids", [])]
    except (OSError, ValueError, TypeError, AttributeError):
        return []


def _save_archive_ids(ids: list[str]) -> None:
    path = _archive_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"ids": sorted({str(x) for x in ids})}), encoding="utf-8")
    tmp.replace(path)


def _archive_pool(app: ModuleType, kind: str = "") -> list[dict[str, Any]]:
    """Matches in the downloaded data the model never trained on (2025 on), between teams in the app, that have the
    model's innings-break call: newest first."""
    from . import replay
    index = replay._quick_index()
    if not index or not any(m.get("m") for m in index[:50]):
        index = (replay._tables() or {}).get("index") or []
    key = ml_model._team_key
    teams = {md: {key(t["name"]) for t in app._team_bank(md).values()} for md in ("ipl", "international")}
    out = []
    for m in index:
        if not m.get("m") or m["date"] < replay.TEST_START or (kind and m["competition"] != kind):
            continue
        md = "ipl" if m["competition"] == "ipl" else "international"
        if {key(m["bat"]), key(m["chase"])} <= teams[md]:
            out.append(m)
    return sorted(out, key=lambda m: (m["date"], m["id"]), reverse=True)


def _archive_entry(m: dict[str, Any]) -> dict[str, Any]:
    """A History entry (model check) for an archive match, from the live model's innings-break call."""
    won = bool(m["bat_won"])
    right = not m["m"]["brk_wrong"]
    winner = m["bat"] if won else m["chase"]
    pick = winner if right else (m["chase"] if won else m["bat"])
    conf = float(m["m"]["brk_conf"])
    bat_pct = conf if pick == m["bat"] else 100 - conf
    return {
        "timestamp": f"{m['date']} 00:00:00", "auto": True, "match_id": f"cs:{m['id']}",
        "mode": "ipl" if m["competition"] == "ipl" else "international", "format": str(m["format"]).upper(),
        "batting_first_team": m["bat"], "chasing_team": m["chase"], "first_innings_score": m["total"],
        "stage": "innings_break", "model": "Model check at the innings break",
        "predicted_winner": pick, "batting_first_win_probability": round(bat_pct, 1),
        "chasing_win_probability": round(100 - bat_pct, 1),
        "actual": {"winner": winner, "note": f"{m['result']} · model check, from your downloaded match data"},
    }


def _same_match(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Two History entries for one match: same two teams and format, played within a day of each other."""
    from . import tracking
    key = ml_model._team_key
    if {key(a["batting_first_team"]), key(a["chasing_team"])} != {key(b["batting_first_team"]), key(b["chasing_team"])}:
        return False
    if str(a.get("format", "")).upper() != str(b.get("format", "")).upper():
        return False
    da, db = tracking._d(a.get("timestamp")), tracking._d(b.get("timestamp"))
    return bool(da and db and abs((da - db).days) <= 1)


def go_back(app: ModuleType, kind: str) -> dict[str, Any]:
    """One press of "Fetch older matches into History" for one kind (ODIs, T20 internationals or IPL)."""
    from . import live_results, replay
    kind = kind if kind in LAST5_KINDS else "odi"
    found = replay.search("", kind, limit=1)
    if not found.get("ready"):
        return {"ready": False}
    newest = found.get("newest") or "2000-01-01"
    paid, calls_before, note = 0, live_results.used_today(), ""
    # 1. matches newer than the downloaded data: CricketData, newest first, while today's calls last
    if live_results.has_key():
        wanted = ({"indian premier league"} if kind == "ipl" else {t["name"] for t in app._team_bank("international").values()})
        note = live_results.discover(newest, wanted).get("note", "") or ""
        for m in replay_recent(app, newest, "", kind):
            if not m.get("winner") or m.get("shortened") or m.get("has_check"):
                continue
            if live_results._hits_left() < live_results.SCORECARD_COST:
                note = "Today's CricketData calls are used up; newer matches will be checked after midnight."
                break
            got = live_results.fetch_scorecard(m["id"])
            if got.get("card"):
                paid += 1
            elif got.get("error"):
                note = got["error"]
                break
    # 2. older matches from the downloaded data: free, the next FREE_PER_PRESS not yet in History
    ids = _archive_ids()
    have = set(ids)
    pool = _archive_pool(app, kind)
    user = app._read_history()
    cd_checks = model_check_entries(app, user, include_archive=False)
    added: list[dict[str, Any]] = []
    for m in pool:
        if len(added) >= FREE_PER_PRESS:
            break
        if str(m["id"]) in have:
            continue
        e = _archive_entry(m)
        if any(_same_match(e, x) for x in cd_checks) or any(_same_match(e, x) for x in user if not x.get("auto")):
            have.add(str(m["id"]))  # already in History (a CricketData check or your own prediction): skip, don't count
            ids.append(str(m["id"]))
            continue
        ids.append(str(m["id"]))
        have.add(str(m["id"]))
        added.append(m)
    _save_archive_ids(ids)
    left = sum(1 for m in pool if str(m["id"]) not in have)
    right = sum(1 for m in added if not m["m"]["brk_wrong"])
    st = live_results.status()
    return {
        "ready": True, "kind": kind, "label": LAST5_KINDS[kind], "paid": paid,
        "calls": max(0, live_results.used_today() - calls_before), "free": len(added), "free_right": right,
        "from": added[0]["date"] if added else None, "to": added[-1]["date"] if added else None,
        "left": left, "in_history": sum(1 for m in pool if str(m["id"]) in have), "newest_data": newest,
        "hits_today": st["hits_today"], "budget": st["budget"], "enabled": st.get("enabled", False), "note": note,
    }


def live_check(app: ModuleType, match_id: str, fetch: bool = False) -> dict[str, Any]:
    """The innings-break model check for a recent match. Needs its CricketData scorecard: a saved one costs nothing;
    fetch=True gets it now (about 10 of the day's calls). The scorecard itself isn't shown, only what the check needs."""
    from . import live_results
    note, error = "", ""
    if _is_shortened(match_id):  # never spend calls on a rain-shortened match
        st = live_results.status()
        return {"check": {"available": False, "reason": "shortened"}, "error": "", "note": "",
                "hits_today": st["hits_today"], "budget": st["budget"], "cost": live_results.SCORECARD_COST}
    if fetch and not live_results.scorecard(match_id):
        got = live_results.fetch_scorecard(match_id)
        error, note = got.get("error") or "", got.get("note") or ""
    check = cached_check(app, match_id) if live_results.scorecard(match_id) else {"available": False}
    st = live_results.status()
    return {"check": check, "error": error, "note": note,
            "hits_today": st["hits_today"], "budget": st["budget"], "cost": live_results.SCORECARD_COST}


def live_refresh(payload: dict[str, Any]) -> dict[str, Any]:
    """'Check now' on the Data page: fetch CricketData's latest results (within the daily call budget)."""
    from . import live_results
    r = live_results.refresh(force=True)
    return {"note": r.get("note"), **live_results.status(_known_teams())}


def _cricsheet_check() -> dict[str, Any]:
    """When the app last asked Cricsheet for new files, and when Cricsheet last published one (written by
    scripts/download_data.py). Explains a gap between today and the latest match: Cricsheet publishes in batches."""
    try:
        d = json.loads((ROOT / "data" / "cricsheet_check.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    files = d.get("files") or {}
    return {"checked_at": d.get("checked_at"), "published": max(files.values()) if files else None}


# --------------------------------------------------------------------------- pre-match preview (12 Nov 2026)
_PREVIEW_CACHE: dict[str, Any] = {}


def _history_stats(mode: str, fmt: str) -> dict[str, Any]:
    """How matches like this usually go since 2021 (IPL, or internationals between full members), from the match log
    and the chase table: first-innings totals, how often chases succeed, how far failed chases fall short, and chases
    that turned (no model involved, just what happened)."""
    path = ML_DIR / "feature_store.json"
    key = (mode, fmt, path.stat().st_mtime if path.exists() else None)
    if key in _PREVIEW_CACHE:
        return _PREVIEW_CACHE[key]
    from .ml_features import FULL_MEMBERS
    kind = "club" if mode == "ipl" else "international"
    since = "2021-01-01"
    out: dict[str, Any] = {"since": since[:4], "competition": "IPL" if mode == "ipl" else f"{fmt.upper()} internationals"}
    log = ((ml_model.load_store() or {}).get("store") or {}).get("match_log", [])
    games = [m for m in log if m[1] == fmt and m[2] == kind and not m[7] and m[0] >= since and len(m[11]) == 2
             and (mode == "ipl" or (m[3] in FULL_MEMBERS and m[4] in FULL_MEMBERS))]
    if games:
        q = lambda arr, f: arr[min(len(arr) - 1, int(f * len(arr)))] if arr else None  # noqa: E731
        firsts = sorted(m[11][0][1] for m in games)
        chased = [m for m in games if m[5] and m[5] == m[11][1][0]]
        short = sorted(m[11][0][1] - m[11][1][1] for m in games if m[5] and m[5] == m[11][0][0])
        out.update({"matches": len(games), "chase_win_pct": round(len(chased) * 100 / len(games), 1),
                    "first_median": q(firsts, 0.5), "first_q25": q(firsts, 0.25), "first_q75": q(firsts, 0.75),
                    "short_median": q(short, 0.5), "short_q25": q(short, 0.25), "short_q75": q(short, 0.75)})
    try:  # chases at the halfway point (T20: 10 overs, ODI: 25)
        import pandas as pd
        df = pd.read_csv(ML_DIR / "chase_rows.csv.gz", usecols=["date", "is_ipl", "is_odi", "is_club", "batting_team", "chasing_team",
                                                               "balls", "runs", "wickets", "target", "label_chase_won"])
        half, hard, easy = (150, 8.0, 5.5) if fmt == "odi" else (60, 11.0, 8.0)
        d = df[(df["balls"] == half) & (df["date"] >= since) & (df["is_odi"] == int(fmt == "odi"))]
        d = d[d["is_ipl"] == 1] if mode == "ipl" else d[(d["is_club"] == 0) & d["batting_team"].isin(FULL_MEMBERS) & d["chasing_team"].isin(FULL_MEMBERS)]
        left = (300 if fmt == "odi" else 120) - half
        rrr = (d["target"] - d["runs"]) * 6 / left
        h, e = d[rrr >= hard], d[(rrr <= easy) & (d["wickets"] <= 2)]
        out["halfway_overs"] = half // 6
        out["comeback"] = {"n": int(len(h)), "won": int(h["label_chase_won"].sum()), "rate": hard}
        out["collapse"] = {"n": int(len(e)), "lost": int((1 - e["label_chase_won"]).sum()), "rate": easy}
    except Exception:  # noqa: BLE001 - extra context only
        pass
    _PREVIEW_CACHE[key] = out
    return out


def _pre_match_record(mode: str, fmt: str) -> dict[str, Any] | None:
    """How often the model's pre-match favourite actually won, on unseen 2025-26 matches (accuracy report)."""
    try:
        rep = json.loads((ML_DIR / "accuracy_report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    comp = "IPL" if mode == "ipl" else ("ODI · full members" if fmt == "odi" else "T20I · full members")
    row = (rep.get("by_competition", {}).get(comp, {}).get("pre_match") or {}).get(rep.get("chosen"))
    if not row:
        return None
    return {"competition": comp, "pct": round(row["accuracy"] * 100, 1), "matches": row.get("matches"), "test_period": rep.get("test_period")}


def match_preview(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """Before the first ball, for the batting order you picked: who wins (the pre-match model), the first-innings
    total and range, the chase from that total, and how often matches like this turned around. Nothing is saved."""
    mode = app._mode_key(payload.get("mode"))
    fmt = payload.get("format") if payload.get("format") in {"t20", "odi"} else "t20"
    a, b = payload.get("batting"), payload.get("chasing")
    if not a or not b or a == b:
        return {"available": False, "reason": "Pick two different teams."}
    base = {k: v for k, v in payload.items() if k not in ("runs", "wickets", "overs", "save", "batting_crease", "chasing_crease")}
    base.update(save=False, runs=0, wickets=0, overs=0, _no_warm=True)
    first = predict(app, base)  # batting side's pre-match chance (pitch + dew included) and the projected total at ball 0
    bat_pct = first["batting_pct"]
    proj = first.get("projection") or {}
    bat = {"code": a, "name": first["batting_team"]}
    chs = {"code": b, "name": first["chasing_team"]}
    chase_at = None
    if proj.get("mid"):
        def chance(total: int) -> float | None:
            try:
                return chase(app, {**base, "target": int(total) + 1}).get("chase_pct")
            except Exception:  # noqa: BLE001
                return None
        chase_at = {k: {"total": proj[k], "chase_pct": chance(proj[k])} for k in ("low", "mid", "high")}
    fav, lead = (bat, bat_pct) if bat_pct >= 50 else (chs, round(100 - bat_pct, 1))
    return {
        "available": True, "format": fmt, "mode": mode,
        "bat": {**bat, "win": round(bat_pct, 1)}, "chase": {**chs, "win": round(100 - bat_pct, 1)},
        "favourite": {**fav, "pct": lead},
        "first": proj or None, "chase_at": chase_at,
        "record": _pre_match_record(mode, fmt),
        "history": _history_stats(mode, fmt),
    }

def clear_fetched(app: ModuleType, kind: str = "") -> dict[str, Any]:
    """Take the matches Fetch older added for one kind back out of History (they can be fetched again any time).
    Only the list of fetched matches changes: your own predictions and CricketData checks are not touched."""
    ids = _archive_ids()
    mine = {str(m["id"]) for m in _archive_pool(app, kind)}
    keep = [i for i in ids if i not in mine]
    _save_archive_ids(keep)
    return {"removed": len(ids) - len(keep), "left": len(keep)}


# ---- "How honest are the percentages?" (Accuracy page): when the model said 50-60%, 60-70% ..., how often that side
# really won, on matches it never trained on. Before the match and at the innings break, per kind of match.
BANDS = ((50, 60), (60, 70), (70, 80), (80, 90), (90, 101))


def _band_rows(calls: list[tuple[float, bool]]) -> list[dict[str, Any]]:
    """calls: (the favourite's % as the model said it, did the favourite win)."""
    rows = []
    for lo, hi in BANDS:
        b = [(p, ok) for p, ok in calls if lo <= p < hi]
        if b:
            rows.append({"band": f"{lo}-{min(hi, 100)}%", "matches": len(b), "said": round(sum(p for p, _ in b) / len(b), 1),
                         "won": round(sum(1 for _, ok in b if ok) * 100 / len(b), 1)})
    return rows


def _index_calls(kind: str = "") -> dict[str, list[tuple[float, bool]]]:
    from . import replay
    index = replay._quick_index() or []
    rows = [m for m in index if m.get("m") and m["date"] >= replay.TEST_START and (not kind or m["competition"] == kind)]
    return {"pre_match": [(m["m"]["fav"], not m["m"]["upset"]) for m in rows],
            "innings_break": [(m["m"]["brk_conf"], not m["m"]["brk_wrong"]) for m in rows]}


def honesty(app: ModuleType) -> dict[str, Any]:
    kinds = [("", "All"), ("ipl", "IPL"), ("t20i", "T20 internationals"), ("odi", "ODIs")]
    stages = {}
    for stage, title in (("pre_match", "Before the match"), ("innings_break", "At the innings break")):
        cols = []
        for code, name in kinds:
            calls = _index_calls(code)[stage]
            cols.append({"name": name, "matches": len(calls), "rows": _band_rows(calls)})
        stages[stage] = {"title": title, "kinds": cols}
    from . import replay
    return {"stages": stages, "source": f"Unseen matches since {replay.TEST_START[:4]} (the model never trained on them)"}


# ---- Update squad (XI box): the players of the team's latest match on CricketData, and players added by name
def squad_update(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {"mode", "team", "add": [names]} or {"remove": name}. Added players stay in the team's squad."""
    mode = app._mode_key(payload.get("mode"))
    code = str(payload.get("team") or "")
    if code not in app._team_bank(mode):
        raise ValueError("Pick the team first.")
    data = app._squad_additions()
    names = data.setdefault(mode, {}).setdefault(code, [])
    if payload.get("remove"):
        gone = str(payload["remove"])
        data[mode][code] = [n for n in names if n != gone]
        note = f"{gone} taken out of the squad."
    else:
        squad = {p["name"] for p in app._team_bank(mode)[code]["squad"]}
        new = [str(n).strip() for n in (payload.get("add") or []) if str(n).strip()]
        fresh = [n for n in dict.fromkeys(new) if n not in squad and n not in names][:20]
        names.extend(fresh)
        note = f"Added to the squad: {', '.join(fresh)}." if fresh else "They're already in the squad."
    app._save_squad_additions(data)
    return {"ok": True, "note": note, "added": app._squad_additions().get(mode, {}).get(code, [])}


def latest_players(app: ModuleType, payload: dict[str, Any], fetch: bool = False) -> dict[str, Any]:
    """The players of the team's most recent match on CricketData (batters, and bowlers from the other innings), each
    matched to the squad. Uses a saved scorecard; fetch=True gets the latest match's scorecard (about 10 calls)."""
    from . import live_results
    mode = app._mode_key(payload.get("mode"))
    code = str(payload.get("team") or "")
    team = app._team_bank(mode).get(code)
    if not team:
        raise ValueError("Pick the team first.")
    name = team["name"]
    matches = sorted((m for m in live_results.load().get("matches", [])
                      if not m.get("women") and name in (m.get("team1"), m.get("team2"))), key=lambda m: m["date"], reverse=True)
    st = live_results.status()
    left = max(0, st["budget"] - st["hits_today"])
    if not matches:
        return {"found": False, "note": f"No recent {name} match on CricketData yet. Use Add a player instead.", "calls_left": left}
    latest = matches[0]
    if payload.get("older"):  # the newest match with a saved scorecard (costs nothing)
        latest = next((m for m in matches if live_results.scorecard(m["id"])), latest)
    card = live_results.scorecard(latest["id"])
    if not card and fetch:
        got = live_results.fetch_scorecard(latest["id"])
        if got.get("error"):
            return {"found": False, "note": got["error"], "calls_left": left}
        card = live_results.scorecard(latest["id"])
    if not card:
        saved = next((m for m in matches[1:] if live_results.scorecard(m["id"])), None)
        return {"found": False, "needs_fetch": True, "match": {"name": latest.get("name"), "date": latest["date"]},
                "older": {"name": saved.get("name"), "date": saved["date"]} if saved else None,
                "cost": live_results.SCORECARD_COST, "calls_left": left,
                "enabled": bool(st.get("enabled", False))}
    own = [i for i in card.get("innings", []) if i.get("title") == name]
    other = [i for i in card.get("innings", []) if i.get("title") != name]
    seen = [b["name"] for i in own for b in i.get("batting", [])] + [w["name"] for i in other for w in i.get("bowling", [])]
    squad = [p["name"] for p in team["squad"]]
    players = []
    for n in dict.fromkeys(seen):
        m = _match_player(n, squad)
        players.append({"name": n, "in_squad": m})
    return {"found": True, "match": {"name": card.get("name") or latest.get("name"), "date": card.get("date") or latest["date"],
                                     "result": card.get("status") or latest.get("status")},
            "players": players, "calls_left": max(0, live_results.status()["budget"] - live_results.status()["hits_today"])}
def official_squad(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    """The team's official IPL squad from Wikipedia (official_squads.py), each player matched to the app: in the
    squad already, in the match data (his record is used once added), or new (no record yet). Withdrawn players are
    listed apart and never offered. Nothing is saved here: the page adds the ones you tick (squad_update)."""
    from . import official_squads, xi_reader
    mode = app._mode_key(payload.get("mode"))
    code = str(payload.get("team") or "")
    team = app._team_bank(mode).get(code)
    if not team:
        raise ValueError("Pick the team first.")
    if mode != "ipl":
        return {"found": False, "note": "Official squads load automatically for IPL teams. For internationals, open the "
                                        "official squad page, copy or screenshot it, and use Team sheet."}
    got = official_squads.ipl_squad(team["name"])
    if not got.get("found"):
        return got
    squad = [p["name"] for p in team["squad"]]
    store = (ml_model.load_store() or {}).get("store") or {}
    players, withdrawn = [], []
    for p in got["players"]:
        if p["withdrawn"]:
            withdrawn.append(p["name"])
            continue
        best, strength, _ = xi_reader._best(p["name"], squad)
        mine = best if best and strength >= xi_reader.SURE else _match_player(p["name"], squad)
        if mine:
            players.append({"name": p["name"], "in_squad": mine, "status": "squad"})
            continue
        pid = ml_model.resolve_id(p["name"], "t20", team["name"])
        known = (store.get("player_names") or {}).get(pid) if pid else None
        players.append({"name": known or p["name"], "in_squad": None, "status": "data" if known else "new"})
    return {"found": True, "team": team["name"], "season": got["season"], "source": got["title"], "url": got["url"],
            "players": players, "withdrawn": withdrawn}


MODES = ("international", "ipl")
WOMEN_OK = False


def _discover(app: ModuleType, since: str, teams: set[str]) -> None:
    """A targeted search for this match's series (not the once-a-day scan, which may already have run today)."""
    from . import live_results
    ipl = {t["name"] for t in app._team_bank("ipl").values()}
    live_results.look_for(sorted(teams), "Indian Premier League" if teams and set(teams) <= ipl else None)


def _link_note(fmt: str, pct: float):
    return sure_odi_note(fmt, "innings_break", pct)



# ---- Check a match from a link (Replay): the link's own words say which match it is (the website isn't read); the
# match, its scorecard and the result come from CricketData, the check is the model's call at the innings break
def link_check(app: ModuleType, payload: dict[str, Any]) -> dict[str, Any]:
    from datetime import date as _date, timedelta as _td

    from . import live_results, match_link
    url = str(payload.get("url") or "").strip()
    if not url:
        raise ValueError("Paste the match link first.")
    names = sorted({t["name"] for md in MODES for t in app._team_bank(md).values()})
    info = match_link.parse(url, names)
    st = live_results.status()
    left = max(0, st["budget"] - st["hits_today"])
    base = {"link": {"teams": info["teams"], "match": info["match"], "women": info["women"]}, "calls_left": left,
            "enabled": bool(st.get("enabled", False)), "cost": live_results.SCORECARD_COST}
    if info["women"] and not WOMEN_OK:
        return {**base, "state": "unknown", "note": "That's a women's match: this app's models are for men's cricket"
                + (" (use the Big Bash app's WBBL side for WBBL matches)." if MODES != ("ipl",) else " (switch to WBBL at the top).")}
    if not info["women"] and WOMEN_OK:
        return {**base, "state": "unknown", "note": "That's a men's match: this is the WBBL side (switch to BBL at the top)."}
    if not info["teams"]:
        return {**base, "state": "unknown", "note": "This link doesn't name two teams the app knows (it needs a match "
                "page link with 'team-vs-team' in it, from ESPNcricinfo, Cricbuzz or similar)."}
    key = ml_model._team_key
    league_only = MODES == ("ipl",)  # Big Bash: each side's results are its own league only (no women's flag to check)
    m = match_link.find(info, live_results.load().get("matches", []), key, check_women=not league_only)
    if not m and payload.get("look") and live_results.has_key():
        since = (_date.today() - _td(days=45)).isoformat()
        _discover(app, since, set(info["teams"]))
        m = match_link.find(info, live_results.load().get("matches", []), key, check_women=not league_only)
    if not m:
        return {**base, "state": "not_found", "can_look": live_results.has_key(),
                "note": f"{' v '.join(info['teams'])}{' · ' + info['match'] if info['match'] else ''} isn't in the app's "
                        "list of recent CricketData results yet."}
    summary = {"id": m["id"], "name": m.get("name"), "date": m.get("date"), "result": m.get("status") or m.get("result"),
               "venue": m.get("venue")}
    if m.get("shortened") or _is_shortened(m["id"]):
        return {**base, "state": "shortened", "match": summary,
                "note": "Shortened by rain: the models are for full-length matches, so this one isn't checked."}
    if not m.get("winner") and "won" not in str(m.get("status") or "").lower():
        return {**base, "state": "not_finished", "match": summary, "note": "No result yet (still on, abandoned or a tie)."}
    if not live_results.scorecard(m["id"]):
        if not payload.get("fetch"):
            return {**base, "state": "needs_fetch", "match": summary}
        got = live_results.fetch_scorecard(m["id"])
        if not live_results.scorecard(m["id"]):
            return {**base, "state": "error", "match": summary, "note": got.get("error") or "Couldn't get the scorecard."}
    chk = innings_break_check(app, m["id"])
    if not chk.get("available"):
        return {**base, "state": "unsupported", "match": summary, "note": chk.get("reason") or "This match can't be checked."}
    pct = float(chk["pick_pct"])
    st = live_results.status()
    return {**base, "state": "ok", "match": summary, "check": chk, "calls_left": max(0, st["budget"] - st["hits_today"]),
            "trust": trust_level("win", "innings_break", chk["mode"], pct), "sure_note": _link_note(chk["format"], pct)}
