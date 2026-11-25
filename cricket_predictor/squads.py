"""Current squads and latest playing XIs, built from the match data.

The team presets in main.py were typed in by hand and go out of date. Here each
team's squad becomes: everyone who has actually played for it recently (most
appearances first), followed by the remaining hand-entered squad members
(marked as not recently picked). Names from the presets are kept where a preset
player matches a Cricsheet player; new players use their Cricsheet name.

"Recently" = within 12 months of the team's latest match for national teams,
and the latest season for IPL franchises.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from . import ml_model

WINDOW_DAYS = 365


def _store() -> dict[str, Any] | None:
    loaded = ml_model.load_store()
    return loaded["store"] if loaded else None


def _infer_role(pid: str, store: dict[str, Any]) -> str:
    """Batter / bowler / all-rounder / keeper from what the player actually does in matches."""
    stats = [store["players"][fam].get(pid) for fam in ("t20", "odi")]
    stats = [s for s in stats if s]
    matches = sum(s.get("matches", 0) for s in stats) or 1
    balls_faced = sum(s.get("balls", 0) for s in stats) / matches
    balls_bowled = sum(s.get("balls_bowled", 0) for s in stats) / matches
    stumpings = sum(s.get("stumpings", 0) for s in stats)
    if stumpings >= 1 and balls_bowled < 3:
        return "wicket_keeper"
    bowls = balls_bowled >= 9  # about 1.5 overs a game
    bats = balls_faced >= 10
    if bowls and bats:
        return "all_rounder"
    if bowls:
        return "bowler"
    return "batter"


def _as_date(text: str) -> date:
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return date.min


def build(preset: dict[str, Any], is_club: bool) -> dict[str, Any] | None:
    """Return {"squad": [...], "latest_xi": {"t20": {...}, "odi": {...}}} or None if no data."""
    store = _store()
    if not store:
        return None
    team = ml_model._team_key(preset["name"])
    recent = store.get("team_recent", {}).get(team)
    if not recent:
        return None
    entries = [(fam, e) for fam in ("t20", "odi") for e in recent.get(fam, [])]
    if not entries:
        return None
    latest = max(_as_date(e["date"]) for _, e in entries)
    if is_club:
        in_window = [(f, e) for f, e in entries if _as_date(e["date"]).year == latest.year]
    else:
        cutoff = latest - timedelta(days=WINDOW_DAYS)
        in_window = [(f, e) for f, e in entries if _as_date(e["date"]) >= cutoff]

    # Map Cricsheet ids back to the friendlier preset names where possible
    preset_by_id: dict[str, dict[str, Any]] = {}
    for p in preset.get("squad", []):
        for fam in ("t20", "odi"):
            pid = ml_model.resolve_id(p["name"], fam, preset["name"])
            if pid and pid not in preset_by_id:
                preset_by_id[pid] = p

    names = store.get("player_names", {})

    def display(pid: str) -> str:
        return preset_by_id[pid]["name"] if pid in preset_by_id else names.get(pid, pid)

    apps: dict[str, int] = {}
    last_seen: dict[str, str] = {}
    for _, e in in_window:
        for pid in e["xi"]:
            apps[pid] = apps.get(pid, 0) + 1
            last_seen[pid] = max(last_seen.get(pid, ""), e["date"])

    squad: list[dict[str, Any]] = []
    by_recency = sorted(apps, key=lambda p: last_seen[p], reverse=True)
    for pid in sorted(by_recency, key=lambda p: -apps[p]):  # most games first, then most recently picked
        role = preset_by_id[pid]["role"] if pid in preset_by_id else _infer_role(pid, store)
        squad.append({"name": display(pid), "role": role, "recent": True, "games": apps[pid], "last": last_seen[pid]})
    listed = {s["name"] for s in squad}
    for p in preset.get("squad", []):
        if p["name"] not in listed:
            squad.append({"name": p["name"], "role": p["role"], "recent": False, "games": 0, "last": None})

    latest_xi: dict[str, dict[str, Any]] = {}
    for fam in ("t20", "odi"):
        if recent.get(fam):
            last = recent[fam][-1]
            ids = list(last["xi"])
            impact = last.get("impact")
            if impact and impact.get("in") in ids and len(ids) > 11:
                ids.remove(impact["in"])  # the starting XI; the impact player is shown separately
            latest_xi[fam] = {
                "date": last["date"],
                "opponent": last["opponent"],
                "venue": last["venue"],
                "xi": [display(pid) for pid in ids[:11]],
            }
            if impact:
                latest_xi[fam]["impact"] = {"in": display(impact["in"]), "out": display(impact.get("out")) if impact.get("out") else None}
    window_label = f"{latest.year} season" if is_club else f"last 12 months (to {latest.isoformat()})"
    return {"squad": squad, "latest_xi": latest_xi, "window": window_label}
