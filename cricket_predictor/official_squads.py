"""Official squads from Wikipedia (its public API, which apps may use; text under CC BY-SA).

IPL: each team has a season page ("2026 Mumbai Indians season") with a "Squad" table that editors keep up to date
from the official announcements. The table's Name column is read; withdrawn players (marked with a dagger) are kept
apart. Internationals are not read automatically: tour pages lay squads out in too many different ways, so for them
the page offers the official site and the team sheet reader instead.

Nothing personal is sent: a generic app name is used as the User-Agent, as Wikipedia asks.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "CreaseIQ/1.0 (personal cricket predictor; Wikipedia API)"
TIMEOUT = 15


def _get(params: dict[str, Any]) -> dict[str, Any]:
    """One API request; a busy answer (429 / 5xx) or a dropped connection is tried again twice, a little later."""
    import time
    import urllib.error
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json", "formatversion": 2})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
                return json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 2:
                raise
        time.sleep(3 * (attempt + 1))
    raise OSError("Wikipedia didn't answer")


def _section_text(title: str, word: str = "squad") -> str | None:
    """The wikitext of the page's first section whose heading contains `word`, or None (no page / no section)."""
    try:
        sec = _get({"action": "parse", "page": title, "prop": "sections", "redirects": 1})
    except (OSError, ValueError):
        raise ValueError("Couldn't reach Wikipedia. Check the internet connection and try again.") from None
    if "error" in sec:
        return None
    index = next((s["index"] for s in sec.get("parse", {}).get("sections", []) if word in s.get("line", "").lower()), None)
    if index is None:
        return None
    try:
        got = _get({"action": "parse", "page": title, "prop": "wikitext", "section": index, "redirects": 1})
    except (OSError, ValueError):
        raise ValueError("Couldn't reach Wikipedia. Check the internet connection and try again.") from None
    return (got.get("parse") or {}).get("wikitext")


_LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_NOT_PLAYER = re.compile(r"^(?:File|Image|Category):|cricket team|Premier League|bowling|batting|Captain|Wicket", re.I)


def _cell_name(cell: str) -> str:
    """A Name cell -> the player's name: the link's shown text, or the plain text (bold marks, notes, refs removed)."""
    cell = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", cell, flags=re.S)
    m = _LINK.search(cell)
    if m:
        name = (m.group(2) or m.group(1)).strip()
    else:
        name = re.sub(r"\{\{[^}]*\}\}", "", cell)
    name = re.sub(r"'{2,}|\{\{[^}]*\}\}|<[^>]+>|[†*]", "", name)
    name = re.sub(r"\s*\(.*?\)\s*", " ", name)
    return " ".join(name.split()).strip(" '")


def parse_squad(wikitext: str) -> list[dict[str, Any]]:
    """Rows of the squad table -> [{"name", "withdrawn"}] in table order, read from the table's Name column (its
    place comes from the header row "! S/N || Name || Nationality ..."). Withdrawn players are marked with a dagger."""
    lines = wikitext.splitlines()
    # the header: one line for all columns ("! S/N || Name || ...", IPL pages) or one line per column
    # ('! style="..." |Name', Big Bash pages); it ends at the first row break after it
    heads: list[str] = []
    started = False
    for l in lines:
        s = l.strip()
        if s.startswith("!"):
            started = True
            for h in re.split(r"!!|\|\|", s[1:]):
                heads.append(re.sub(r"\{\{[^}]*\}\}|'''?", "", h).split("|")[-1].strip())
        elif started and s.startswith("|-"):
            break
    col = next((i for i, h in enumerate(heads) if re.fullmatch(r"(?:Player\s+)?Name", h, re.I)), None)
    if col is None:
        return []
    players: list[dict[str, Any]] = []
    seen: set[str] = set()
    # the caption ("|+ ... squad for the ...") and the header lines are not players
    body = "\n".join(l for l in lines if not l.lstrip().startswith(("|+", "{|", "|}")))
    for row in re.split(r"\n\|-", body):
        # a row starts with its own settings ('style="text-align:center"'); the cells follow on lines starting "|"
        # (several on one line split by "||", or one per line); group headings ("! Batters") are not rows
        rows = row.split("\n")
        text = "\n".join(rows[1:] if rows and not rows[0].lstrip().startswith("|") else rows).strip()
        if not text.startswith("|"):
            continue
        cells = [c.strip() for c in re.split(r"\|\||\n\|", text.lstrip("|"))]
        if len(cells) <= col:
            continue
        name = _cell_name(cells[col])
        if len(name.split()) < 2 or len(name) > 40 or name in seen or _NOT_PLAYER.search(name):
            continue
        seen.add(name)
        players.append({"name": name, "withdrawn": bool(re.search(r"\{\{\s*dagger|†", row, re.I))})
    return players


def ipl_squad(team_name: str, today: date | None = None) -> dict[str, Any]:
    """The team's current IPL squad: this year's season page, or last year's if this season's has no squad yet."""
    year = (today or date.today()).year
    for y in (year, year - 1):
        title = f"{y} {team_name} season"
        text = _section_text(title)
        if text:
            players = parse_squad(text)
            if len(players) >= 11:
                return {"found": True, "title": title, "season": y, "players": players,
                        "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))}
    return {"found": False, "note": f"No {year} or {year - 1} squad for {team_name} on Wikipedia yet."}
