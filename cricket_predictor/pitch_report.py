"""Pitch reports: read the text (typed, pasted or from a picture), pick the pitch and dew buttons it points to, and
later check those calls against what the first innings actually scored.

The reader is a simple word list, not a trained model: there is no free archive of past pitch reports to learn from.
Every call shows the words it went by, and you can always change the buttons. The History check (`checks`) builds the
record that tells us, over time, whether the pitch adjustments are about right.
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# (phrase, weight). Longer phrases are matched first, and a word inside a phrase that matched is not counted again.
CUES: dict[str, list[tuple[str, float]]] = {
    "flat": [
        ("batting paradise", 2), ("good for batting", 2), ("great for batting", 2), ("batting friendly", 2),
        ("batting-friendly", 2), ("belter", 2), ("road", 1.5), ("shirtfront", 2), ("flat", 2), ("hard and true", 2),
        ("true bounce", 1.5), ("true surface", 1.5), ("high scoring", 2), ("high-scoring", 2), ("plenty of runs", 2),
        ("lots of runs", 2), ("a lot of runs", 2), ("runs on offer", 2), ("comes on to the bat", 1.5),
        ("comes onto the bat", 1.5), ("nicely on to the bat", 1.5), ("value for shots", 1.5), ("hard surface", 1),
        ("even bounce", 1), ("good batting", 1.5), ("batting track", 1.5), ("batting surface", 1.5),
    ],
    "green": [
        ("green", 2), ("grassy", 2), ("grass", 1.5), ("tinge", 1.5), ("tinge of grass", 2), ("bit of grass", 1.5),
        ("lot of grass", 2.5), ("covering of grass", 2), ("grass covering", 2), ("live grass", 2), ("seam", 1.5), ("seamers", 1.5),
        ("seam movement", 2), ("swing", 1), ("moisture", 1.5), ("moist", 1.5), ("damp", 1.5), ("juice", 1.5),
        ("help for the quicks", 2), ("help for the pacers", 2), ("help for the fast bowlers", 2), ("pace and bounce", 1.5),
        ("lateral movement", 2), ("nibble", 1), ("overcast", 1), ("bouncy", 1), ("extra bounce", 1),
    ],
    "dry": [
        ("dry", 1.5), ("cracks", 2), ("crack", 1.5), ("rank turner", 2.5), ("turner", 2), ("turning", 2), ("turn", 1.5),
        ("spin", 1.5), ("spinners", 1.5), ("spin friendly", 2), ("spin-friendly", 2), ("dusty", 2), ("rough", 1),
        ("bare", 1), ("abrasive", 1), ("grip", 1), ("help for the spinners", 2),
    ],
    "slow": [
        ("slow", 1.5), ("sluggish", 2), ("two paced", 2), ("two-paced", 2), ("low bounce", 2), ("keeps low", 2),
        ("staying low", 2), ("variable bounce", 1.5), ("holding up", 1.5), ("stopping", 1.5), ("sticky", 1.5),
        ("tacky", 1.5), ("cutters", 1), ("slower balls", 1), ("slower ones", 1), ("tough to bat", 1.5),
        ("hard to score", 1.5), ("low scoring", 2), ("low-scoring", 2), ("not easy to bat", 1.5),
    ],
}
BOWLING_GENERAL = ["bowler friendly", "bowler-friendly", "good for bowling", "bowlers will enjoy", "help for the bowlers",
                   "something for the bowlers", "bowling friendly", "bowling-friendly"]
DEW_CUES: dict[str, list[str]] = {
    "none": ["no dew", "not much dew", "little dew", "dew won't", "dew will not", "dew is not expected", "no sign of dew"],
    "heavy": ["heavy dew", "lot of dew", "lots of dew", "plenty of dew", "dew will play a big", "dew will be a big",
              "dew is a big", "big dew", "dew factor", "wet ball", "dew could be a factor", "dew will be a factor"],
    "light": ["some dew", "bit of dew", "light dew", "little bit of dew", "dew later", "dew expected", "dew could",
              "dew might", "dew may", "dew"],
    "slowing": ["slow down", "get slower", "slower as the game", "slower later", "deteriorate", "wear and tear",
                "tougher to bat second", "harder to bat second", "spin more later", "grip more later",
                "hold up more later", "difficult to chase"],
}
NEGATORS = {"no", "not", "hardly", "barely", "without", "isn't", "wont", "won't", "never", "nor", "lack", "minimal",
            "less"}  # "not much grass", "hardly any turn" ("much" / "any" alone don't negate)
LABELS = {"balanced": "Balanced", "flat": "Flat / batting", "green": "Green / grassy", "dry": "Dry / turning",
          "slow": "Slow / low"}
DEW_LABELS = {"none": "No effect", "light": "Light dew", "heavy": "Heavy dew", "slowing": "Pitch slows / no dew"}
MAX_TEXT = 6000


def _find(text: str, phrase: str, taken: list[tuple[int, int]]) -> list[tuple[int, int]]:
    hits = []
    for m in re.finditer(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", text):
        span = (m.start(), m.end())
        if not any(a < span[1] and span[0] < b for a, b in taken):
            hits.append(span)
    return hits


def _negated(text: str, start: int) -> bool:
    """'no grass', 'not much turn', 'hardly any swing', 'without much dew' (a negating word in the 3 words before)."""
    before = re.findall(r"[a-z']+", text[max(0, start - 30):start])[-3:]
    return any(w in NEGATORS for w in before)


def read(text: str) -> dict[str, Any]:
    """Pick the pitch (balanced / flat / green / dry / slow) and dew call a pitch report points to, with the words used."""
    raw = re.sub(r"\s+", " ", str(text or ""))[:MAX_TEXT].strip()
    low = raw.lower().replace("’", "'")
    scores = {k: 0.0 for k in CUES}
    words: list[dict[str, Any]] = []
    # "will slow down later" is about the second innings (dew box), so it doesn't make the pitch itself slow
    taken: list[tuple[int, int]] = [s for p in DEW_CUES["slowing"] for s in _find(low, p, [])]
    cues = sorted(((k, p, w) for k, lst in CUES.items() for p, w in lst), key=lambda c: -len(c[1]))
    for key, phrase, weight in cues:
        for span in _find(low, phrase, taken):
            taken.append(span)
            if _negated(low, span[0]):
                words.append({"text": raw[span[0]:span[1]], "means": key, "ignored": True})
                if key == "green":  # "no grass" / "not much grass" leans towards a good batting surface
                    scores["flat"] += 0.5
                continue
            scores[key] += weight
            words.append({"text": raw[span[0]:span[1]], "means": key, "at": span[0]})
    general = sum(len(_find(low, p, taken)) for p in BOWLING_GENERAL)
    if general:
        scores["flat"] -= 1.0 * general  # "good for the bowlers" without saying how: counts against a batting pitch
        words.append({"text": "good for bowlers", "means": "bowling", "at": -1})

    # dew (and "the pitch will slow down later"), most specific first
    dew, dew_words, dtaken = "none", [], []
    found: dict[str, int] = {}
    for key in ("none", "heavy", "slowing", "light"):
        for phrase in DEW_CUES[key]:
            for span in _find(low, phrase, dtaken):
                dtaken.append(span)
                if key == "light" and _negated(low, span[0]):
                    key_used = "none"
                else:
                    key_used = key
                found[key_used] = found.get(key_used, 0) + 1
                dew_words.append({"text": raw[span[0]:span[1]], "means": key_used})
    if found.get("heavy"):
        dew = "heavy"
    elif found.get("light") and not found.get("none"):
        dew = "light"
    elif found.get("slowing") and not found.get("light"):
        dew = "slowing"

    # "slowing" phrases mean a later change, so they don't also make the pitch itself slow
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    (top, best), (second, next_best) = ranked[0], ranked[1]
    if best < 1.5:
        pitch, why = "balanced", "Nothing clear about the pitch in this report." if raw else "No text to read."
    elif best - next_best < 1.0 and next_best >= 1.5 and {top, second} != {"dry", "slow"}:
        pitch, why = "balanced", f"Mixed signals: {LABELS[top].split(' /')[0].lower()} and {LABELS[second].split(' /')[0].lower()} both mentioned."
    else:
        pitch = top
        why = f"Mostly {LABELS[top].lower()} words."
        if next_best >= 1.5:
            why += f" Some {LABELS[second].split(' /')[0].lower()} words too."
    words.sort(key=lambda w: w.get("at", 10**6))
    for w in words:
        w.pop("at", None)
    return {
        "pitch": pitch, "pitch_label": LABELS[pitch], "dew": dew, "dew_label": DEW_LABELS[dew],
        "why": why, "words": words, "dew_words": dew_words,
        "scores": {k: round(v, 1) for k, v in scores.items()}, "text": raw,
    }


# ---- pictures: Windows' own text recognition (offline). Not available in the online copy.
OCR_SCRIPT = Path(__file__).with_name("ocr_windows.ps1")
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def image_text(data_url: str) -> str:
    """The text in a picture (a data: URL from the page), read by Windows. Raises ValueError with a plain message."""
    if os.name != "nt" or not OCR_SCRIPT.exists():
        raise ValueError("Reading pictures needs Windows' text recognition, which isn't available here. Paste the text instead.")
    head, _, body = str(data_url or "").partition(",")
    if not head.startswith("data:image/") or not body:
        raise ValueError("That doesn't look like a picture. Try a PNG or JPG.")
    ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/bmp": ".bmp", "image/gif": ".gif",
           "image/webp": None}.get(head[5:].split(";")[0], ".png")
    if ext is None:
        raise ValueError("Windows can't read WebP pictures. Save it as PNG or JPG, or take a screenshot.")
    try:
        blob = base64.b64decode(body, validate=False)
    except ValueError:
        raise ValueError("The picture couldn't be read.") from None
    if len(blob) > MAX_IMAGE_BYTES:
        raise ValueError("That picture is too big (over 8 MB). Crop it to the pitch report, or take a screenshot.")
    fd, path = tempfile.mkstemp(suffix=ext, prefix="crease_pitch_")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(blob)
        run = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(OCR_SCRIPT), path],
            capture_output=True, timeout=45, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise ValueError("Reading the picture took too long. Try a smaller or clearer picture.") from None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    text = run.stdout.decode("utf-8", "replace").strip()
    if run.returncode != 0 and not text:
        raise ValueError("Windows couldn't read that picture. Try a clearer one, or paste the text.")
    if not text:
        raise ValueError("No text found in that picture. Try a clearer one, or paste the text.")
    return text


def read_image(data_url: str) -> dict[str, Any]:
    out = read(image_text(data_url))
    out["from_picture"] = True
    return out


# ---- History: was the pitch call right? (first-innings total against the ground's usual par)
ABOUT_PAR = 5  # within 5 runs of the usual par counts as "about par", neither right nor wrong


def _verdict(pitch: str, diff: int) -> str:
    if abs(diff) <= ABOUT_PAR:
        return "par"
    batting = pitch == "flat"
    return "right" if (diff > 0) == batting else "wrong"


def checks(items: list[dict[str, Any]], base_par) -> dict[str, Any]:
    """For each match where you called the pitch (not Balanced) and the full first-innings total is known, compare the
    total with the ground's usual par. `base_par(entry)` gives that par (or None). Adds e["pitch_check"] to every save
    of the match and returns a summary by call."""
    from . import tracking

    groups: dict[str, list[dict[str, Any]]] = {}
    for e in items:
        if e.get("auto") or e.get("is_practice"):  # model checks and practice runs aren't your pitch calls on a real match
            continue
        groups.setdefault(e.get("match_key") or tracking.match_key(e), []).append(e)
    summary: dict[str, dict[str, int]] = {}
    rows = []
    for saves in groups.values():
        saves.sort(key=lambda e: str(e.get("timestamp", "")))
        latest = saves[-1]
        pitch = latest.get("pitch") or (latest.get("setup") or {}).get("pitch")
        if pitch not in LABELS or pitch == "balanced":
            continue
        totals = [int(e["first_innings_score"]) for e in saves
                  if e.get("first_innings_score") is not None and (e.get("type") == "chase" or e.get("stage") == "innings_break")]
        par = base_par(latest)
        if not totals or not par:
            check = {"pitch": pitch, "label": LABELS[pitch], "status": "waiting",
                     "detail": f"Called {LABELS[pitch].lower()}: checked once the first innings is finished and saved."}
        else:
            total, par = totals[-1], int(round(par))
            diff = total - par
            status = _verdict(pitch, diff)
            side = f"{abs(diff)} {'above' if diff > 0 else 'below'} the usual par of {par}" if diff else f"exactly the usual par of {par}"
            word = {"right": "right", "wrong": "wrong", "par": "about par (not counted)"}[status]
            check = {"pitch": pitch, "label": LABELS[pitch], "status": status, "total": total, "par": par, "diff": diff,
                     "detail": f"Called {LABELS[pitch].lower()}: first innings made {total}, {side}. Call {word}."}
            s = summary.setdefault(pitch, {"right": 0, "wrong": 0, "par": 0})
            s[status] += 1
            rows.append(check)
        for e in saves:
            e["pitch_check"] = check
    right = sum(s["right"] for s in summary.values())
    wrong = sum(s["wrong"] for s in summary.values())
    return {"by_call": {k: {**v, "label": LABELS[k]} for k, v in summary.items()}, "right": right, "wrong": wrong,
            "par": sum(s["par"] for s in summary.values()), "checked": len(rows)}
