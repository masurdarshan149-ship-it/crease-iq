"""Feature definitions shared by the training script and the live app.

Keeping them in one place guarantees the app builds exactly the same inputs
the model was trained on.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

FORMAT_MAX_BALLS = {"t20": 120, "odi": 300}
ELO_START = 1500.0
VENUE_SHRINK = 4.0  # pseudo-matches pulling a venue average toward the recent format average
VENUE_WINDOW = 15  # last N full first innings at a venue
GROUP_WINDOW = 150  # last N full first innings in the same format + competition type
GROUP_DEFAULT = {
    "t20|club": 165.0, "t20|league": 160.0, "t20|international": 160.0, "t20|associate": 140.0,
    "odi|international": 260.0, "odi|associate": 230.0, "odi|club": 250.0,
}

# ICC full members: matches between two of these form the "international" pool;
# any international match involving another side goes to the "associate" pool.
FULL_MEMBERS = {
    "India", "Australia", "England", "South Africa", "New Zealand", "Pakistan",
    "Sri Lanka", "West Indies", "Bangladesh", "Afghanistan", "Zimbabwe", "Ireland",
}


def competition_group(fam: str, team_type: str, teams: list[str]) -> str:
    if team_type == "club":
        return f"{fam}|club"          # the IPL
    if team_type == "league":
        return f"{fam}|league"        # other T20 leagues (training only)
    if len(teams) == 2 and all(t in FULL_MEMBERS for t in teams):
        return f"{fam}|international"
    return f"{fam}|associate"

# App preset venue name -> extra Cricsheet spellings (first part of the venue string)
VENUE_ALIASES: dict[str, list[str]] = {
    "Maharaja Yadavindra Singh Stadium": ["Maharaja Yadavindra Singh International Cricket Stadium"],
    "Ekana Cricket Stadium": ["Bharat Ratna Shri Atal Bihari Vajpayee Ekana Cricket Stadium"],
    "Rajiv Gandhi Intl. Stadium": ["Rajiv Gandhi International Stadium"],
    "PCA Stadium": ["Punjab Cricket Association IS Bindra Stadium", "Punjab Cricket Association Stadium"],
    "Arun Jaitley Stadium": ["Feroz Shah Kotla"],
    "Narendra Modi Stadium": ["Sardar Patel Stadium"],
    "Ageas Bowl": ["The Rose Bowl", "Rose Bowl", "Utilita Bowl"],
    "The Gabba": ["Brisbane Cricket Ground"],
    "Optus Stadium": ["Perth Stadium"],
    "The Oval": ["Kennington Oval"],
    "Sinhalese Sports Club": ["Sinhalese Sports Club Ground"],
    "Sheikh Zayed Stadium": ["Zayed Cricket Stadium"],
    "Barsapara Cricket Stadium": ["ACA Stadium"],
}
# Generic venue names shared by several grounds: also require the city to match
CITY_CHECKED_VENUES = {"nationalstadium", "nationalcricketstadium"}

# Prior (average-player) values used to shrink small samples
BAT_PRIOR = {
    "t20": {"avg": 18.0, "sr": 120.0},
    "odi": {"avg": 25.0, "sr": 78.0},
}
BOWL_PRIOR = {
    "t20": {"econ": 8.3},
    "odi": {"econ": 5.6},
}
PRIOR_OUTS = 3.0
PRIOR_BALLS_FACED = 60.0
PRIOR_BALLS_BOWLED = 120.0

TEAM_NAME_ALIASES: dict[str, list[str]] = {
    "Delhi Capitals": ["Delhi Capitals", "Delhi Daredevils"],
    "Punjab Kings": ["Punjab Kings", "Kings XI Punjab"],
    "Royal Challengers Bengaluru": ["Royal Challengers Bengaluru", "Royal Challengers Bangalore"],
    "Rising Pune Supergiant": ["Rising Pune Supergiant", "Rising Pune Supergiants"],
}

# Columns fed to the model, in order
FEATURE_COLUMNS = [
    "is_odi",
    "is_club",
    "is_ipl",
    "balls_left_frac",
    "runs",
    "wickets",
    "run_rate",
    "venue_avg",
    "runs_vs_par",
    # team strength: Kalman (state-space) rating gap + its uncertainty; replaced "elo_diff" on 10 Nov 2026
    # (scripts/kalman_experiment.py: better log loss at every stage on 2024 and on unseen 2025-26)
    "kal_diff",
    "kal_unc",
    # recency-weighted player ratings of both XIs (cricket_predictor/player_ratings.py), added 17 Nov 2026
    "prb_sr", "prb_bpd", "prb_ec", "prb_wk", "prc_sr", "prc_bpd", "prc_ec", "prc_wk",
    "bat_xi_bat",
    "bat_xi_bowl_econ",
    "bat_xi_exp",
    "chase_xi_bat",
    "chase_xi_bowl_econ",
    "chase_xi_exp",
    # "toss_bat_first" was tested on 7 Nov 2026 and removed: no gain on the 2024 tuning year
]


# ---- live chase (second innings) model ----
CHASE_FEATURE_COLUMNS = [
    "is_odi",
    "is_club",
    "is_ipl",
    "balls_left",
    "balls_left_frac",
    "runs_needed",
    "wickets_in_hand",
    "required_rate",
    "current_rate",
    "rate_gap",
    "target",
    "target_vs_par",
    "kal_diff_chase",  # Kalman rating gap from the chasing side (was "elo_diff_chase" until 10 Nov 2026)
    "kal_unc",
    "prb_sr", "prb_bpd", "prb_ec", "prb_wk", "prc_sr", "prc_bpd", "prc_ec", "prc_wk",  # player ratings (17 Nov 2026)
    "chase_xi_bat",
    "chase_xi_exp",
    "chase_xi_bowl_econ",
    "bat_xi_bat",
    "bat_xi_bowl_econ",
    "bat_xi_exp",
    # recent form (last 10 innings / spells): improved the 2024 tuning check (7 Nov 2026), so the chase model uses it
    "bat_xi_form_bat",
    "bat_xi_form_econ",
    "chase_xi_form_bat",
    "chase_xi_form_econ",
]


# ---- projected first-innings total ----
SCORE_FEATURE_COLUMNS = [
    "is_odi",
    "is_club",
    "is_ipl",
    "balls_left_frac",
    "runs",
    "wickets",
    "run_rate",
    "venue_avg",
    "runs_vs_par",
    "bat_xi_bat",
    "bat_xi_exp",
    "chase_xi_bowl_econ",
    "chase_xi_exp",
    "elo_diff",
]


_PHASE_CURVE: dict[str, Any] | None = None


def phase_curve(fam: str) -> dict[str, list[float]] | None:
    """Model's par curve (share of the total and wickets down after each over), from innings before 2022."""
    global _PHASE_CURVE
    if _PHASE_CURVE is None:
        try:
            import json as _json
            from pathlib import Path as _Path
            path = _Path(__file__).resolve().parents[1] / "data" / "ml" / "phase_par_model.json"
            _PHASE_CURVE = _json.loads(path.read_text(encoding="utf-8")).get("groups", {})
        except (OSError, ValueError):
            _PHASE_CURVE = {}
    return _PHASE_CURVE.get(fam)


def _curve_at(arr: list[float], balls: float) -> float:
    k = min(len(arr) - 1, int(balls // 6))
    if k >= len(arr) - 1:
        return arr[-1]
    return arr[k] + (arr[k + 1] - arr[k]) * ((balls - 6 * k) / 6.0)


def add_chase_derived(row: dict[str, Any]) -> dict[str, Any]:
    """Chase features from target, runs, wickets and balls (same for training and the live app)."""
    fam = "odi" if int(row["is_odi"]) else "t20"
    max_balls = FORMAT_MAX_BALLS[fam]
    balls = int(row["balls"])
    balls_left = max(1, max_balls - balls)
    runs_needed = int(row["target"]) - int(row["runs"])
    row["balls_left"] = balls_left
    row["balls_left_frac"] = round(balls_left / max_balls, 4)
    row["runs_needed"] = runs_needed
    row["wickets_in_hand"] = 10 - int(row["wickets"])
    row["required_rate"] = round(min(36.0, runs_needed * 6 / balls_left), 3)
    row["current_rate"] = round(int(row["runs"]) * 6 / balls, 3) if balls else 0.0
    # how far the required rate is above what the target itself needed from ball one
    row["rate_gap"] = round(row["required_rate"] - int(row["target"]) * 6 / max_balls, 3)
    row["target_vs_par"] = float(row["target"]) - 1 - float(row["venue_avg"])
    row["elo_diff_chase"] = -float(row["elo_diff"])
    if "kal_diff" in row:
        row["kal_diff_chase"] = -float(row["kal_diff"])
    curve = phase_curve(fam)
    if curve:  # where a normal innings would be on the way to this target, by real innings shape (not a straight line)
        row["chase_vs_path"] = round(int(row["runs"]) - float(row["target"]) * _curve_at(curve["share"], balls), 2)
        row["wkts_vs_phase_par"] = round(int(row["wickets"]) - _curve_at(curve["wkts"], balls), 3)
    return row


def normalize_name(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def normalize_venue(value: str) -> str:
    return normalize_name((value or "").split(",")[0])


# Grounds that changed name: old key -> current key, so each ground keeps one history
RENAMED_VENUE_KEYS = {
    "westpacstadium": "hnrystadium",
    "skystadium": "hnrystadium",
    "jadestadium": "amistadium",
    "lancasterpark": "amistadium",
    "subrataroysaharastadium": "maharashtracricketassociationstadium",
    "andhracricketassociationvisakhapatnamdistrictcricketassociationstadium": "dryrajasekharareddyacavdcacricketstadium",
}


def venue_key(venue: str, city: str = "") -> str:
    """Key for venue stats; generic names like 'National Stadium' get the city attached."""
    key = normalize_venue(venue)
    key = RENAMED_VENUE_KEYS.get(key, key)
    if key in CITY_CHECKED_VENUES:
        parts = [p.strip() for p in (venue or "").split(",")]
        place = city or (parts[-1] if len(parts) > 1 else "")
        key = f"{key}|{normalize_name(place)}"
    return key


def recent_venue_average(venue_totals: list[float], group_totals: list[float], group: str) -> float:
    """Mean of a venue's recent first-innings totals, shrunk toward the recent format average."""
    group_mean = sum(group_totals) / len(group_totals) if len(group_totals) >= 20 else GROUP_DEFAULT.get(group, 160.0)
    return (sum(venue_totals) + VENUE_SHRINK * group_mean) / (len(venue_totals) + VENUE_SHRINK)


def elo_expected(diff: float) -> float:
    return 1.0 / (1.0 + 10 ** (-diff / 400.0))


def player_bat_index(stats: dict[str, Any] | None, fam: str) -> float:
    prior = BAT_PRIOR[fam]
    runs = float(stats.get("runs", 0)) if stats else 0.0
    balls = float(stats.get("balls", 0)) if stats else 0.0
    outs = float(stats.get("outs", 0)) if stats else 0.0
    average = (runs + prior["avg"] * PRIOR_OUTS) / (outs + PRIOR_OUTS)
    strike_rate = (runs + prior["sr"] / 100.0 * PRIOR_BALLS_FACED) / (balls + PRIOR_BALLS_FACED) * 100.0
    return average * strike_rate / 100.0


def player_bowl_econ(stats: dict[str, Any] | None, fam: str) -> float:
    prior = BOWL_PRIOR[fam]["econ"]
    balls = float(stats.get("balls_bowled", 0)) if stats else 0.0
    conceded = float(stats.get("runs_conceded", 0)) if stats else 0.0
    return (conceded + prior / 6.0 * PRIOR_BALLS_BOWLED) / (balls + PRIOR_BALLS_BOWLED) * 6.0


def xi_features(players: Iterable[dict[str, Any] | None], fam: str) -> dict[str, float]:
    """Summarise a playing XI from each player's record *before* the match.

    bat       mean batting index of the best 7 batters (average x strike rate / 100)
    bowl_econ mean economy of the 5 most-used bowlers (lower is better)
    exp       mean log(1 + matches played) — experience of the XI
    Unknown players count as average-level debutants.
    """
    players = list(players)[:12]  # IPL 2023+: the impact player is a 12th name, giving extra batting/bowling depth
    while len(players) < 11:
        players.append(None)
    bat_values = sorted((player_bat_index(p, fam) for p in players), reverse=True)[:7]
    bowlers = sorted(players, key=lambda p: float(p.get("balls_bowled", 0)) if p else 0.0, reverse=True)[:5]
    bowl_values = [player_bowl_econ(p, fam) for p in bowlers]
    exp_values = [math.log1p(float(p.get("matches", 0))) if p else 0.0 for p in players]
    return {
        "bat": round(sum(bat_values) / len(bat_values), 3),
        "bowl_econ": round(sum(bowl_values) / len(bowl_values), 3),
        "exp": round(sum(exp_values) / len(exp_values), 3),
    }


# ---- who's in and who's left to bat (live-state features)
LINEUP_COLUMNS = ["bat_crease", "bat_next3"]
CHASE_LINEUP_COLUMNS = ["chase_crease", "chase_next3"]
DEFAULT_BAT_POS = 8.0  # a player with no batting record is assumed to bat low


def typical_position(stats: dict[str, Any] | None) -> float:
    """Average batting position so far (1 = opener)."""
    if stats and stats.get("pos_n"):
        return float(stats["pos_sum"]) / float(stats["pos_n"])
    return DEFAULT_BAT_POS


def lineup_features(crease: list[dict[str, Any] | None], upcoming: list[dict[str, Any] | None], fam: str) -> dict[str, float]:
    """crease = the two batters in; upcoming = batters still to come, in order.

    crease  mean batting index of the two batters at the crease (0 for an empty slot)
    next3   mean batting index of the next three to come (0 for each slot nobody is left for)
    """
    c = [player_bat_index(s, fam) for s in crease[:2]] + [0.0] * max(0, 2 - len(crease))
    n = [player_bat_index(s, fam) for s in upcoming[:3]] + [0.0] * max(0, 3 - len(upcoming))
    return {"crease": round(sum(c) / 2, 3), "next3": round(sum(n) / 3, 3)}


# ---- phase strength: death-overs hitting and bowling of an XI (from per-player phase totals, PHASE_FIELDS order)
PHASE_COLUMNS = ["bat_xi_death_sr", "bat_xi_death_econ", "chase_xi_death_sr", "chase_xi_death_econ"]
PHASE_PRIOR = {"t20": {"sr": 149.0, "econ": 9.2}, "odi": {"sr": 117.0, "econ": 7.2}}  # all-player averages
PHASE_K = 60.0  # balls of evidence before a player's own number counts as much as the average


def xi_death_features(rows: list[list | None], fam: str) -> dict[str, float]:
    """rows[i] = that player's 18 phase totals (bat pp/mid/death runs,balls,outs then bowl pp/mid/death balls,runs,wkts).

    sr    mean death strike rate of the 6 players who face most death balls (shrunk toward average)
    econ  mean death economy of the 4 players who bowl most death balls (shrunk toward average)
    """
    prior = PHASE_PRIOR[fam]
    vals = [r if r else [0] * 18 for r in list(rows)[:12]] + [[0] * 18] * max(0, 11 - len(rows))
    hitters = sorted(vals, key=lambda v: -v[7])[:6]
    bowlers = sorted(vals, key=lambda v: -v[15])[:4]
    sr = sum((v[6] + prior["sr"] / 100 * PHASE_K) / (v[7] + PHASE_K) * 100 for v in hitters) / len(hitters)
    econ = sum((v[16] + prior["econ"] / 6 * PHASE_K) / (v[15] + PHASE_K) * 6 for v in bowlers) / len(bowlers)
    return {"sr": round(sr, 2), "econ": round(econ, 3)}


SET_CAP = 30  # balls: after about 30 balls a batter counts as fully "in"


def crease_set(balls_faced: list[int]) -> float:
    """How set the two batters are, 0 (both new) to 1 (both on 30+ balls)."""
    b = [max(0, int(x)) for x in balls_faced[:2]] + [0] * max(0, 2 - len(balls_faced))
    return round(sum(min(x, SET_CAP) for x in b) / (2 * SET_CAP), 3)


def expected_set(table: dict[str, float], fam: str, balls: int, wickets: int) -> float:
    """The typical crease_set at this point of an innings (used when the app isn't told who is in)."""
    key = f"{fam}|{max(0, int(balls)) // 6}|{max(0, min(9, int(wickets)))}"
    return float(table.get(key, 0.35))


def app_lineup(players: list[dict[str, Any] | None], wickets: int, fam: str, ordered: bool = False) -> dict[str, float]:
    """Unless the user set the batting order (ordered=True: players are already in that order), the app uses each
    player's usual position: after w wickets the batters at positions w+1 and w+2 are taken to be in, and the ones
    after them still to come."""
    order = list(players) if ordered else sorted(players, key=typical_position)
    w = max(0, min(10, int(wickets)))
    return lineup_features(order[w:w + 2], order[w + 2:], fam)


def app_lineup_known(players: list[dict[str, Any] | None], crease: list[dict[str, Any] | None], wickets: int, fam: str,
                     ordered: bool = False) -> dict[str, float]:
    """Like app_lineup, but the two batters at the crease are known; the rest keep their order (the user's, or the
    usual one), with the top `wickets` of them taken to be out already."""
    rest = [p for p in players if all(p is not c for c in crease)]
    order = rest if ordered else sorted(rest, key=typical_position)
    w = max(0, min(10, int(wickets)))
    return lineup_features(crease[:2], order[w:], fam)


FORM_COLUMNS = ["bat_xi_form_bat", "bat_xi_form_econ", "chase_xi_form_bat", "chase_xi_form_econ"]
# leaner version: how much more in form than usual each side is (batting index up, economy down = better)
FORM_EDGE_COLUMNS = ["form_bat_edge", "form_bowl_edge"]


def add_form_edges(row: dict[str, Any]) -> dict[str, Any]:
    if "bat_xi_form_bat" in row:
        row["form_bat_edge"] = round((float(row["bat_xi_form_bat"]) - float(row["bat_xi_bat"]))
                                     - (float(row["chase_xi_form_bat"]) - float(row["chase_xi_bat"])), 3)
        # positive = the batting-first side's bowlers are in better form (relative to career) than the chasers'
        row["form_bowl_edge"] = round((float(row["chase_xi_form_econ"]) - float(row["chase_xi_bowl_econ"]))
                                      - (float(row["bat_xi_form_econ"]) - float(row["bat_xi_bowl_econ"])), 3)
    return row


def xi_recent_form(bat_entries: list[list | None], bowl_entries: list[list | None], fam: str) -> dict[str, float]:
    """Recent form of an XI from each player's last 10 innings / last 10 bowling spells.

    bat_entries[i]  = that player's recent innings rows [date, opponent, venue, runs, balls, out, 4s, 6s] (or None)
    bowl_entries[i] = recent spells [date, opponent, venue, balls, runs, wickets] (or None)
    Uses the same shrinkage as the career numbers, so a player with little recent cricket stays near average.
    bat  mean recent batting index of the best 7      econ  mean recent economy of the 5 busiest bowlers
    """
    bat_vals, bowl = [], []
    for inns in list(bat_entries)[:12] + [None] * max(0, 11 - len(bat_entries)):
        rows = inns or []
        bat_vals.append(player_bat_index({"runs": sum(r[3] for r in rows), "balls": sum(r[4] for r in rows),
                                          "outs": sum(r[5] for r in rows)}, fam))
    for spells in list(bowl_entries)[:12] + [None] * max(0, 11 - len(bowl_entries)):
        rows = spells or []
        bowl.append({"balls_bowled": sum(r[3] for r in rows), "runs_conceded": sum(r[4] for r in rows)})
    top_bat = sorted(bat_vals, reverse=True)[:7]
    busiest = sorted(bowl, key=lambda b: b["balls_bowled"], reverse=True)[:5]
    return {"bat": round(sum(top_bat) / len(top_bat), 3),
            "econ": round(sum(player_bowl_econ(b, fam) for b in busiest) / len(busiest), 3)}


def add_derived(row: dict[str, Any]) -> dict[str, Any]:
    """Add features computed from the raw state (used for training rows and live input)."""
    fam = "odi" if int(row["is_odi"]) else "t20"
    max_balls = FORMAT_MAX_BALLS[fam]
    balls_done = max_balls * (1.0 - float(row["balls_left_frac"]))
    # Par for this point in the innings: the venue average scaled by overs used
    row["runs_vs_par"] = float(row["runs"]) - float(row["venue_avg"]) * balls_done / max_balls
    curve = phase_curve(fam)
    if curve:  # the same, but with the real shape of an innings (slow middle, fast death)
        row["runs_vs_phase_par"] = round(float(row["runs"]) - float(row["venue_avg"]) * _curve_at(curve["share"], balls_done), 2)
        row["wkts_vs_phase_par"] = round(float(row["wickets"]) - _curve_at(curve["wkts"], balls_done), 3)
    return add_form_edges(row)
