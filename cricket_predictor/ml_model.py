"""Live predictions from the trained win model.

Loads data/ml/win_model.joblib (trained by scripts/train_win_model.py) and
data/ml/feature_store.json (built by scripts/build_training_data.py), turns a
MatchContext into the same features used in training, and returns a
PredictionResult. Returns None when the model can't be used (files missing,
libraries not installed, or a Test match) so the caller can fall back to the
original formula.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ml_features import (
    FORMAT_MAX_BALLS,
    FULL_MEMBERS,
    ELO_START,
    TEAM_NAME_ALIASES,
    VENUE_ALIASES,
    add_derived,
    normalize_name,
    venue_key,
    xi_features,
    xi_recent_form,
    app_lineup,
    app_lineup_known,
    crease_set,
    expected_set,
    xi_death_features,
    competition_group,
)
from .models import MatchContext
from . import kalman, player_ratings
from .once import locked_cache

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "data" / "ml" / "win_model.joblib"
STORE_PATH = ROOT / "data" / "ml" / "feature_store.json"

# Cricsheet spellings that the simple initials rule can't derive
MANUAL_NAME_ALIASES: dict[str, list[str]] = {
    "Virat Kohli": ["V Kohli"],
    "Rohit Sharma": ["RG Sharma"],
    "Surya Kumar Yadav": ["SA Yadav", "SK Yadav"],
    "Suryakumar Yadav": ["SA Yadav"],
    "Ruturaj Gaikwad": ["RD Gaikwad"],
    "Yashasvi Jaiswal": ["YBK Jaiswal"],
    "Phil Salt": ["PD Salt"],
    "Jasprit Bumrah": ["JJ Bumrah"],
    "Hardik Pandya": ["HH Pandya"],
    "Rishabh Pant": ["RR Pant"],
    "Mitchell Starc": ["MA Starc"],
    "Jos Buttler": ["JC Buttler"],
    "Travis Head": ["TM Head"],
    "Pat Cummins": ["PJ Cummins"],
    "Josh Hazlewood": ["JR Hazlewood"],
    "Shreyas Iyer": ["SS Iyer"],
    "Nitish Kumar Reddy": ["Nithish Kumar Reddy", "K Nitish Kumar Reddy"],
    "Varun Chakaravarthy": ["CV Varun"],
    "Varun Chakravarthy": ["CV Varun"],
    "Wanindu Hasaranga": ["PWH de Silva"],
    "Prabhsimran Singh": ["P Simran Singh"],
    "Kusal Mendis": ["BKG Mendis"],
    "Kamindu Mendis": ["PHKD Mendis"],
    "Kusal Perera": ["MDKJ Perera"],
    "Salman Agha": ["Agha Salman"],
    "Litton Das": ["Liton Das"],
    "Najmul Hossain Shanto": ["Nazmul Hossain Shanto"],
    "Mohammad Shami": ["Mohammed Shami"],
    "Sai Kishore": ["R Sai Kishore"],
    "Shahbaz Ahamad": ["Shahbaz Ahmed"],
    "Dushmantha Chameera": ["PVD Chameera"],
    "Rassie van der Dussen": ["HE van der Dussen"],
}

_TEAM_LOOKUP = {normalize_name(a): canonical for canonical, aliases in TEAM_NAME_ALIASES.items() for a in aliases}


@locked_cache  # one shared load even when several requests ask at once (see once.py)
def load_store() -> dict[str, Any] | None:
    """Just the feature store (team ratings, player stats, results) and the name look-ups - no model.

    Loading the model means importing LightGBM / scikit-learn, about 3.5 s on a cold start. The home page (team cards,
    squads, scorecard) only needs this store, so it no longer waits for that.
    """
    if not MODEL_PATH.exists() or not STORE_PATH.exists():
        return None
    store = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    by_name: dict[str, list[str]] = {}
    by_surname: dict[str, list[tuple[str, str]]] = {}  # surname -> [(initials, id)]
    for pid, name in store["player_names"].items():
        by_name.setdefault(normalize_name(name), []).append(pid)
        tokens = name.split()
        # Cricsheet style "MS Dhoni", "Q de Kock": leading all-caps token = initials
        if len(tokens) >= 2 and tokens[0].isupper() and tokens[0].isalpha() and len(tokens[0]) <= 4:
            by_surname.setdefault(normalize_name(" ".join(tokens[1:])), []).append((tokens[0], pid))
    return {"store": store, "by_name": by_name, "by_surname": by_surname}


@locked_cache
def _load() -> dict[str, Any] | None:
    """Model + feature store (what a prediction needs)."""
    base = load_store()
    if not base:
        return None
    try:
        import joblib  # noqa: F401  (also pulls in lightgbm when unpickling)

        bundle = joblib.load(MODEL_PATH)
    except Exception:  # missing libraries or incompatible pickle
        return None
    return {**base, "bundle": bundle}


MODEL_LABELS = {
    "ensemble_lr_lgbm": "LightGBM + logistic regression",
    "lightgbm": "LightGBM",
    "lightgbm_calibrated": "LightGBM (calibrated)",
    "logistic_regression": "logistic regression",
}


def is_available() -> bool:
    return _load() is not None


def model_info() -> dict[str, Any] | None:
    loaded = _load()
    if not loaded:
        return None
    bundle = loaded["bundle"]
    return {
        "chosen": bundle.get("chosen"),
        "trained_at": bundle.get("trained_at"),
        "data_through": bundle.get("data_through"),
        "test_metrics": bundle.get("test_metrics"),
    }


def _aliases(full_name: str) -> list[str]:
    parts = [p for p in full_name.replace(".", " ").split() if p]
    aliases = [full_name, *MANUAL_NAME_ALIASES.get(full_name, [])]
    if len(parts) >= 2:
        surname = parts[-1]
        aliases.append(f"{''.join(p[0] for p in parts[:-1])} {surname}")
        aliases.append(f"{parts[0][0]} {surname}")
    return aliases


def _resolve_player(name: str, fam: str, loaded: dict[str, Any], team: str | None = None) -> dict[str, Any] | None:
    pid = _resolve_id(name, fam, loaded, team)
    return loaded["store"]["players"][fam][pid] if pid is not None else None


def resolve_id(name: str, fam: str, team_name: str | None = None) -> str | None:
    loaded = load_store()
    if not loaded or fam not in FORMAT_MAX_BALLS:
        return None
    return _resolve_id(name, fam, loaded, _team_key(team_name) if team_name else None)


def _resolve_id(name: str, fam: str, loaded: dict[str, Any], team: str | None = None) -> str | None:
    store = loaded["store"]
    table = store["players"][fam]
    teams_of = store.get("player_teams", {})

    # Exact Cricsheet spelling first (squads built from match data use these names), but only if that
    # player actually played for this team: "Rohit Sharma" is also the exact name of an Indonesia player,
    # while India's Rohit is "RG Sharma" in Cricsheet.
    exact = [pid for pid in loaded["by_name"].get(normalize_name(name), [])
             if pid in table and name == store["player_names"].get(pid)]
    exact_for_team = [pid for pid in exact if team is None or team in teams_of.get(pid, [])]
    if exact_for_team:
        return max(exact_for_team, key=lambda pid: (table[pid].get("matches", 0), store["player_last_seen"].get(pid, "")))

    def best(ids: list[str]) -> str | None:
        ids = [pid for pid in ids if pid in table]
        if not ids:
            return None
        # Prefer someone who has played for this team, then the most experienced
        return max(ids, key=lambda pid: (team in teams_of.get(pid, []), table[pid].get("matches", 0), store["player_last_seen"].get(pid, "")))

    # Each step below prefers a player who has played for this team; a match from another team is
    # only kept as a fallback, in case nothing better turns up.
    fallback: str | None = None

    def for_team(pid: str | None) -> bool:
        return pid is not None and (team is None or team in teams_of.get(pid, []))

    for alias in _aliases(name):
        found = best(loaded["by_name"].get(normalize_name(alias), []))
        if for_team(found):
            return found
        fallback = fallback or found

    # Same surname and same first initial ("Rajat Patidar" -> "RM Patidar")
    parts = [p for p in name.replace(".", " ").split() if p]
    if len(parts) >= 2:
        first_initial = parts[0][0].upper()
        surnames = {" ".join(parts[i:]) for i in range(1, len(parts))}
        ids = [
            pid
            for surname in surnames
            for initials, pid in loaded["by_surname"].get(normalize_name(surname), [])
            if initials[0] == first_initial
        ]
        found = best(ids)
        if for_team(found):
            return found
        fallback = fallback or found

        # Last resort: a player who played for THIS team with the same surname,
        # accepted only if exactly one such player exists ("Charith Asalanka" -> "KIC Asalanka")
        if team:
            last = normalize_name(parts[-1])
            first = normalize_name(parts[0])
            same_team = [
                pid for pid, pname in store["player_names"].items()
                if pid in table and team in teams_of.get(pid, [])
                and normalize_name(pname.split()[-1]) == last
            ]
            with_first = [pid for pid in same_team if first in normalize_name(store["player_names"][pid])]
            for group in (with_first, same_team):
                if len(group) == 1:
                    return group[0]
    # A namesake who only ever played for associate national sides (e.g. "Naman Tiwari" of Cyprus for an
    # uncapped IPL player) is almost certainly someone else: better to treat the player as a newcomer.
    if fallback and team:
        types = store.get("team_types", {})
        played = teams_of.get(fallback, [])
        if played and all(types.get(t) != "club" and t not in FULL_MEMBERS for t in played):
            return None
    return fallback


def venue_catalog(kind: str) -> dict[str, dict[str, Any]]:
    """Every ground in the data: kind is 'club' (IPL) or 'international'."""
    loaded = load_store()
    if not loaded:
        return {}
    return loaded["store"].get("venue_catalog", {}).get(kind, {})


def preset_venue_key(venue_name: str, city: str) -> list[str]:
    """Catalogue keys a hand-entered app venue corresponds to (its name plus known aliases)."""
    return [venue_key(n, city) for n in [venue_name, *VENUE_ALIASES.get(venue_name, [])]]


def venue_average(venue_name: str, city: str, fam: str, team_type: str, key: str | None = None) -> dict[str, Any] | None:
    """Recent first-innings average for an app venue, using the model's own definition.

    Returns {"avg", "n", "last"}; n == 0 means no recent matches here, so the
    recent format average is used. None if the feature store isn't available.
    """
    loaded = load_store()
    if not loaded or fam not in FORMAT_MAX_BALLS:
        return None
    group = f"{fam}|{team_type}"
    store = loaded["store"]
    table = store.get("venue_recent", {}).get(group, {})
    keys = [key] if key else preset_venue_key(venue_name, city)
    candidates = [table[k] for k in keys if k in table]
    if candidates:
        best = max(candidates, key=lambda c: (c.get("n", 0), c.get("last", "")))
        return {"avg": best["avg"], "n": best["n"], "last": best.get("last")}
    fallback = store.get("group_recent", {}).get(group)
    return {"avg": fallback, "n": 0, "last": None} if fallback else None


def _team_key(name: str) -> str:
    return _TEAM_LOOKUP.get(normalize_name(name), name)


def _balls_from_overs(overs: float, max_balls: int) -> int:
    whole = int(overs)
    part = int(round((overs - whole) * 10))
    return max(0, min(max_balls, whole * 6 + min(part, 5)))


def _xi_form(names: list[str], fam: str, loaded: dict[str, Any], team: str | None) -> dict[str, float]:
    """Recent form (last 10 innings / spells) of an XI, from the same table the Form tab shows."""
    from . import insights  # imported here: insights imports this module

    table = (insights._load() or {}).get("form", {})
    bats, bowls = [], []
    for name in names:
        pid = _resolve_id(name, fam, loaded, team)
        entry = table.get(pid, {}).get(fam, {}) if pid else {}
        bats.append(entry.get("bat"))
        bowls.append(entry.get("bowl"))
    return xi_recent_form(bats, bowls, fam)


def build_features(context: MatchContext) -> tuple[dict[str, Any], dict[str, Any]] | None:
    loaded = _load()
    fam = context.format
    if not loaded or fam not in FORMAT_MAX_BALLS:
        return None
    store = loaded["store"]
    max_balls = FORMAT_MAX_BALLS[fam]
    bat_name = _team_key(context.batting_first_team.name)
    chase_name = _team_key(context.chasing_team.name)
    elo_table = store["elo"][fam]
    team_types = store.get("team_types", {})
    is_club = int(team_types.get(bat_name) == "club" or team_types.get(chase_name) == "club")

    bat_stats = [_resolve_player(p.name, fam, loaded, bat_name) for p in context.batting_first_team.players]
    chase_stats = [_resolve_player(p.name, fam, loaded, chase_name) for p in context.chasing_team.players]
    bat_xi = xi_features(bat_stats, fam)
    chase_xi = xi_features(chase_stats, fam)
    pratings = player_ratings.for_xis([_resolve_id(p.name, fam, loaded, bat_name) for p in context.batting_first_team.players],
                                      [_resolve_id(p.name, fam, loaded, chase_name) for p in context.chasing_team.players], fam)
    bat_form = _xi_form([p.name for p in context.batting_first_team.players], fam, loaded, bat_name)
    chase_form = _xi_form([p.name for p in context.chasing_team.players], fam, loaded, chase_name)

    balls = _balls_from_overs(context.overs_faced, max_balls)
    wickets = max(0, min(10, context.wickets_lost))
    if wickets >= 10:
        balls = balls or max_balls
    runs = max(0, context.first_innings_score)
    row = {
        "is_odi": int(fam == "odi"),
        "is_club": is_club,
        "is_ipl": is_club,  # the app's franchise teams are all IPL sides
        "balls_left_frac": round((max_balls - balls) / max_balls, 4),
        "runs": runs,
        "wickets": wickets,
        "run_rate": round(runs * 6 / balls, 3) if balls else 0.0,
        "venue_avg": float(context.pitch_report.average_first_innings_score),
        "elo_diff": elo_table.get(bat_name, ELO_START) - elo_table.get(chase_name, ELO_START),
        # team strength the win / chase models use: Kalman rating gap + uncertainty as of today (kalman.py)
        **dict(zip(("kal_diff", "kal_unc"), kalman.gap(fam, bat_name, chase_name))),
        "bat_xi_bat": bat_xi["bat"], "bat_xi_bowl_econ": bat_xi["bowl_econ"], "bat_xi_exp": bat_xi["exp"],
        "chase_xi_bat": chase_xi["bat"], "chase_xi_bowl_econ": chase_xi["bowl_econ"], "chase_xi_exp": chase_xi["exp"],
        **pratings,
        "bat_xi_form_bat": bat_form["bat"], "bat_xi_form_econ": bat_form["econ"],
        "chase_xi_form_bat": chase_form["bat"], "chase_xi_form_econ": chase_form["econ"],
    }
    # home advantage and how often batting first wins at this ground (same definitions as training)
    venue = getattr(context, "venue", None) or {}
    vkey = venue.get("key")
    group = competition_group(fam, "club" if is_club else "international", [bat_name, chase_name])
    bf = store.get("venue_bf", {}).get(f"{group}|{vkey}") if vkey else None
    venue_bf_rate = round((bf[0] + 5.0) / (bf[1] + 10.0), 3) if bf else 0.5

    def is_home(team: str) -> int:
        if not vkey:
            return 0
        if is_club:
            return 0  # IPL "home grounds" didn't help on the three-season backtest; internationals only
        from .venue_countries import country_for
        return int(country_for(venue.get("name", ""), venue.get("city", ""), None) == team)

    crease = (getattr(context, "crease", None) or {})
    set_table = store.get("crease_set_expect", {})

    def known(side_rows, names, stats):
        """[(stats, balls)] for the batters the user said are in (only XI members count)."""
        picked = []
        for r in side_rows or []:
            if r["name"] in names:
                picked.append((stats[names.index(r["name"])], r.get("balls")))
        return picked

    bat_names = [p.name for p in context.batting_first_team.players]
    chase_names = [p.name for p in context.chasing_team.players]

    def in_order(names, stats, wanted):
        """The XI's stats in the batting order the user set (None: they didn't, so the model guesses it)."""
        if not wanted:
            return stats, False
        pos = {n: i for i, n in enumerate(wanted)}
        idx = sorted(range(len(names)), key=lambda i: (pos.get(names[i], len(pos)), i))
        return [stats[i] for i in idx], True

    order = getattr(context, "order", None) or {}
    bat_line, bat_ordered = in_order(bat_names, bat_stats, order.get("bat"))
    chase_line, chase_ordered = in_order(chase_names, chase_stats, order.get("chase"))
    bat_known = known(crease.get("bat"), bat_names, bat_stats)
    if bat_known:
        lineup = app_lineup_known(bat_line, [s for s, _ in bat_known], wickets, fam, bat_ordered)
    else:
        lineup = app_lineup(bat_line, wickets, fam, bat_ordered)
    row["bat_crease"], row["bat_next3"] = lineup["crease"], lineup["next3"]
    balls_known = [b for _, b in bat_known if b is not None]
    row["bat_crease_set"] = (crease_set(balls_known) if len(balls_known) == 2
                             else expected_set(set_table, fam, balls, wickets))
    row["_chase_known"] = known(crease.get("chase"), chase_names, chase_stats)
    row["_set_table"] = set_table
    # death-overs hitting and bowling of both XIs (same per-player phase totals the Phases tab shows)
    from . import insights
    ph = (insights._load() or {}).get("phase_stats", {}).get(fam, {})
    bd = xi_death_features([ph.get(_resolve_id(p.name, fam, loaded, bat_name)) for p in context.batting_first_team.players], fam)
    cd = xi_death_features([ph.get(_resolve_id(p.name, fam, loaded, chase_name)) for p in context.chasing_team.players], fam)
    row.update({"bat_xi_death_sr": bd["sr"], "bat_xi_death_econ": bd["econ"], "chase_xi_death_sr": cd["sr"], "chase_xi_death_econ": cd["econ"]})
    row["home_diff"] = is_home(bat_name) - is_home(chase_name)
    row["venue_bf_rate"] = venue_bf_rate
    # in batting order (the user's if set, flagged by _ordered; else XI order and the model sorts by usual position)
    row["_chase_stats"], row["_chase_ordered"] = chase_line, chase_ordered  # the chase model works out who's in from this
    row["_bat_stats"], row["_bat_known"], row["_bat_ordered"] = bat_line, bat_known, bat_ordered  # par-by-wickets grid
    add_derived(row)
    meta = {
        "balls": balls,
        "max_balls": max_balls,
        "bat_elo": elo_table.get(bat_name), "chase_elo": elo_table.get(chase_name),
        "bat_matched": sum(s is not None for s in bat_stats), "bat_total": len(bat_stats),
        "chase_matched": sum(s is not None for s in chase_stats), "chase_total": len(chase_stats),
    }
    return row, meta


def predict_probability(rows: list[dict[str, Any]]) -> list[float]:
    """Batting-first win probability (0-1) for each feature row."""
    loaded = _load()
    if not loaded:
        raise RuntimeError("ML model not available")
    import pandas as pd

    bundle = loaded["bundle"]
    X = pd.DataFrame(rows)[bundle["features"]]
    chosen = bundle.get("chosen", "lightgbm")
    gbm = bundle["model"].predict_proba(X)[:, 1]
    if chosen == "logistic_regression":
        probs = bundle["logreg"].predict_proba(X)[:, 1]
    elif chosen == "ensemble_lr_lgbm":
        probs = (gbm + bundle["logreg"].predict_proba(X)[:, 1]) / 2.0
    elif bundle.get("isotonic") is not None:
        probs = bundle["isotonic"].predict(gbm)
    else:
        probs = gbm
    return [float(min(0.99, max(0.01, p))) for p in probs]


def factor_effects(row: dict[str, Any]) -> dict[str, float]:
    """How many percentage points each factor moves the batting-first chance.

    Each factor is reset to a neutral value and the model is re-run; the
    difference is that factor's effect.
    """
    neutral_score = dict(row)
    max_balls = FORMAT_MAX_BALLS["odi" if row["is_odi"] else "t20"]
    balls_done = max_balls * (1 - row["balls_left_frac"])
    neutral_score["runs"] = round(row["venue_avg"] * balls_done / max_balls)
    neutral_score["run_rate"] = round(neutral_score["runs"] * 6 / balls_done, 3) if balls_done else 0.0
    add_derived(neutral_score)

    neutral_elo = dict(row, elo_diff=0.0, kal_diff=0.0)

    neutral_xi = dict(row)
    for a, b in (("bat_xi_bat", "chase_xi_bat"), ("bat_xi_bowl_econ", "chase_xi_bowl_econ"), ("bat_xi_exp", "chase_xi_exp"), *player_ratings.PAIRS):
        if a in row and b in row:
            mean = (row[a] + row[b]) / 2.0
            neutral_xi[a] = neutral_xi[b] = mean

    base, p_score, p_elo, p_xi = predict_probability([row, neutral_score, neutral_elo, neutral_xi])
    return {
        "probability": base,
        "score_vs_par": (base - p_score) * 100,
        "team_ratings": (base - p_elo) * 100,
        "playing_xi": (base - p_xi) * 100,
    }


def predict(context: MatchContext, formula_probability: float | None = None):
    from .predictor import PredictionResult  # local import avoids a cycle

    built = build_features(context)
    if built is None:
        return None
    row, meta = built
    effects = factor_effects(row)
    bat_pct = round(effects["probability"] * 100, 2)
    chase_pct = round(100 - bat_pct, 2)
    bat = context.batting_first_team.name
    chase = context.chasing_team.name
    info = model_info() or {}
    test = (info.get("test_metrics") or {}).get("innings_break", {}).get(info.get("chosen", ""), {})
    label = MODEL_LABELS.get(info.get("chosen", ""), info.get("chosen", "ML"))

    overs_text = f"{meta['balls'] // 6}.{meta['balls'] % 6}"
    par = row["venue_avg"] * (meta["max_balls"] - row["balls_left_frac"] * meta["max_balls"]) / meta["max_balls"]

    def signed(points: float, team: str, other: str) -> str:
        if abs(points) < 0.5:
            return "roughly neutral"
        return f"{abs(points):.1f} pts toward {team if points > 0 else other}"

    def elo_text(value: float | None) -> str:
        return f"{value:.0f}" if value is not None else "no history (1500)"

    explanation = [
        f"Machine-learning model ({label}) learned from {_load()['store']['built_from_matches']:,} men's T20/ODI matches on Cricsheet "
        f"up to {info.get('data_through', '?')}"
        + (f"; it picked the right winner in {test['accuracy']:.0%} of unseen 2025–26 matches at the innings break." if test else "."),
        f"Score: {row['runs']}/{row['wickets']} after {overs_text} overs vs a par of about {par:.0f} at this venue — "
        f"{signed(effects['score_vs_par'], bat, chase)}.",
        f"Team ratings (Elo): {bat} {elo_text(meta['bat_elo'])} vs {chase} {elo_text(meta['chase_elo'])} — "
        f"{signed(effects['team_ratings'], bat, chase)}.",
        f"Playing XI records (players found in data: {meta['bat_matched']}/{meta['bat_total']} and "
        f"{meta['chase_matched']}/{meta['chase_total']}) — {signed(effects['playing_xi'], bat, chase)}.",
    ]
    if formula_probability is not None:
        explanation.append(f"For comparison, the old hand-tuned formula gave {bat} {formula_probability:.1f}%.")
    explanation.append("Pitch sliders and dew aren't in the historical data, so the model uses only the venue average for conditions.")

    return PredictionResult(
        batting_first_team=bat,
        chasing_team=chase,
        batting_first_win_probability=bat_pct,
        chasing_win_probability=chase_pct,
        predicted_winner=bat if bat_pct >= chase_pct else chase,
        confidence=round(abs(bat_pct - chase_pct), 2),
        explanation=explanation,
        model_used=f"ML ({label})",
        details={
            "engine": "ml",
            "model_label": label,
            "test_accuracy_innings_break": test.get("accuracy"),
            "par": round(par),
            "venue_avg": round(row["venue_avg"]),
            "overs_text": overs_text,
            "runs": row["runs"],
            "wickets": row["wickets"],
            "factors": {
                "score_vs_par": round(effects["score_vs_par"], 1),
                "team_ratings": round(effects["team_ratings"], 1),
                "playing_xi": round(effects["playing_xi"], 1),
            },
            "bat_elo": round(meta["bat_elo"]) if meta["bat_elo"] is not None else None,
            "chase_elo": round(meta["chase_elo"]) if meta["chase_elo"] is not None else None,
            "players_found": {"batting": [meta["bat_matched"], meta["bat_total"]], "chasing": [meta["chase_matched"], meta["chase_total"]]},
            "formula_probability": formula_probability,
        },
    )


def player_found(name: str, fam: str, team_name: str) -> bool:
    return player_matches(name, fam, team_name) is not None


def player_matches(name: str, fam: str, team_name: str) -> int | None:
    """Matches played in this format (None if the player isn't in the data)."""
    loaded = load_store()
    if not loaded or fam not in FORMAT_MAX_BALLS:
        return None
    stats = _resolve_player(name, fam, loaded, _team_key(team_name))
    return int(stats.get("matches", 0)) if stats is not None else None


def player_position(name: str, fam: str, team_name: str) -> float:
    """Usual batting position in this format (1 = opener); players with no record count as batting low.
    The same number the model sorts by when it guesses the batting order."""
    from .ml_features import typical_position

    loaded = load_store()
    if not loaded or fam not in FORMAT_MAX_BALLS:
        return typical_position(None)
    return round(typical_position(_resolve_player(name, fam, loaded, _team_key(team_name))), 2)


def reload() -> None:
    """Drop cached model + feature store so a fresh retrain is picked up."""
    load_store.cache_clear()
    _load.cache_clear()
