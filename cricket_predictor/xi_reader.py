"""Playing XIs from a team sheet: a picture (read by Windows, see pitch_report.image_text) or a pasted list.

Each name is matched, in this order, to
  1. the team's squad ("SK Yadav", "Suryakumar Yadav" or "Yadav" -> the squad's name),
  2. any player in the match data (a player who changed teams, or plays another format),
  3. otherwise it is kept as a new player under the name as read (the model treats unknown players as
     average-level debutants with no experience).
A name that is close to a squad player but not certain ("M Santnar") is marked "check" with suggestions, so it is
never swapped silently. The order of the names is kept: team sheets list players in batting order.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

MARKERS = re.compile(r"\((?:c|w|k|wk|vc|capt|captain|w/k|c\s*&\s*wk|c/wk|wk/c)\)|[†*©®✝+]|\b(?:captain|capt|vice-captain|wicketkeeper|wicket-keeper|wk)\b", re.I)
ROLE_WORDS = {"batter", "batsman", "bowler", "allrounder", "all-rounder", "all", "rounder", "keeper", "bat", "bowl",
              "opener", "spinner", "pacer", "seamer", "rhb", "lhb", "rf", "rm", "lm", "sla", "ob", "lb", "rfm", "lfm"}
HEADING_WORDS = {"playing", "xi", "11", "team", "teams", "lineup", "line-up", "line", "up", "squad", "toss", "vs", "v",
                 "won", "elected", "bat", "bowl", "field", "first", "match", "today", "tonight", "the", "and", "of",
                 "announced", "confirmed", "batting", "bowling", "order", "news", "live"}
SUB_WORDS = re.compile(r"\b(?:impact|substitute|substitutes|subs|bench|reserves|replacement)\b", re.I)
SURE, MAYBE = 0.93, 0.74  # match strength: at or above SURE is used as is; between the two is shown as "check"


def _fold(s: str) -> str:
    return " ".join(re.sub(r"[^a-z' ]", " ", str(s).lower().replace("-", " ")).split())


def _title(s: str) -> str:
    particles = {"de", "van", "du", "der", "da", "von", "le", "la", "den", "ten"}
    return " ".join(w.lower() if (i and w.lower() in particles) else w if (w.isupper() and len(w) <= 2 and w.lower() not in particles)
                    else w[:1].upper() + w[1:].lower() for i, w in enumerate(s.split()))


def split_names(text: str) -> list[str]:
    """The text broken into pieces that may be names (lines, columns, commas, numbered lists)."""
    out = []
    for line in str(text or "").splitlines():
        for part in re.split(r"\s\|\s|[,;:•·|\t]|\s{3,}|(?:(?<=\s)|^)\d{1,2}\s*[.)]\s*|\s+-\s+", line):
            part = part.strip(" .:-–—'\"")
            if part:
                out.append(part)
    return out


def clean(piece: str) -> str:
    """'1. H Pandya (c)' -> 'H Pandya'; role words and markers removed."""
    s = MARKERS.sub(" ", piece)
    s = re.sub(r"[^A-Za-z.'\- ]", " ", s)
    words = [w.strip(".-'") for w in s.split()]
    words = [w for w in words if w and w.lower().strip(".") not in ROLE_WORDS]
    while len(words) > 2 and len(words[-1]) == 1:  # a stray letter after the surname ("Rickelton w")
        words.pop()
    return " ".join(words)


def _score(read: str, name: str) -> float:
    """How well a piece read from the sheet matches a squad name (1 = the same)."""
    a, b = _fold(read), _fold(name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    pa, pb = a.split(), b.split()
    if pa[-1] == pb[-1]:  # same surname
        if len(pa) == 1:
            return 0.93  # surname only ("Jacks"); only used when it is the only one in the squad
        ga, gb = "".join(pa[:-1]), "".join(pb[:-1])  # given names, spaces ignored ("Suryakumar" = "Surya Kumar")
        if ga == gb:
            return 0.98
        if len(pa[0]) > 3 and len(pb[0]) > 3:  # both first names in full and different: "Karn" is not "Kartik"
            return 0.6 + 0.35 * SequenceMatcher(None, ga, gb).ratio()
        ia, ib = pa[0][0], pb[0][0]
        if ia == ib:
            return 0.97  # "SK Yadav" / "S Yadav" / "Suryakumar Yadav" v "SK Yadav"
        if len(pb[0]) <= 3 and pb[0].isalpha() and ia in pb[0]:
            return 0.95  # "Kumar Yadav" v "SK Yadav"
        return 0.6
    whole = SequenceMatcher(None, a, b).ratio()
    sur = SequenceMatcher(None, pa[-1], pb[-1]).ratio()
    same_initial = pa[0][0] == pb[0][0] if len(pa) > 1 and len(pb) > 1 else True
    return max(whole * 0.95, sur * (0.9 if same_initial else 0.7))


def _best(read: str, squad: list[str]) -> tuple[str | None, float, list[str]]:
    scored = sorted(((_score(read, n), n) for n in squad), reverse=True)
    if not scored or scored[0][0] < MAYBE:
        return None, 0.0, []
    top, name = scored[0]
    rivals = [n for s, n in scored[1:] if s >= top - 0.02]
    if rivals:  # two squad players fit equally well ("Sharma"): not sure which
        return name, min(top, SURE - 0.01), [name, *rivals][:3]
    return name, top, [n for s, n in scored[:3] if s >= MAYBE]


def _heading_side(piece: str, teams: dict[str, dict[str, Any]]) -> str | None:
    f = _fold(piece)
    for side, t in teams.items():
        names = {_fold(t.get("name", "")), _fold(t.get("code", ""))}
        if f and any(n and (f == n or (len(n) > 3 and n in f)) for n in names):
            return side
        # the start of the full name, at least two words: "ROYAL CHALLENGERS", "SUNRISERS HYDERABAD" (on a cramped graphic)
        full = _fold(t.get("name", ""))
        if len(f.split()) >= 2 and full.startswith(f + " "):
            return side
    # a short heading with the team's nickname: "SIXERS SQUAD", "Thunder XI" (only when the nickname is the other
    # team's too would it be unclear, e.g. two "Kings", so then it isn't used)
    words = f.split()
    if 0 < len(words) <= 4 and any(w in HEADING_WORDS for w in words):
        nick = {s: _fold(t.get("name", "")).split()[-1] for s, t in teams.items() if _fold(t.get("name", ""))}
        hits = [s for s, n in nick.items() if len(n) > 3 and n in words and list(nick.values()).count(n) == 1]
        if len(hits) == 1:
            return hits[0]
    return None


def _top(name: str, teams: dict[str, dict[str, Any]]) -> float:
    """The best match strength of a name against any of the squads."""
    return max((_best(name, t["squad"])[1] for t in teams.values() if t.get("squad")), default=0.0)


def _pieces(text: str, teams: dict[str, dict[str, Any]]) -> list[str]:
    """split_names, then two repairs for real team graphics:
    - a first name on one line and the surname on the next ("SEAN" / "ABBOTT") are joined when that matches better;
    - a line holding several names ("STEVE SMITH JOSH PHILIPPE SEAN ABBOTT") is cut into the names it contains."""
    raw = split_names(text)
    out: list[str] = []
    i = 0
    while i < len(raw):
        piece = raw[i]
        one = clean(piece).split()
        if len(one) == 1 and i + 1 < len(raw):
            nxt = clean(raw[i + 1]).split()
            if 1 <= len(nxt) <= 2 and not SUB_WORDS.search(raw[i + 1]):
                joined = f"{one[0]} {' '.join(nxt)}"
                singles = max(_top(one[0], teams), _top(" ".join(nxt), teams))
                known = _top(joined, teams) >= SURE and _top(joined, teams) > singles
                # two lone words that match nobody, neither a heading word: a new player's first name and surname
                newbie = (singles < MAYBE and _top(joined, teams) < MAYBE and one[0].isalpha() and len(one[0]) > 1
                          and not any(w.lower() in HEADING_WORDS for w in [one[0], *nxt]) and not _heading_side(piece, teams)
                          and not _heading_side(raw[i + 1], teams)
                          # don't borrow a first name that starts a known player with the line after it
                          and not (i + 2 < len(raw) and _top(f"{' '.join(nxt)} {clean(raw[i + 2])}", teams) >= SURE))
                if known or newbie:
                    out.append(f"{piece} {raw[i + 1]}")
                    i += 2
                    continue
        words = clean(piece).split()
        if len(words) > 4 and not _heading_side(piece, teams):
            found, j = [], 0
            while j < len(words):
                for n in (3, 2):
                    cand = " ".join(words[j:j + n])
                    if len(words[j:j + n]) == n and _top(cand, teams) >= SURE:
                        found.append(cand)
                        j += n
                        break
                else:
                    j += 1
            if found:
                out.extend(found)
                i += 1
                continue
        out.append(piece)
        i += 1
    return out


def _columns(text: str, teams: dict[str, dict[str, Any]]) -> tuple[str, bool]:
    """Two teams side by side under their names ("MUMBAI INDIANS | ROYAL CHALLENGERS", then "Rohit Sharma | Virat
    Kohli" ...): rewritten as one team's list after the other, so each column stays with the team named above it.
    Returns (text, True when it was rewritten)."""
    lines = str(text or "").splitlines()
    for i, line in enumerate(lines):
        parts = [p.strip() for p in line.split(" | ")]
        if len(parts) != 2:
            continue
        sides = [_heading_side(p, teams) for p in parts]
        if not all(sides) or sides[0] == sides[1]:
            continue
        cols: list[list[str]] = [[parts[0]], [parts[1]]]
        for row in lines[i + 1:]:
            cells = [c.strip() for c in row.split(" | ")]
            if len(cells) == 2:
                cols[0].append(cells[0])
                cols[1].append(cells[1])
            elif row.strip():  # a line across both columns (a footer, "Impact subs"): keep it after both lists
                cols[1].append(row.strip())
        return "\n".join([*lines[:i], *cols[0], *cols[1]]), True
    return text, False


def read(text: str, teams: dict[str, dict[str, Any]], want: str, lookup=None) -> dict[str, Any]:
    """teams: {"bat": {"name", "code", "squad": [names]}, "chase": {...}}; want: the side whose box was used.
    lookup(name, side) -> a name from the match data, or None. Returns what was found for each side."""
    other = "chase" if want == "bat" else "bat"
    text, by_column = _columns(text, teams)
    rows: list[dict[str, Any]] = []
    section, subs = None, False
    for piece in _pieces(text, teams):
        side = _heading_side(piece, teams)
        if side:
            section, subs = side, bool(SUB_WORDS.search(piece))
            continue
        if SUB_WORDS.search(piece):
            subs = True
            continue
        name = clean(piece)
        words = _fold(name).split()
        if not words or all(w in HEADING_WORDS for w in words) or len(re.sub(r"[^a-z]", "", name.lower())) < 3:
            continue
        if len(words) > 4:  # a sentence, not a name
            continue
        found = {s: _best(name, t["squad"]) for s, t in teams.items() if t.get("squad")}
        rows.append({"read": piece.strip(), "clean": name, "found": found, "section": section, "sub": subs})

    # one team or both? Both when several names belong clearly to the other squad
    clear_other = sum(1 for r in rows if r["found"].get(other, (None, 0))[1] >= SURE
                      and r["found"].get(other, (None, 0))[1] > r["found"].get(want, (None, 0))[1])
    both = (clear_other >= 4 or by_column) and other in teams

    out: dict[str, dict[str, Any]] = {s: {"players": [], "subs": []} for s in ((want, other) if both else (want,))}
    ignored: list[str] = []
    taken: dict[str, set[str]] = {s: set() for s in out}
    for r in rows:
        f = r["found"]
        if both and by_column and r["section"] in out:
            side = r["section"]  # side-by-side columns under the team names: the column decides
        elif both:
            side = max(out, key=lambda s: (f.get(s, (None, 0))[1], s == r["section"]))
            if f.get(side, (None, 0))[1] < MAYBE and r["section"] in out:
                side = r["section"]
        else:
            side = want
            theirs = f.get(other, (None, 0.0))[1]
            if theirs >= SURE and theirs > f.get(want, (None, 0.0))[1]:
                continue  # the other team's player, on a sheet read for one team
        name, strength, options = f.get(side, (None, 0.0, []))
        if name and strength >= SURE and name not in taken[side]:
            item = {"read": r["read"], "name": name, "status": "squad"}
        elif name and strength >= MAYBE and name not in taken[side]:
            known = lookup(r["clean"], side) if lookup and len(r["clean"].split()) >= 2 else None
            if known and known not in options and known not in taken[side]:
                options = [*options, known]  # someone in the match data fits too: offer them as well
            item = {"read": r["read"], "name": name, "status": "check", "options": options, "as_read": _title(r["clean"])}
        else:
            known = lookup(r["clean"], side) if lookup and len(r["clean"].split()) >= 2 else None
            if known and known not in taken[side]:
                item = {"read": r["read"], "name": known, "status": "data"}
            elif known or (name and name in taken[side]):
                continue  # the same player read twice
            elif len(r["clean"].split()) < 2:
                ignored.append(r["read"])  # one word that matches nobody: a heading or a stray word, not a player
                continue
            else:
                item = {"read": r["read"], "name": _title(r["clean"]), "status": "new"}
        taken[side].add(item["name"])
        bucket = "subs" if r["sub"] else "players"
        out[side][bucket].append(item)
    for side, got in out.items():
        # 14 or more names: a full squad, not a playing XI (the page offers to save it as the squad instead)
        got["sheet"] = [p["name"] for p in got["players"]]
        got["squad_like"] = len(got["players"]) >= 14
        if len(got["players"]) > 11:  # extra names after the 11th are substitutes / reserves
            got["subs"] = got["players"][11:] + got["subs"]
            got["players"] = got["players"][:11]
        got["counts"] = {k: sum(1 for p in got["players"] if p["status"] == k) for k in ("squad", "data", "check", "new")}
    return {"sides": out, "both": both, "read_count": len(rows), "ignored": ignored[:12]}
