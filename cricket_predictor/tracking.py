"""Check saved predictions against what really happened.

Automatic: a prediction is matched to a real match in the data (same two teams,
same format, played from 1 day before to 4 days after the prediction was made).
Manual: the user can set the result themselves; a manual result always wins.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from . import ml_model

WINDOW_BEFORE = 1
WINDOW_AFTER = 4


def _d(text: str | None) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


def _results() -> tuple[list[dict[str, Any]], str | None]:
    loaded = ml_model.load_store()
    if not loaded:
        return [], None
    store = loaded["store"]
    fields = store.get("results_fields") or []
    rows = [dict(zip(fields, r)) for r in store.get("results", [])]
    return rows, store.get("latest_match_date")


def find_result(entry: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any] | None:
    made = _d(entry.get("timestamp"))
    if not made:
        return None
    teams = {ml_model._team_key(entry.get("batting_first_team", "")), ml_model._team_key(entry.get("chasing_team", ""))}
    fmt = str(entry.get("format", "")).lower()
    candidates = [
        r for r in results
        if {r["team1"], r["team2"]} == teams and (not fmt or r["format"] == fmt)
        and made - timedelta(days=WINDOW_BEFORE) <= (_d(r["date"]) or date.min) <= made + timedelta(days=WINDOW_AFTER)
    ]
    if not candidates:
        return None
    # the match closest to when the prediction was made
    return min(candidates, key=lambda r: abs(((_d(r["date"]) or made) - made).days))


def _live() -> list[dict[str, Any]]:
    """Recent men's results fetched from CricketData (local cache only; empty without a key)."""
    try:
        from . import live_results
        return [m for m in live_results.load().get("matches", []) if not m.get("women")]
    except Exception:  # noqa: BLE001 - an optional extra
        return []


def find_live(entry: dict[str, Any], live: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Same rule as find_result (same two teams and format, played 1 day before to 4 days after the prediction)."""
    made = _d(entry.get("timestamp"))
    if not made or not live:
        return None
    key = ml_model._team_key
    teams = {key(entry.get("batting_first_team", "")), key(entry.get("chasing_team", ""))}
    fmt = str(entry.get("format", "")).lower()
    cands = [m for m in live
             if {key(m["team1"]), key(m["team2"])} == teams and (not fmt or m.get("format") == fmt)
             and made - timedelta(days=WINDOW_BEFORE) <= (_d(m.get("date")) or date.min) <= made + timedelta(days=WINDOW_AFTER)]
    return min(cands, key=lambda m: abs(((_d(m["date"]) or made) - made).days)) if cands else None


def _teams(e: dict[str, Any]) -> str:
    return "|".join(sorted(ml_model._team_key(str(e.get(k) or "")) for k in ("batting_first_team", "chasing_team")))


def _runs(score: Any) -> int | None:
    """153, "153" or "153/7" -> 153."""
    try:
        return int(str(score).split("/")[0].strip())
    except (TypeError, ValueError):
        return None


def assign_matches(items: list[dict[str, Any]], results: list[dict[str, Any]], live: list[dict[str, Any]],
                   late: dict[int, dict[str, Any]] | None = None) -> dict[int, tuple[str, str]]:
    """Which real match each entry belongs to, as (key, match day), keyed by id(entry).
    1. A save linked to a real match (the downloaded data, or CricketData's recent results) belongs to that match,
       so two matches between the same teams on back-to-back days stay apart. A model check is its own match.
    2. A save not linked yet (waiting for data, or a practice prediction) joins saves of the same two teams and format
       made the same day, or showing the same first-innings score within 2 days (same score = same match)."""
    out: dict[int, tuple[str, str]] = {}
    loose: list[dict[str, Any]] = []
    for e in items:
        base = f"{_teams(e)}|{str(e.get('format') or '').upper()}"
        day = None
        if e.get("auto"):
            day = str(e.get("timestamp") or "")[:10]
        else:
            hit = find_result(e, results) or find_live(e, live)
            day = hit.get("date") if hit else None
        if day:
            out[id(e)] = (f"m|{base}|{day}", day)
        else:
            loose.append(e)
    # a save made well after the match (e.g. a past match predicted again) is that match when the teams, format and
    # first-innings score are the same as a known match played up to 45 days before the save
    known = [(e, out[id(e)]) for e in items if id(e) in out]
    for e in list(loose):
        base = f"{_teams(e)}|{str(e.get('format') or '').upper()}"
        runs, made = _runs(e.get("first_innings_score")), _d(e.get("timestamp"))
        if runs is None or not made:
            continue
        for other, (key, day) in known:
            played = _d(day)
            if (key.startswith(f"m|{base}|") and _runs(other.get("first_innings_score")) == runs and played
                    and timedelta(days=-1) <= made - played <= timedelta(days=45)):
                out[id(e)] = (key, day)
                loose.remove(e)
                break
    # still not linked: look for the real match in the downloaded files (same teams, batting side and total)
    for e in list(loose):
        hit = _late_match(e) if _runs(e.get("first_innings_score")) is not None else None
        if hit:
            base = f"{_teams(e)}|{str(e.get('format') or '').upper()}"
            out[id(e)] = (f"m|{base}|{hit['date']}", hit["date"])
            if late is not None:
                late[id(e)] = hit
            loose.remove(e)
    groups: list[dict[str, Any]] = []
    for e in sorted(loose, key=lambda x: str(x.get("timestamp") or "")):
        base = f"{_teams(e)}|{str(e.get('format') or '').upper()}"
        made, score = _d(e.get("timestamp")), e.get("first_innings_score")

        def same(x: dict[str, Any]) -> bool:
            other = _d(x.get("timestamp"))
            if not made or not other:
                return False
            if made == other:
                return True
            return score is not None and x.get("first_innings_score") == score and abs((made - other).days) <= 2

        home = next((g for g in groups if g["base"] == base and any(same(x) for x in g["saves"])), None)
        if home is None:
            home = {"base": base, "saves": []}
            groups.append(home)
        home["saves"].append(e)
    for g in groups:
        first = str(g["saves"][0].get("timestamp") or "")[:10]
        last = str(g["saves"][-1].get("timestamp") or "")[:10]
        for e in g["saves"]:
            out[id(e)] = (f"s|{g['base']}|{first}", last)
    return out


def _busy_elsewhere(e: dict[str, Any], results: list[dict[str, Any]], live: list[dict[str, Any]]) -> bool:
    """One of the two teams played a different real match within a day of the save: so it wasn't this match."""
    made = _d(e.get("timestamp"))
    if not made:
        return False
    key = ml_model._team_key
    a, b = key(str(e.get("batting_first_team") or "")), key(str(e.get("chasing_team") or ""))
    for m in [*results, *live]:
        played = _d(m.get("date"))
        if not played or abs((played - made).days) > 1:
            continue
        pair = {key(str(m.get("team1") or "")), key(str(m.get("team2") or ""))}
        if pair != {a, b} and (a in pair or b in pair):
            return True
    return False


def enrich(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Add an 'outcome' to every history entry and a summary of how often predictions were right."""
    results, latest = _results()
    latest_d = _d(latest)
    live = _live()
    late: dict[int, dict[str, Any]] = {}
    keys = assign_matches(items, results, live, late)

    def key_of(entry: dict[str, Any]) -> str:
        return keys[id(entry)][0] if id(entry) in keys else match_key(entry)

    # a result you enter is a fact about the match, so it also settles the other saves of that match (e.g. the
    # innings-break prediction when you set the result on the live chase); the latest save with a result wins
    shared: dict[str, tuple[str, dict[str, Any]]] = {}
    for entry in items:
        if entry.get("actual"):
            k, ts = key_of(entry), str(entry.get("timestamp", ""))
            if k not in shared or ts > shared[k][0]:
                shared[k] = (ts, entry["actual"])
    out = []
    for entry in items:
        e = dict(entry)
        own = e.get("actual")
        manual = own or (shared.get(key_of(entry)) or (None, None))[1]
        if manual:  # set by the user (on this save, or on another save of the same match)
            winner = manual.get("winner")
            status = "no_result" if winner in (None, "", "No result", "Tie") else ("right" if winner == e.get("predicted_winner") else "wrong")
            from_check = not own and "model check" in str(manual.get("note") or "")
            e["outcome"] = {"status": status, "winner": winner, "source": "data" if from_check else "you",
                            "detail": (manual.get("note") or "Result entered by you") if own
                            else (str(manual.get("note")).split(" · ")[0] + " · result of this match" if from_check else "Result you entered for this match")}
        else:
            found = find_result(e, results)
            if found:
                winner = found.get("winner")
                if not winner:
                    status, detail = "no_result", f"{found.get('result') or 'No result'} · {found['date']} · {found['venue']}"
                else:
                    status = "right" if ml_model._team_key(e.get("predicted_winner", "")) == winner else "wrong"
                    detail = f"{winner} won {found.get('margin') or ''} · {found['date']} · {found['venue']}".replace("  ", " ")
                e["outcome"] = {"status": status, "winner": winner, "source": "data", "detail": detail}
            elif id(entry) in late:  # a past match predicted again: its result from the downloaded files
                hit = late[id(entry)]
                winner = hit.get("winner")
                if not winner:
                    status, detail = "no_result", f"No result · {hit['date']}"
                else:
                    status = "right" if ml_model._team_key(e.get("predicted_winner", "")) == ml_model._team_key(winner) else "wrong"
                    detail = f"{winner} won · played {hit['date']}"
                e["outcome"] = {"status": status, "winner": winner, "source": "data", "detail": detail}
            elif (live_hit := find_live(e, live)) is not None:  # not in Cricsheet yet: CricketData's recent results
                winner = live_hit.get("winner")
                if not winner:
                    status = "no_result"
                    detail = f"{'Tied' if live_hit['result'] == 'tie' else 'No result'} · {live_hit['date']} · from CricketData"
                else:
                    status = "right" if ml_model._team_key(e.get("predicted_winner", "")) == ml_model._team_key(winner) else "wrong"
                    detail = f"{winner} won by {live_hit.get('margin') or ''} · {live_hit['date']} · from CricketData".replace("  ", " ")
                e["outcome"] = {"status": status, "winner": winner, "source": "cricketdata", "detail": detail}
            else:
                made = _d(e.get("timestamp"))
                waiting_for_data = bool(made and latest_d and made + timedelta(days=WINDOW_AFTER) > latest_d)
                e["outcome"] = (
                    {"status": "waiting", "detail": f"Match data runs to {latest}. Download the latest data, or set the result yourself."}
                    if waiting_for_data else
                    {"status": "unmatched", "detail": "No real match between these teams around that date (a practice prediction?). Set the result if there was one."}
                )
        e["match_key"] = key_of(entry)
        e["match_date"] = keys[id(entry)][1] if id(entry) in keys else str(e.get("timestamp") or "")[:10]
        out.append(e)

    # practice runs: your saves that match no real match (no result in the data or CricketData and none found later,
    # or one of the teams was busy in another real match that day). They are listed apart and not counted.
    # A choice you made with the Practice run / Count as a real match buttons always wins.
    by_key: dict[str, list[dict[str, Any]]] = {}
    for e in out:
        if not e.get("auto"):
            by_key.setdefault(e["match_key"], []).append(e)
    for saves in by_key.values():
        chosen = [s for s in sorted(saves, key=lambda s: str(s.get("timestamp", ""))) if "practice" in s]
        if chosen:
            practice, why = bool(chosen[-1]["practice"]), "you marked it as practice"
        elif saves[0]["match_key"].startswith("m|"):
            practice, why = False, ""
        elif any(s["outcome"]["status"] == "unmatched" for s in saves):
            practice, why = True, "no real match between these teams around that date"
        elif any(_busy_elsewhere(s, results, live) for s in saves):
            practice, why = True, "one of these teams played a different match that day"
        else:
            practice, why = False, ""
        for s in saves:
            s["is_practice"] = practice
            if practice:
                s["practice_reason"] = why

    # one match = one prediction: a match saved several times (Predict pressed again, innings break then live chase)
    # counts once, by its latest save, your final call. History still shows every save.
    latest_per: dict[str, dict[str, Any]] = {}
    for e in out:
        k = e["match_key"]
        if k not in latest_per or str(e.get("timestamp", "")) > str(latest_per[k].get("timestamp", "")):
            latest_per[k] = e
    for e in out:
        e["counted"] = any(v is e for v in latest_per.values()) and not e.get("is_practice")
    full = out
    out = [e for e in full if e["counted"]]

    def score(entries: list[dict[str, Any]]) -> dict[str, Any]:
        decided = [x for x in entries if x["outcome"]["status"] in ("right", "wrong")]
        right = sum(1 for x in decided if x["outcome"]["status"] == "right")
        return {"checked": len(decided), "right": right, "pct": round(right * 100 / len(decided), 1) if decided else None}

    summary = {
        "total": len(out),
        "waiting": sum(1 for x in out if x["outcome"]["status"] == "waiting"),
        "unmatched": sum(1 for x in out if x["outcome"]["status"] == "unmatched"),
        "no_result": sum(1 for x in out if x["outcome"]["status"] == "no_result"),
        "all": score(out),
        "first_innings": score([x for x in out if x.get("type") != "chase"]),
        "live_chase": score([x for x in out if x.get("type") == "chase"]),
        "data_through": latest,
    }
    summary["tracker"] = tracker(out, score)
    summary["matches"] = len({e["match_key"] for e in full})
    summary["saves"] = len(full)
    summary["practice"] = len({e["match_key"] for e in full if e.get("is_practice")})
    return full, summary


def match_key(e: dict[str, Any]) -> str:
    """Which match a saved prediction belongs to: the two teams, the format and the day it was saved."""
    return "|".join([str(e.get("mode") or ""), str(e.get("batting_first_team") or ""), str(e.get("chasing_team") or ""),
                     str(e.get("format") or "").upper(), str(e.get("timestamp") or "")[:10]])


STAGES = {"pre_match": "Before the match", "mid_innings": "During 1st innings", "innings_break": "At the innings break",
          "chase": "Live chase", "unknown": "Older saves (stage not recorded)"}
BUCKETS = ((50, 60), (60, 70), (70, 80), (80, 101))


def tracker(out: list[dict[str, Any]], score) -> dict[str, Any]:
    """Your own hit rate: by stage, by how confident the call was, by competition, by team, and over time."""
    decided = [x for x in out if x["outcome"]["status"] in ("right", "wrong")]

    def stage(x: dict[str, Any]) -> str:
        return x.get("stage") or ("chase" if x.get("type") == "chase" else "unknown")

    def conf(x: dict[str, Any]) -> float:
        return max(float(x.get("batting_first_win_probability") or 50), float(x.get("chasing_win_probability") or 50))

    by_stage = [{"key": k, "label": v, **score([x for x in out if stage(x) == k])} for k, v in STAGES.items()]
    by_conf = []
    for lo, hi in BUCKETS:
        part = [x for x in decided if lo <= conf(x) < hi]
        s = score(part)
        s["expected"] = round(sum(conf(x) for x in part) / len(part), 1) if part else None  # what the model said, on average
        by_conf.append({"label": f"{lo}–{min(hi, 100)}%", **s})
    teams: dict[str, list] = {}
    for x in out:
        for t in (x.get("batting_first_team"), x.get("chasing_team")):
            if t:
                teams.setdefault(t, []).append(x)
    by_team = sorted(({"team": t, **score(v)} for t, v in teams.items()), key=lambda r: (-r["checked"], r["team"]))
    by_team = [r for r in by_team if r["checked"]][:12]
    by_mode = [{"label": label, **score([x for x in out if (x.get("mode") or "") == key])}
               for key, label in (("ipl", "IPL"), ("international", "International"))]
    # running hit rate, oldest first
    timeline, right = [], 0
    for i, x in enumerate(sorted(decided, key=lambda e: e.get("timestamp", "")), 1):
        right += x["outcome"]["status"] == "right"
        timeline.append({"n": i, "date": (x.get("timestamp") or "")[:10], "pct": round(right * 100 / i, 1),
                         "right": x["outcome"]["status"] == "right"})
    streak = 0
    for x in sorted(decided, key=lambda e: e.get("timestamp", ""), reverse=True):
        if x["outcome"]["status"] != "right":
            break
        streak += 1
    return {"by_stage": [s for s in by_stage if s["checked"] or s["key"] != "unknown"], "by_confidence": by_conf,
            "by_team": by_team, "by_mode": by_mode, "timeline": timeline[-200:], "streak": streak}


def _archives() -> list:
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "data"
    return [root / "cricsheet_odis.zip", root / "cricsheet_t20s.zip", root / "cricsheet_ipl.zip"]


def _wanted(info: dict[str, Any]) -> bool:
    return info.get("gender") == "male"


def _totals_path():
    from pathlib import Path
    return Path(__file__).resolve().parents[1] / "data" / "ml" / "first_innings_totals.json"


_TOTALS_PATH = _totals_path()


# ---- first-innings totals of every match since 2024, read once from the downloaded Cricsheet files and cached, so a
# save made long after its match (a past match predicted again) can be linked to the real match by its score
TOTALS_SINCE = "2024-01-01"
_TOTALS: dict[str, Any] = {}
_TOTALS_LOCK = __import__("threading").Lock()


def first_innings_totals() -> list[dict[str, Any]]:
    """[{date, format, bat, chase, total, wickets, winner}] for every finished match since 2024 (this app's kind).
    One reader at a time: a second caller waits and then gets the same cached rows."""
    with _TOTALS_LOCK:
        return _read_totals()


def _read_totals() -> list[dict[str, Any]]:
    import json
    import zipfile
    archives = [p for p in _archives() if p.exists()]
    stamp = [[str(p), p.stat().st_mtime_ns, p.stat().st_size] for p in archives]
    if _TOTALS.get("stamp") == stamp:
        return _TOTALS["rows"]
    try:
        saved = json.loads(_TOTALS_PATH.read_text(encoding="utf-8"))
        if saved.get("stamp") == stamp:
            _TOTALS.update(saved)
            return saved["rows"]
    except (OSError, ValueError):
        pass
    rows: list[dict[str, Any]] = []
    for path in archives:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if not name.endswith(".json"):
                    continue
                try:
                    d = json.loads(z.read(name))
                except ValueError:
                    continue
                info = d.get("info") or {}
                day = (info.get("dates") or [""])[0]
                if day < TOTALS_SINCE or not d.get("innings") or not _wanted(info):
                    continue
                first = d["innings"][0]
                teams = info.get("teams") or []
                balls = [b for o in first.get("overs", []) for b in o.get("deliveries", [])]
                rows.append({
                    "date": day, "format": "odi" if info.get("match_type") == "ODI" else "t20",
                    "bat": first.get("team", ""), "chase": next((t for t in teams if t != first.get("team")), ""),
                    "total": sum(b["runs"]["total"] for b in balls), "wickets": sum(len(b.get("wickets", [])) for b in balls),
                    "winner": (info.get("outcome") or {}).get("winner"),
                })
    _TOTALS.update({"stamp": stamp, "rows": rows})
    try:
        _TOTALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _TOTALS_PATH.write_text(json.dumps({"stamp": stamp, "rows": rows}), encoding="utf-8")
    except OSError:
        pass
    return rows


def _late_match(e: dict[str, Any]) -> dict[str, Any] | None:
    """The real match a late save was for: same two teams, format, batting side and first-innings total, played up
    to a year before the save (when several fit, the one with the same wickets, then the most recent)."""
    runs, made = _runs(e.get("first_innings_score")), _d(e.get("timestamp"))
    if runs is None or not made:
        return None
    key = ml_model._team_key
    bat, chase = key(str(e.get("batting_first_team") or "")), key(str(e.get("chasing_team") or ""))
    fmt = "odi" if str(e.get("format") or "").upper() == "ODI" else "t20"
    fits = [r for r in first_innings_totals()
            if r["format"] == fmt and r["total"] == runs and key(r["bat"]) == bat and key(r["chase"]) == chase
            and timedelta(days=-1) <= made - (_d(r["date"]) or made) <= timedelta(days=400)]
    wk = e.get("wickets")
    if wk is not None and any(r["wickets"] == wk for r in fits):
        fits = [r for r in fits if r["wickets"] == wk]
    return max(fits, key=lambda r: r["date"]) if fits else None

def warm_totals() -> None:
    """Read the match totals in the background (after a data update, and when the app starts), so History never
    waits for them. Does nothing when the cache is already up to date."""
    import threading

    def run() -> None:
        try:
            first_innings_totals()
        except Exception:  # noqa: BLE001 - an extra; History reads them itself if this fails
            pass
    threading.Thread(target=run, daemon=True, name="match-totals").start()
