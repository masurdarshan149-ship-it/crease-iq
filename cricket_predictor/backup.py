"""A copy of your personal files in OneDrive, made when the app starts (in the background, a second or so).

Everything else on this PC can be downloaded or rebuilt (match files, models), but these can't: your saved
predictions (Crease IQ and the Big Bash app, D:\\bbl, when it's there), squads you added or saved, model checks you
fetched, logged dropped catches and your settings. The daily history backups in data/history_backups are on the same
drive as the app, so a failed drive would take them too; OneDrive keeps a copy off this PC.

  OneDrive\\Crease IQ backup\\2026-11-26\\crease-iq\\prediction_history.json ...
                                   \\big-bash\\bbl\\prediction_history.json ...

One folder per day (today's is refreshed at each start); folders older than KEEP_DAYS are removed (only this backup's
own dated folders). Key files are never copied. Test copies (their own history file) and the online copy make no copy.
To restore: close the app, copy a file back to where the folder layout shows, start the app.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BBL_ROOT = Path(os.environ.get("CREASE_BBL_DIR") or r"D:\bbl")
FOLDER_NAME = "Crease IQ backup"
KEEP_DAYS = 30
STATUS_PATH = ROOT / "data" / "backup_status.json"
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
README = """Crease IQ backup

A copy of your personal files, made each day the app starts (the last 30 days are kept):

  crease-iq\\prediction_history.json    your saved predictions          -> D:\\codex\\prediction_history.json
  crease-iq\\data\\...                  squads you added, model checks  -> D:\\codex\\data\\
  big-bash\\bbl\\..., big-bash\\wbbl\\... the Big Bash app's files         -> D:\\bbl\\data\\bbl\\ and D:\\bbl\\data\\wbbl\\

To restore: close the app, copy the file back to the place shown on the right, then start the app.
Your CricketData keys are never copied here; keep them only in the apps' key files.
"""


def onedrive() -> Path | None:
    """The OneDrive folder Windows set up (None when there isn't one)."""
    for var in ("OneDrive", "OneDriveConsumer"):
        p = os.environ.get(var)
        if p and Path(p).is_dir():
            return Path(p)
    p = Path.home() / "OneDrive"
    return p if p.is_dir() else None


def personal_files() -> list[tuple[Path, str]]:
    """(the file, where it goes in the backup) for every personal file that exists."""
    main = [(ROOT / "prediction_history.json", "crease-iq/prediction_history.json")]
    for name in ("squad_additions.json", "archive_checks.json", "drops_log.json", "settings.json"):
        main.append((ROOT / "data" / name, f"crease-iq/data/{name}"))
    bbl = []
    for league in ("bbl", "wbbl"):
        for name in ("prediction_history.json", "squad_overrides.json", "archive_checks.json", "drops_log.json", "settings.json"):
            bbl.append((BBL_ROOT / "data" / league / name, f"big-bash/{league}/{name}"))
    return [(src, dest) for src, dest in main + bbl if src.is_file() and "key" not in src.name.lower()]


def run(today: date | None = None, target: Path | None = None) -> dict[str, Any]:
    """Copy the files into today's folder and drop folders older than KEEP_DAYS. Never raises."""
    today = today or date.today()
    base = target or onedrive()
    if base is None:
        return _status({"ok": False, "note": "No OneDrive folder on this PC, so no copy was made."})
    folder = base / FOLDER_NAME
    day_dir = folder / today.isoformat()
    copied, failed = [], []
    for src, dest in personal_files():
        try:
            out = day_dir / dest
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out)
            copied.append(dest)
        except OSError as exc:
            failed.append(f"{dest}: {exc}")
    readme = folder / "READ ME.txt"
    if copied and not readme.exists():
        try:
            readme.write_text(README, encoding="utf-8")
        except OSError:
            pass
    removed = 0
    cutoff = today - timedelta(days=KEEP_DAYS)
    for d in folder.iterdir() if folder.is_dir() else []:
        if d.is_dir() and _DAY.match(d.name) and date.fromisoformat(d.name) < cutoff:
            shutil.rmtree(d, ignore_errors=True)  # only this backup's own dated folders
            removed += 1
    note = f"{len(copied)} files copied to the OneDrive folder \"{FOLDER_NAME}\" (one folder per day)"
    if failed:
        note += f"; {len(failed)} couldn't be copied"
    return _status({"ok": not failed and bool(copied), "note": note, "folder": str(day_dir), "files": copied,
                    "failed": failed, "removed_old": removed})


def _status(out: dict[str, Any]) -> dict[str, Any]:
    out["at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATUS_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    except OSError:
        pass
    return out


def last() -> dict[str, Any]:
    """The last copy's result, for the Data page."""
    try:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def start_background() -> None:
    """Make today's copy without holding up the app (desktop copy only; never for test copies or the online app)."""
    if os.environ.get("CREASE_PUBLIC") == "1" or os.environ.get("CRICKET_HISTORY_PATH") or os.environ.get("CREASE_NO_BACKUP") == "1":
        return

    def work() -> None:
        try:
            run()
        except Exception:  # noqa: BLE001 - a backup must never stop the app
            pass

    threading.Thread(target=work, daemon=True, name="onedrive-backup").start()
