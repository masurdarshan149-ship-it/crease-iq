"""Recent results from CricketData.org (free plan: 100 calls a day), so saved predictions can be checked before
Cricsheet publishes the match (Cricsheet stays the source the models learn from).

The API key lives in data/cricketdata_key.txt (you paste it there; data/ is never committed). Without it nothing
here does anything. Results are kept in data/cricketdata_cache.json; the History check only reads that file, it
never calls the internet. A refresh reads every page of CricketData's "current matches" list (25 per call) and stops
well before the daily limit.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
KEY_PATH = Path(os.environ.get("CRICKETDATA_KEY_PATH") or ROOT / "data" / "cricketdata_key.txt")
CACHE_PATH = Path(os.environ.get("CRICKETDATA_CACHE_PATH") or ROOT / "data" / "cricketdata_cache.json")
URL = "https://api.cricapi.com/v1/currentMatches"
DAILY_LIMIT = 100
BUDGET = 90          # this app stops at 90 calls a day (of the free plan's 100), leaving a little room
MAX_PAGES = 8        # 25 matches a page
REFRESH_EVERY = 3 * 3600  # automatic check every 3 hours while the app runs (about 6 calls each)
KEEP_DAYS = 45
UA = {"User-Agent": "Crease-IQ/1.0 (local cricket predictor)"}
_lock = threading.Lock()


def _key() -> str:
    try:
        return KEY_PATH.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def has_key() -> bool:
    return bool(_key())


def load() -> dict[str, Any]:
    try:
        c = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    for m in c.get("matches", []):  # results saved before these were added: work them out
        if not m.get("format"):
            m["format"] = _format_of({"name": m.get("name")})
        m["shortened"] = shortened(m.get("status"))
    return c


def _save(cache: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_name(CACHE_PATH.name + ".tmp")
    tmp.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    tmp.replace(CACHE_PATH)


# ---- the daily call count: ONE count per key, shared by every thread and process that uses it (Big Bash runs BBL and
# WBBL as two processes on one key). Every CricketData request goes through _call(), which holds a lock across
# "is there room?", the request and the new count, so overlapping fetches can't both slip past the cap.
HITS_PATH = Path(os.environ.get("CRICKETDATA_HITS_PATH") or KEY_PATH.with_name("cricketdata_hits.json"))
_call_lock = threading.Lock()


class BudgetError(RuntimeError):
    """Not enough of today's calls left for this request."""


class KeyRejected(BudgetError):
    """CricketData refused the key ("Invalid API Key", or its own daily limit reached): calls pause until tomorrow, or
    until the key file changes (a new key is tried straight away)."""


def _key_tag() -> str:
    """A short fingerprint of the key in use (not the key), so a pause ends as soon as you paste a new key."""
    import hashlib
    k = _key() or ""
    return hashlib.sha256(k.encode("utf-8")).hexdigest()[:10] if k else ""


def paused() -> str:
    """Why CricketData calls are paused today ("" when they aren't)."""
    try:
        h = json.loads(HITS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if h.get("date") == date.today().isoformat() and h.get("paused") and h.get("paused_key") == _key_tag():
        return str(h["paused"])
    return ""


class _KeyLock:
    """Thread lock + a lock file next to the count (other processes using the same key wait for it)."""

    def __init__(self) -> None:
        self.path = HITS_PATH.with_name(HITS_PATH.name + ".lock")

    def __enter__(self):
        _call_lock.acquire()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        end = time.time() + 180
        while True:
            try:
                os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 120:  # left behind by a stopped app
                        self.path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.time() > end:
                    _call_lock.release()
                    raise BudgetError("CricketData is busy with another request; try again in a moment")
                time.sleep(0.2)

    def __exit__(self, *exc) -> None:
        try:
            self.path.unlink(missing_ok=True)
        finally:
            _call_lock.release()


def used_today() -> int:
    """Calls used today on this app's key (CricketData's own count after each request)."""
    today = date.today().isoformat()
    try:
        h = json.loads(HITS_PATH.read_text(encoding="utf-8"))
        if h.get("date") == today:
            return int(h.get("used") or 0)
        return 0
    except (OSError, ValueError):
        c = load()  # before the shared count existed, the cache kept it
        return int(c.get("hits_today") or 0) if c.get("hits_date") == today else 0


def _set_used(n: int, pause: str | None = None) -> None:
    """Save today's count; `pause` (a reason) stops calls on this key until tomorrow. An existing pause is kept."""
    today = date.today().isoformat()
    try:
        old = json.loads(HITS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    rec = {"date": today, "used": int(n)}
    if pause:
        rec.update(paused=pause, paused_key=_key_tag())
    elif old.get("date") == today and old.get("paused"):
        rec.update(paused=old["paused"], paused_key=old.get("paused_key"))
    tmp = HITS_PATH.with_name(HITS_PATH.name + ".tmp")
    tmp.write_text(json.dumps(rec), encoding="utf-8")
    tmp.replace(HITS_PATH)


def _call(name: str, params: dict[str, Any], cost: int = 1) -> dict[str, Any]:
    """One CricketData request, only if `cost` calls still fit under BUDGET today; the count is updated before the
    lock is let go. Raises BudgetError when there's no room."""
    with _KeyLock():
        why = paused()
        if why:
            raise KeyRejected(f"CricketData refused the key earlier today ({why}). Calls are paused until tomorrow, "
                              "or until you put a new key in data/cricketdata_key.txt.")
        used = used_today()
        if used + cost > BUDGET:
            raise BudgetError(f"Not enough calls left today ({used} used, this needs about {cost}; this app stops at {BUDGET})")
        try:
            d = _get_endpoint(name, params)
        except Exception:
            _set_used(used + cost)  # it may have been counted by CricketData anyway: assume it was
            raise
        info = d.get("info") or {}
        if str(d.get("status") or "").lower() == "failure":
            reason = str(d.get("reason") or "CricketData refused the request")
            key_problem = re.search(r"api ?key|apikey|hits|limit|blocked|expired", reason, re.I)
            _set_used(int(info.get("hitsToday") or used + cost), pause=reason if key_problem else None)
            _note_error(reason)
            raise (KeyRejected if key_problem else BudgetError)(f"CricketData said: {reason}")
        _set_used(int(info.get("hitsToday") or used + cost))
        return d


def _note_error(reason: str) -> None:
    """Keep the last refusal where the Data page shows it (any call, not only the results refresh)."""
    try:
        cache = load()
        cache["last_error"] = reason
        cache["last_error_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        _save(cache)
    except Exception:  # noqa: BLE001 - never let a note break a request
        pass


WON = re.compile(r"^(?P<team>.+?) won by (?P<margin>.+)$", re.I)
# rain-shortened matches (overs cut, DLS / VJD targets): the models are built on full-length matches only, so these
# are never checked against the model (their result still settles your own predictions)
SHORT = re.compile(r"\bDLS\b|\bD/L\b|\bVJD\b|reduced to|\d+\s*-?\s*overs? (?:game|match|a side)|\(\d+\s*overs?\)", re.I)


def shortened(status: str) -> bool:
    return bool(SHORT.search(str(status or "")))


def winner_of(status: str) -> str | None:
    """'India won by 5 wkts' -> 'India'; ties, no results and anything else -> None."""
    m = WON.match(str(status or "").strip())
    return m.group("team").strip() if m else None


def _format_of(m: dict[str, Any]) -> str:
    """CricketData leaves matchType empty for some ODIs; then the match name says it ('3rd ODI', '1st T20I')."""
    t = str(m.get("matchType") or "").lower()
    if t:
        return t
    name = str(m.get("name") or "").lower()
    for word, fmt in (("odi", "odi"), ("one-day", "odi"), ("t20", "t20"), ("test", "test")):
        if re.search(rf"\b{word}", name):
            return fmt
    return ""


def _normal(m: dict[str, Any]) -> dict[str, Any] | None:
    teams = [str(t) for t in (m.get("teams") or [])][:2]
    if len(teams) != 2 or not m.get("matchEnded"):
        return None
    status = str(m.get("status") or "")
    win = winner_of(status)
    margin = WON.match(status.strip()).group("margin").strip() if win else ""
    low = status.lower()
    result = "won" if win else ("tie" if "tied" in low else "no_result" if ("no result" in low or "abandon" in low) else "")
    if not result:
        return None
    return {
        "id": str(m.get("id") or ""), "date": str(m.get("date") or str(m.get("dateTimeGMT") or "")[:10])[:10],
        "format": _format_of(m), "name": str(m.get("name") or ""),
        "team1": teams[0], "team2": teams[1], "winner": win, "margin": margin, "result": result,
        "status": status, "venue": str(m.get("venue") or ""),
        "women": any(t.lower().endswith(" women") for t in teams),
    }


def _get(params: dict[str, Any]) -> dict[str, Any]:
    url = URL + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


def refresh(force: bool = False) -> dict[str, Any]:
    """Fetch the latest results if due (or forced) and within budget. Never raises; returns the cache with a note."""
    key = _key()
    if not key:
        return {**load(), "note": "No CricketData key in data/cricketdata_key.txt"}
    with _lock:
        cache = load()
        last = cache.get("fetched_ts") or 0
        if not force and time.time() - last < REFRESH_EVERY:
            return {**cache, "note": "Checked recently"}
        if used_today() >= BUDGET:
            return {**cache, "note": f"Daily budget of {BUDGET} calls used; next check tomorrow"}
        found: dict[str, dict[str, Any]] = {m["id"]: m for m in cache.get("matches", []) if m.get("id")}
        offset, pages, error = 0, 0, ""
        try:
            while pages < MAX_PAGES:
                try:
                    d = _call("currentMatches", {"apikey": key, "offset": offset})
                except BudgetError as err:
                    error = str(err)
                    break
                pages += 1
                info = d.get("info") or {}
                cache["hits_limit"] = int(info.get("hitsLimit") or DAILY_LIMIT)
                if d.get("status") != "success":
                    error = str(d.get("reason") or "CricketData said no")
                    break
                for raw in d.get("data") or []:
                    m = _normal(raw)
                    if m and m["id"]:
                        found[m["id"]] = m
                total = int(info.get("totalRows") or 0)
                offset += len(d.get("data") or [])
                if not d.get("data") or offset >= total:
                    break
        except Exception as err:  # noqa: BLE001 - offline / timeout / bad reply: keep what we had
            error = str(err).replace(key, "<key>")
        cutoff = (date.today() - timedelta(days=KEEP_DAYS)).isoformat()
        cache["matches"] = sorted((m for m in found.values() if m["date"] >= cutoff), key=lambda m: m["date"], reverse=True)
        cache["fetched_ts"] = time.time() if not error or pages > 1 else last
        cache["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        cache["last_error"] = error
        cache["pages"] = pages
        _save(cache)
        return {**cache, "note": error or f"Updated ({pages} call{'s' if pages != 1 else ''})"}


# ---- finding recent tours / leagues (CricketData's "current matches" list only covers a few days)
SKIP_SERIES = ("women", "under 19", "u19", "u-19", " a tour", "emerging", "legends", "masters")


def _hits_left() -> int:
    return BUDGET - used_today()


def discover(since: str, wanted: set[str]) -> dict[str, Any]:
    """Find tours / leagues that ran after `since` (the newest match in the ball-by-ball data) involving the app's
    teams (`wanted`: team names, plus 'indian premier league'), and add their finished matches to the recent results.
    Done at most once a day: about 3 calls for the series list plus 1 per series found."""
    key = _key()
    if not key:
        return {"error": "No CricketData key"}
    c = load()
    today = date.today().isoformat()
    if c.get("discovered") == today:
        return {"note": "Already looked today"}
    found, offset, error = [], 0, ""
    try:
        for _ in range(5):  # the list is newest first (including future tours); stop once it's older than `since`
            d = _call("series", {"apikey": key, "offset": offset})
            rows = d.get("data") or []
            for s in rows:
                start = str(s.get("startDate") or "")
                if len(start) != 10 or start > today:
                    continue
                name = str(s.get("name") or "")
                low = name.lower()
                if any(w in low for w in SKIP_SERIES) or not any(t.lower() in low for t in wanted):
                    continue
                if start >= (date.fromisoformat(since) - timedelta(days=75)).isoformat():
                    found.append({"id": s.get("id"), "name": name, "start": start})
            offset += len(rows)
            starts = [str(s.get("startDate") or "") for s in rows if len(str(s.get("startDate") or "")) == 10]
            if not rows or (starts and min(starts) < (date.fromisoformat(since) - timedelta(days=75)).isoformat()):
                break
        added = 0
        for s in found[:8]:
            d = _call("series_info", {"apikey": key, "id": s["id"]})
            added += _add_matches((d.get("data") or {}).get("matchList") or [])
    except BudgetError as err:
        error = str(err)
    except Exception as err:  # noqa: BLE001
        error = str(err).replace(key, "<key>")
    with _lock:
        c = load()
        if not error:
            c["discovered"] = today
        c["series_found"] = [s["name"] for s in found]
        _save(c)
    return {"note": error or f"Found {len(found)} recent series", "series": [s["name"] for s in found], "error": error}


def _add_matches(raw_list: list[dict[str, Any]]) -> int:
    with _lock:
        c = load()
        have = {m["id"]: i for i, m in enumerate(c.get("matches", []))}
        n = 0
        for raw in raw_list:
            m = _normal(raw)
            if not m or not m["id"]:
                continue
            if m["id"] in have:
                c["matches"][have[m["id"]]] = m
            else:
                c.setdefault("matches", []).append(m)
                n += 1
        c["matches"].sort(key=lambda m: m["date"], reverse=True)
        _save(c)
    return n


# ---- scorecards (CricketData charges about 10 calls each on the free plan, so each is fetched once and kept)
SCORECARD_PATH = Path(os.environ.get("CRICKETDATA_SCORECARD_PATH") or ROOT / "data" / "cricketdata_scorecards.json")
SCORECARD_COST = 10


def _scorecards() -> dict[str, Any]:
    try:
        return json.loads(SCORECARD_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def scorecard(match_id: str) -> dict[str, Any] | None:
    card = _scorecards().get(str(match_id))
    return _tidy_titles(card) if card else None


def _tidy_titles(card: dict[str, Any]) -> dict[str, Any]:
    """CricketData's innings labels can be messy ('england', 'Australia,England'): name each innings by its batting
    team, using the two teams in the match name ('Australia vs England, 3rd ODI, ...')."""
    head = str(card.get("name") or "").split(",")[0]
    teams = [t.strip() for t in head.split(" vs ")] if " vs " in head else []
    if len(teams) != 2:
        return card
    prev = None
    for inn in card.get("innings", []):
        hits = [t for t in teams if t.lower() in str(inn.get("title") or "").lower()]
        if len(hits) == 1:
            team = hits[0]
        else:  # both or neither named: innings alternate, so it's the side that didn't bat last
            team = teams[1] if prev == teams[0] else teams[0]
        inn["title"], prev = team, team
    return card


def _num(v: Any) -> float | int | None:
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return None


def normal_scorecard(data: dict[str, Any]) -> dict[str, Any]:
    """CricketData's match_scorecard reply -> the fields the Replay card shows."""
    score = {str(s.get("inning", "")).lower(): s for s in data.get("score") or []}
    innings = []
    for inn in data.get("scorecard") or []:
        title = str(inn.get("inning") or "")
        tot = score.get(title.lower(), {})
        innings.append({
            "title": title.replace(" Inning 1", "").replace(" Inning 2", " (2nd innings)"),
            "runs": _num(tot.get("r")), "wickets": _num(tot.get("w")), "overs": _num(tot.get("o")),
            "batting": [{"name": (b.get("batsman") or {}).get("name", ""), "how": b.get("dismissal-text") or "",
                         "r": _num(b.get("r")), "b": _num(b.get("b")), "fours": _num(b.get("4s")), "sixes": _num(b.get("6s")),
                         "sr": _num(b.get("sr"))} for b in inn.get("batting") or []],
            "bowling": [{"name": (w.get("bowler") or {}).get("name", ""), "o": _num(w.get("o")), "m": _num(w.get("m")),
                         "r": _num(w.get("r")), "w": _num(w.get("w")), "eco": _num(w.get("eco")),
                         "wd": _num(w.get("wd")), "nb": _num(w.get("nb"))} for w in inn.get("bowling") or []],
        })
    toss = f"{str(data.get('tossWinner') or '').title()} won the toss and chose to {data.get('tossChoice')}" if data.get("tossWinner") else ""
    return {"id": str(data.get("id") or ""), "name": data.get("name") or "", "date": str(data.get("date") or "")[:10],
            "venue": data.get("venue") or "", "status": data.get("status") or "", "winner": data.get("matchWinner") or "",
            "toss": toss, "innings": innings, "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M")}


def save_scorecard(data: dict[str, Any]) -> dict[str, Any]:
    card = normal_scorecard(data)
    with _lock:
        cards = _scorecards()
        cards[card["id"]] = card
        SCORECARD_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SCORECARD_PATH.with_name(SCORECARD_PATH.name + ".tmp")
        tmp.write_text(json.dumps(cards, indent=1), encoding="utf-8")
        tmp.replace(SCORECARD_PATH)
    return card


def fetch_scorecard(match_id: str) -> dict[str, Any]:
    """Get one scorecard from CricketData (about 10 calls), unless it's already saved or the budget can't cover it."""
    have = scorecard(match_id)
    if have:
        return {"card": have, "note": "Already saved"}
    key = _key()
    if not key:
        return {"error": "No CricketData key in data/cricketdata_key.txt"}
    try:
        d = _call("match_scorecard", {"apikey": key, "id": match_id}, SCORECARD_COST)
    except BudgetError as err:
        return {"error": str(err)}
    except Exception as err:  # noqa: BLE001
        return {"error": str(err).replace(key, "<key>")}
    if d.get("status") != "success" or not isinstance(d.get("data"), dict):
        return {"error": str(d.get("reason") or "CricketData has no scorecard for this match")}
    return {"card": save_scorecard(d["data"]), "note": "Scorecard saved"}


def saved_check(match_id: str, stamp: str) -> dict[str, Any] | None:
    """The model's innings-break check for a match, as worked out by the current model (`stamp` = when it was trained)."""
    card = _scorecards().get(str(match_id)) or {}
    chk = card.get("check")
    return chk if chk and chk.get("stamp") == stamp else None


def save_check(match_id: str, check: dict[str, Any], stamp: str) -> None:
    """Keep the check with its scorecard, so History and the Last-N view don't rerun the model every time."""
    with _lock:
        cards = _scorecards()
        if str(match_id) not in cards:
            return
        cards[str(match_id)]["check"] = {**check, "stamp": stamp}
        tmp = SCORECARD_PATH.with_name(SCORECARD_PATH.name + ".tmp")
        tmp.write_text(json.dumps(cards, indent=1), encoding="utf-8")
        tmp.replace(SCORECARD_PATH)


def _get_endpoint(name: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"https://api.cricapi.com/v1/{name}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
        return json.load(r)


def status(known: set[str] | None = None) -> dict[str, Any]:
    """What the Data page shows: whether a key is set, when we last checked, calls used, latest results
    (only matches between teams the app knows, when `known` is given)."""
    c = load()
    men = [m for m in c.get("matches", []) if not m.get("women")
           and (not known or (m["team1"] in known and m["team2"] in known))]
    return {
        "enabled": has_key(), "fetched_at": c.get("fetched_at"), "last_error": c.get("last_error") or "",
        "last_error_at": c.get("last_error_at") or "", "paused": paused(),
        "hits_today": used_today(),  # the shared count for this key (all leagues / threads)
        "hits_limit": c.get("hits_limit", DAILY_LIMIT), "budget": BUDGET,
        "count": len(c.get("matches", [])),
        "men": men[:12],
    }


def start_background() -> None:
    """Check once shortly after the app starts, then every few hours, while the app runs (only with a key)."""
    if not has_key() or os.environ.get("CREASE_NO_LIVE_RESULTS"):
        return

    def loop() -> None:
        time.sleep(20)  # let the app finish starting first
        while True:
            try:
                refresh()
            except Exception:  # noqa: BLE001 - a background helper never takes the app down
                pass
            time.sleep(600)  # wakes every 10 minutes; refresh() itself only calls when 3 hours have passed

    threading.Thread(target=loop, daemon=True, name="cricketdata").start()


def look_for(teams: list[str], search: str | None = None) -> dict[str, Any]:
    """Find the series of one match (the link check's 'Look for it'): search CricketData's series by name, keep recent
    ones naming both teams (or the `search` words, e.g. "Indian Premier League"), and add their matches. Not limited to
    once a day; about 1 call per search word tried plus 1 per series found (usually 2 in all)."""
    key = _key()
    if not key:
        return {"error": "No CricketData key"}
    today = date.today()
    words = [search] if search else sorted(teams, key=len)  # the shorter name first (fewer, closer results)
    hits, added, error = [], 0, ""
    try:
        for w in words:
            d = _call("series", {"apikey": key, "offset": 0, "search": w})
            for s in d.get("data") or []:
                name = str(s.get("name") or "").lower()
                start = str(s.get("startDate") or "")[:10]
                if len(start) != 10 or start > today.isoformat() or start < (today - timedelta(days=150)).isoformat():
                    continue
                if (search and search.lower() in name) or (not search and all(t.lower() in name for t in teams)):
                    if not any(w in name for w in ("women",)):
                        hits.append(s)
            if hits:
                break
        for s in sorted(hits, key=lambda s: str(s.get("startDate")), reverse=True)[:2]:
            d = _call("series_info", {"apikey": key, "id": s.get("id")})
            added += _add_matches((d.get("data") or {}).get("matchList") or [])
    except BudgetError as err:
        error = str(err)
    except Exception as err:  # noqa: BLE001
        error = str(err).replace(key, "<key>")
    return {"note": error or f"Found {len(hits)} series", "series": [s.get("name") for s in hits], "error": error}
