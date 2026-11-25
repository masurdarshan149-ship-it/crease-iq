"""Match time machine: replay any past match over by over with the model's win chance at each point.

Everything comes from files the app already has: data/ml/training_rows.csv.gz (first innings, one row per over) and
data/ml/chase_rows.csv.gz (the chase). Each row carries the model's inputs as they stood on the day of the match
(team ratings, XI strength, venue par), so the replay shows what the model would have said then, not with hindsight.

Honesty: matches before TEST_START were part of the model's training data, so it has "seen" them; matches from
TEST_START on are unseen. The replay says which.

The tables are read once, on the first replay request (a few seconds), then kept in memory.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from . import chase_model, kalman, ml_model
from .ml_features import add_chase_derived, add_derived
from .once import locked_cache

ROOT = Path(__file__).resolve().parents[1]
ROWS_PATH = ROOT / "data" / "ml" / "training_rows.csv.gz"
CHASE_PATH = ROOT / "data" / "ml" / "chase_rows.csv.gz"
TEST_START = "2025-01-01"  # same split as scripts/train_win_model.py
COMPETITIONS = {"ipl": "IPL", "t20i": "T20 internationals", "odi": "ODIs"}


def _competition(row: dict[str, Any]) -> str:
    if int(row.get("is_ipl") or 0):
        return "ipl"
    return "odi" if row["fam"] == "odi" else "t20i"


@locked_cache
def _tables() -> dict[str, Any] | None:
    """Both row files, grouped by match, plus the list of matches (newest first)."""
    if not ROWS_PATH.exists():
        return None
    fast = _load_fast()
    if fast is not None:
        return fast
    import pandas as pd

    try:
        first = pd.read_csv(ROWS_PATH)
        chase = pd.read_csv(CHASE_PATH) if CHASE_PATH.exists() else None
    except (OSError, EOFError, ValueError):  # half-written file (an update is running): no replays for now
        return None
    if "is_league" in first:
        first = first[first["is_league"] == 0]
    # kept as two sorted tables with each match's row range (a dict of every row would cost hundreds of MB)
    first = first.sort_values(["match_id", "balls"]).reset_index(drop=True)
    from . import player_ratings  # the win model's player-rating inputs for every past match

    first = player_ratings.add_columns(first)
    if chase is not None:
        chase = player_ratings.add_columns(chase)
    ratings = kalman.from_training_rows()

    def spans(df):
        ids = df["match_id"].to_numpy()
        out, start = {}, 0
        for k in range(1, len(ids) + 1):
            if k == len(ids) or ids[k] != ids[start]:
                out[int(ids[start])] = (start, k)
                start = k
        return out

    first_span = spans(first)
    chase_span: dict[int, tuple[int, int]] = {}
    if chase is not None:
        chase = chase[chase["match_id"].isin(first_span.keys())].sort_values(["match_id", "balls"]).reset_index(drop=True)
        chase_span = spans(chase)
    index = []
    for mid, (a, b) in first_span.items():
        r0, rl = first.iloc[a], first.iloc[b - 1]
        c0 = chase.iloc[chase_span[mid][0]] if mid in chase_span else None
        index.append({
            "id": mid, "date": str(r0["date"])[:10], "competition": _competition(r0), "format": r0["fam"],
            "bat": r0["batting_team"], "chase": r0["chasing_team"], "venue": r0["venue"] if isinstance(r0["venue"], str) else "",
            "total": int(rl["runs"]) if _nan(r0.get("final_total")) else int(r0["final_total"]),
            "bat_won": int(r0["label_batting_first_won"]),
        })
        m = index[-1]
        m["target"] = int(c0["target"]) if c0 is not None else m["total"] + 1
        # the row files hold the score at the end of each over, not the final ball, so the result is given in words
        m["result"] = (f"{m['bat']} defended {m['total']}" if m["bat_won"] else f"{m['chase']} chased {m['target']}")
    _add_metrics(first, chase, first_span, chase_span, ratings, index)
    index.sort(key=lambda m: (m["date"], m["id"]), reverse=True)
    _save_index(index)
    out = {"first": first, "chase": chase, "first_span": first_span, "chase_span": chase_span, "ratings": ratings,
           "index": index, "by_id": {m["id"]: m for m in index}}
    _save_fast(out)
    return out


def _all_probs(table, ratings: dict[Any, tuple[float, float]], derive, predict) -> list[float]:
    """The model's answer for every row of a table, in chunks (scored exactly as a single replay scores them)."""
    out: list[float] = []
    default = (0.0, math.sqrt(2 * kalman.START_VAR))
    for start in range(0, len(table), 20000):
        recs = table.iloc[start:start + 20000].to_dict("records")
        for r in recs:
            r["kal_diff"], r["kal_unc"] = ratings.get(r["match_id"], default)
            if int(r.get("is_ipl") or 0):
                r["home_diff"] = 0
            derive(r)
        out.extend(predict(recs))
    return out


def _add_metrics(first, chase, first_span, chase_span, ratings, index: list[dict[str, Any]]) -> None:
    """Headline numbers for each match (for the Replay page's lists): was it an upset, did the model have the wrong
    side at the innings break, how low did the winner go, how close was it late on. Needs the models; if they aren't
    loaded the lists are simply not offered."""
    try:
        if not ml_model.is_available():
            return
        p_first = _all_probs(first, ratings, add_derived, ml_model.predict_probability)
        p_chase: list[float] = []
        if chase is not None and len(chase) and chase_model.is_available():
            p_chase = [1.0 - p for p in _all_probs(chase, ratings, add_chase_derived, lambda rows: chase_model._probabilities(rows)[0])]
    except Exception:  # noqa: BLE001 - the lists are an extra; the replay itself doesn't depend on them
        return
    for m in index:
        a, b = first_span[m["id"]]
        series = p_first[a:b]
        late = series[-1]
        if p_chase and m["id"] in chase_span:
            c, d = chase_span[m["id"]]
            series = series + p_chase[c:d]
            late = p_chase[d - 1]
        won = bool(m["bat_won"])
        mine = (lambda p: p) if won else (lambda p: 1.0 - p)  # the eventual winner's chance
        pre, brk = p_first[a], p_first[b - 1]
        m["m"] = {
            "upset": (pre >= 0.5) != won, "fav": round(max(pre, 1 - pre) * 100, 1),
            "brk_wrong": (brk >= 0.5) != won, "brk_conf": round(max(brk, 1 - brk) * 100, 1),
            "low": round(min(mine(p) for p in series) * 100, 1), "late": round(mine(late) * 100, 1),
        }


SORTS = {
    "upsets": "Biggest upsets", "wrong": "Model got it wrong", "comebacks": "Biggest comebacks", "close": "Closest finishes",
}


def _sorted(matches: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    have = [m for m in matches if m.get("m")]
    if sort == "upsets":
        return sorted((m for m in have if m["m"]["upset"]), key=lambda m: -m["m"]["fav"])
    if sort == "wrong":
        return sorted((m for m in have if m["m"]["brk_wrong"]), key=lambda m: -m["m"]["brk_conf"])
    if sort == "comebacks":
        return sorted((m for m in have if m["m"]["low"] < 25), key=lambda m: m["m"]["low"])
    if sort == "close":
        return sorted(have, key=lambda m: abs(m["m"]["late"] - 50))
    return matches


def _note(m: dict[str, Any], sort: str) -> str:
    x = m.get("m")
    if not x:
        return ""
    winner, loser = (m["bat"], m["chase"]) if m["bat_won"] else (m["chase"], m["bat"])
    if sort == "upsets":
        return f"{loser} were {x['fav']:.0f}% favourites before the first ball"
    if sort == "wrong":
        return f"The model had {loser} at {x['brk_conf']:.0f}% at the innings break"
    if sort == "comebacks":
        return f"{winner} were down to {x['low']:.0f}%"
    if sort == "close":
        return f"{winner} were at {x['late']:.0f}% with an over to go"
    return ""


def refresh() -> None:
    """After a retrain / data update: forget the old archive and prepare the new one in the background."""
    _tables.cache_clear()
    _INDEX_CACHE.clear()
    warm()


def _rows(table, span: tuple[int, int] | None) -> list[dict[str, Any]]:
    return table.iloc[span[0]:span[1]].to_dict("records") if span and table is not None else []


def _nan(v: Any) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _venue_name(key: str) -> str:
    store = (ml_model.load_store() or {}).get("store", {})
    for kind in ("club", "international"):
        entry = (store.get("venue_catalog", {}).get(kind) or {}).get(key)
        if entry:
            return entry.get("name") or key
    return key


def _fold(text: str) -> str:
    return "".join(ch for ch in str(text).lower() if ch.isalnum() or ch == " ")


INDEX_PATH = ROOT / "data" / "ml" / "replay_index.json"


def _rows_key() -> str:
    """Changes whenever the row files are rebuilt, so nothing saved from older data is ever used."""
    try:
        st = ROWS_PATH.stat()
        ch = CHASE_PATH.stat() if CHASE_PATH.exists() else None
        key = f"{st.st_size}-{int(st.st_mtime)}" + (f"-{ch.st_size}-{int(ch.st_mtime)}" if ch else "")
        from . import player_ratings
        for model in (ml_model.MODEL_PATH, chase_model.MODEL_PATH, player_ratings.MATCHES_PATH):  # the lists use the models' answers
            key += f"-{int(model.stat().st_mtime)}" if model.exists() else "-0"
        return key + "-v2"
    except OSError:
        return ""


FAST_PATH = ROOT / "data" / "ml" / "replay_cache.pkl"


def _save_fast(tables: dict[str, Any]) -> None:
    """The prepared tables saved in a quick-to-read form: reading the two .csv.gz files and working out every match's
    ratings takes ~10 s (much longer while the app is starting up); reading this back takes about a second."""
    try:
        import pickle

        tmp = FAST_PATH.with_name(FAST_PATH.name + ".tmp")
        with tmp.open("wb") as fh:
            pickle.dump({"key": _rows_key(), "tables": tables}, fh, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(FAST_PATH)
    except Exception:  # noqa: BLE001 - only a speed-up
        pass


def _load_fast() -> dict[str, Any] | None:
    key = _rows_key()
    if not key or not FAST_PATH.exists():
        return None
    try:
        import pickle

        with FAST_PATH.open("rb") as fh:
            saved = pickle.load(fh)  # written by this app on this PC (never downloaded)
    except Exception:  # noqa: BLE001 - damaged or from another pandas version: rebuild from the row files
        return None
    return saved["tables"] if saved.get("key") == key else None


def _save_index(index: list[dict[str, Any]]) -> None:
    """The match list on its own (about 1 MB), so the Replay page can list and search matches at once instead of
    waiting for the whole archive to be read."""
    try:
        import json

        tmp = INDEX_PATH.with_name(INDEX_PATH.name + ".tmp")
        tmp.write_text(json.dumps({"key": _rows_key(), "index": index}), encoding="utf-8")
        tmp.replace(INDEX_PATH)
    except OSError:
        pass  # only a speed-up


_INDEX_CACHE: dict[str, Any] = {}


def _quick_index() -> list[dict[str, Any]] | None:
    """The saved match list if it belongs to the current row file; None if there isn't one yet."""
    key = _rows_key()
    if key and _INDEX_CACHE.get("key") == key:
        return _INDEX_CACHE["index"]
    try:
        import json

        saved = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    # the online copy has no row files (key ""): it uses the list exactly as published from the PC, where it was checked
    online = not key and __import__("os").environ.get("CREASE_PUBLIC") == "1"
    if not online and (not key or saved.get("key") != key):
        return None
    _INDEX_CACHE.update(key=key, index=saved["index"])
    return saved["index"]


def warm() -> None:
    """Read the archive in the background (so the first replay opens quickly) without making anyone wait for it."""
    if _tables.cache_info().currsize or _INDEX_CACHE.get("warming"):
        return
    import threading

    _INDEX_CACHE["warming"] = True
    threading.Thread(target=_tables, daemon=True, name="replay-warm").start()


def search(query: str = "", competition: str = "", limit: int = 40, sort: str = "") -> dict[str, Any]:
    """Past matches, newest first. `query` matches team names, the year or a date (e.g. "india pakistan 2022").
    `sort` picks one of the SORTS lists instead (biggest upsets, model got it wrong, comebacks, closest finishes)."""
    index = _quick_index() if not _tables.cache_info().currsize else None
    if index is not None:
        warm()  # the list is answered now; the full archive loads behind it for the replay itself
        t = {"index": index}
    else:
        t = _tables()
    if not t:
        return {"matches": [], "total": 0, "ready": False}
    words = [w for w in _fold(query).split() if w]
    out = []
    for m in t["index"]:
        if competition in COMPETITIONS and m["competition"] != competition:
            continue
        if words:
            hay = _fold(f"{m['bat']} {m['chase']} {m['date']} {m['date'][:4]}")
            if not all(w in hay for w in words):
                continue
        out.append(m)
    has_lists = any(m.get("m") for m in t["index"][:50])
    sort = sort if sort in SORTS and has_lists else ""
    out = _sorted(out, sort)
    total = len(out)
    shown = []
    for m in out[: max(1, min(int(limit or 40), 100))]:
        winner = m["bat"] if m["bat_won"] else m["chase"]
        row = {k: v for k, v in m.items() if k != "m"}
        shown.append({**row, "venue": _venue_name(m["venue"]), "winner": winner, "unseen": m["date"] >= TEST_START,
                      "note": _note(m, sort)})
    newest = max((m["date"] for m in t["index"]), default=None)  # the latest match in the data (all competitions)
    return {"matches": shown, "total": total, "ready": True, "competitions": COMPETITIONS, "sort": sort,
            "sorts": SORTS if has_lists else {}, "newest": newest}


def _win_probs(rows: list[dict[str, Any]], rating: tuple[float, float]) -> list[float]:
    """Batting-first win chance for each first-innings row, exactly as the live win model would score it."""
    feats = []
    for r in rows:
        row = add_derived(dict(r))
        row["kal_diff"], row["kal_unc"] = rating
        if int(row.get("is_ipl") or 0):
            row["home_diff"] = 0  # same rule as training: home advantage for internationals only
        feats.append(row)
    return ml_model.predict_probability(feats)


def _chase_probs(rows: list[dict[str, Any]], rating: tuple[float, float]) -> list[float]:
    """Chasing side's win chance for each chase row, exactly as the live chase model would score it."""
    feats = []
    for r in rows:
        row = dict(r)
        row["kal_diff"], row["kal_unc"] = rating
        if int(row.get("is_ipl") or 0):
            row["home_diff"] = 0
        feats.append(add_chase_derived(row))
    probs, _simple = chase_model._probabilities(feats)
    return probs


def _overs(balls: int) -> str:
    return f"{balls // 6}.{balls % 6}" if balls % 6 else f"{balls // 6}"


def replay(match_id: Any) -> dict[str, Any]:
    t = _tables()
    if not t:
        raise ValueError("Past matches aren't available right now (the data is being rebuilt). Try again in a few minutes.")
    try:
        mid = int(match_id)
    except (TypeError, ValueError):
        raise ValueError("Pick a match from the list.") from None
    meta = t["by_id"].get(mid)
    if not meta:
        raise ValueError("That match isn't in the data.")
    if not ml_model.is_available():
        raise ValueError("The model isn't loaded yet. Try again in a moment.")
    first, chase = _rows(t["first"], t["first_span"].get(mid)), _rows(t["chase"], t["chase_span"].get(mid))
    rating = t["ratings"].get(mid, (0.0, math.sqrt(2 * kalman.START_VAR)))
    max_balls = 300 if meta["format"] == "odi" else 120

    points: list[dict[str, Any]] = []
    for r, p in zip(first, _win_probs(first, rating)):
        points.append({"inn": 1, "balls": int(r["balls"]), "over": _overs(int(r["balls"])), "runs": int(r["runs"]),
                       "wickets": int(r["wickets"]), "p": round(p * 100, 1)})
    target = int(chase[0]["target"]) if chase else meta["total"] + 1
    if chase and chase_model.is_available():
        for r, p in zip(chase, _chase_probs(chase, rating)):
            if int(r["balls"]) == 0 and points:  # the innings break is one moment: keep the chase model's view of it
                points[-1]["break"] = True
            points.append({"inn": 2, "balls": int(r["balls"]), "over": _overs(int(r["balls"])), "runs": int(r["runs"]),
                           "wickets": int(r["wickets"]), "p": round((1 - p) * 100, 1), "need": max(0, target - int(r["runs"])),
                           "balls_left": max(0, max_balls - int(r["balls"]))})
    # the result itself is the last point
    points.append({"inn": 2 if chase else 1, "balls": None, "over": "end", "runs": None, "wickets": None,
                   "p": 100.0 if meta["bat_won"] else 0.0, "final": True})

    # wickets that fell and runs scored between consecutive points, and how far the win chance moved
    for i, pt in enumerate(points):
        prev = points[i - 1] if i else None
        same = prev is not None and prev["inn"] == pt["inn"] and pt.get("runs") is not None and prev.get("runs") is not None
        pt["d_runs"] = pt["runs"] - prev["runs"] if same else 0
        pt["d_wkts"] = pt["wickets"] - prev["wickets"] if same else 0
        # the first point of the chase is the same moment as the innings break (two models' views of it): no "swing"
        pt["swing"] = round(pt["p"] - prev["p"], 1) if prev is not None and not (pt["inn"] == 2 and pt.get("balls") == 0) else 0.0

    winner = meta["bat"] if meta["bat_won"] else meta["chase"]
    turning = []
    for i, pt in sorted(enumerate(points), key=lambda ip: -abs(ip[1]["swing"])):
        if pt.get("final") or abs(pt["swing"]) < 4 or len(turning) >= 4:
            continue
        side = meta["bat"] if pt["inn"] == 1 else meta["chase"]
        gained = meta["bat"] if pt["swing"] > 0 else meta["chase"]
        what = f"{pt['d_runs']} runs" + (f", {pt['d_wkts']} wicket{'s' if pt['d_wkts'] != 1 else ''}" if pt["d_wkts"] else "")
        turning.append({"index": i, "inn": pt["inn"], "over": pt["over"], "swing": pt["swing"], "to": gained,
                        "text": f"{side} {pt['runs']}/{pt['wickets']} after {pt['over']} overs ({what} in the over)"})
    turning.sort(key=lambda x: x["index"])

    start_p = points[0]["p"]
    fav = meta["bat"] if start_p >= 50 else meta["chase"]
    low = min((pt["p"] if meta["bat_won"] else 100 - pt["p"]) for pt in points[:-1]) if len(points) > 1 else 50.0
    # the model's call at fixed checkpoints, each marked right or wrong against the real result
    def call(stage: str, p_bat: float, index: int) -> dict[str, Any]:
        team = meta["bat"] if p_bat >= 50 else meta["chase"]
        return {"stage": stage, "team": team, "pct": round(max(p_bat, 100 - p_bat), 1), "right": team == winner,
                "close": abs(p_bat - 50) < 5, "index": index}

    calls = [call("Before the first ball", points[0]["p"], 0)]
    brk = next((i for i, pt in enumerate(points) if pt.get("break")), None)
    if brk is not None:
        calls.append(call("At the innings break", points[brk]["p"], brk))
    half = [(i, pt) for i, pt in enumerate(points) if pt["inn"] == 2 and pt.get("balls") == max_balls // 2]
    if half:
        calls.append(call("Halfway through the chase", half[0][1]["p"], half[0][0]))
    n_right = sum(c["right"] for c in calls)
    return {
        "calls": calls, "calls_right": n_right,
        "id": mid, "date": meta["date"], "competition": COMPETITIONS[meta["competition"]], "format": meta["format"].upper(),
        "bat": meta["bat"], "chase": meta["chase"], "venue": _venue_name(meta["venue"]),
        "total": meta["total"], "target": target, "result": meta["result"], "winner": winner,
        "unseen": meta["date"] >= TEST_START, "max_balls": max_balls, "points": points, "turning": turning,
        "story": {
            "favourite": fav, "favourite_pct": round(max(start_p, 100 - start_p), 1),
            "upset": fav != winner, "winner_lowest": round(low, 1),
            "called_at_break": next((round(pt["p"], 1) for pt in points if pt.get("break")), None),
        },
    }
