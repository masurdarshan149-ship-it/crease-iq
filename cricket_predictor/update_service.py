from __future__ import annotations

import json
import ssl
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "data" / "player_insights_cache.json"
BUILD_SCRIPT = ROOT / "scripts" / "build_cricsheet_cache.py"
AUTO_UPDATE_INTERVAL = 24 * 3600  # seconds
STARTUP_UPDATE_DELAY = 5 * 60  # seconds after launch before a catch-up update may start

# Format-specific archives — much smaller than the monolithic all_json.zip (~400 MB)
CRICSHEET_ARCHIVES = [
    ("ipl",  "https://cricsheet.org/downloads/ipl_json.zip",  ROOT / "data" / "cricsheet_ipl.zip",  "IPL"),
    ("t20s", "https://cricsheet.org/downloads/t20s_json.zip", ROOT / "data" / "cricsheet_t20s.zip", "T20 Internationals"),
    ("odis", "https://cricsheet.org/downloads/odis_json.zip", ROOT / "data" / "cricsheet_odis.zip", "ODIs"),
]
ARCHIVE_PATHS = [entry[2] for entry in CRICSHEET_ARCHIVES]


def _ssl_context() -> ssl.SSLContext:
    try:
        return ssl.create_default_context()
    except Exception:
        return ssl._create_unverified_context()  # noqa: SLF001 — fallback for restricted envs


def _format_megabytes(value: int | float) -> str:
    return f"{value / (1024 * 1024):.1f} MB"


def _format_eta(seconds: float | int | None) -> str:
    if seconds is None:
        return "Calculating ETA"
    seconds = max(0, int(seconds))
    minutes, remainder = divmod(seconds, 60)
    if minutes:
        return f"About {minutes}m {remainder:02d}s left"
    return f"About {remainder}s left"


def _log(message: str) -> None:
    print(f"[update-service] {message}", flush=True)


@dataclass
class UpdateState:
    state: str = "idle"
    percent: int = 0
    stage: str = "Preparing"
    downloaded: int = 0
    total: int = 0
    eta_seconds: float | None = None
    message: str = ""
    started_at: float | None = None
    last_update_at: float | None = None
    processed_items: int = 0
    total_items: int = 0
    error: str = ""
    success: bool | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class DataUpdateService:
    def __init__(self) -> None:
        self._state = UpdateState()
        self._worker: threading.Thread | None = None
        self._auto_update_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Internal state helpers
    # ------------------------------------------------------------------

    def _set_state(self, **changes: Any) -> None:
        with self._state.lock:
            for key, value in changes.items():
                setattr(self._state, key, value)
            self._state.last_update_at = time.time()
            if self._state.started_at is None:
                self._state.started_at = self._state.last_update_at

    def _set_failure(self, error_message: str) -> None:
        cleaned = error_message.strip() or "Unknown update error"
        _log(f"ERROR {cleaned}")
        current_percent = max(1, min(99, int(self._state.percent or 0)))
        self._set_state(
            state="error",
            success=False,
            stage="Failed",
            percent=current_percent,
            eta_seconds=None,
            message="Update failed — check server logs",
            error=cleaned,
        )

    def _set_success(self) -> None:
        total = sum(p.stat().st_size for p in ARCHIVE_PATHS if p.exists()) or self._state.downloaded
        self._set_state(
            state="success",
            success=True,
            stage="Completed",
            percent=100,
            downloaded=total,
            total=total,
            eta_seconds=0,
            message="Update Completed ✅",
            error="",
        )

    def _cache_is_fresh(self) -> bool:
        """True when cache exists and is newer than every downloaded archive."""
        if not CACHE_PATH.exists() or CACHE_PATH.stat().st_size == 0:
            return False
        cache_mtime = CACHE_PATH.stat().st_mtime
        for path in ARCHIVE_PATHS:
            if not path.exists():
                return False
            if cache_mtime < path.stat().st_mtime:
                return False
        return True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._state.lock:
            return {
                "percent": int(self._state.percent),
                "stage": self._state.stage,
                "downloaded": int(self._state.downloaded),
                "total": int(self._state.total),
                "downloadedSize": _format_megabytes(self._state.downloaded),
                "totalSize": _format_megabytes(self._state.total) if self._state.total else "Pending",
                "eta": "Completed" if self._state.success else _format_eta(self._state.eta_seconds),
                "eta_seconds": self._state.eta_seconds,
                "state": self._state.state,
                "success": self._state.success,
                "message": self._state.message,
                "meta": self._state.error if self._state.state == "error" else self._state.message,
                "processedItems": self._state.processed_items,
                "totalItems": self._state.total_items,
                "error": self._state.error,
            }

    def start_update(self) -> dict[str, Any]:
        with self._state.lock:
            if self._state.state == "running":
                return self.snapshot()
            now = time.time()
            self._state = UpdateState(
                state="running",
                percent=1,
                stage="Preparing",
                downloaded=0,
                total=0,
                eta_seconds=None,
                message="Preparing download",
                started_at=now,
                last_update_at=now,
                success=None,
            )
        self._worker = threading.Thread(target=self._run_update, daemon=True, name="update-worker")
        self._worker.start()
        return self.snapshot()

    def start_auto_updates(self, interval: int = AUTO_UPDATE_INTERVAL) -> None:
        """Start a background thread that triggers an update every `interval` seconds."""
        if self._auto_update_thread and self._auto_update_thread.is_alive():
            return

        def _loop() -> None:
            # Wait a few minutes after launch before a catch-up update, so it doesn't compete with the first page
            # loads and predictions (start-up stays fast); then trigger if the cache is absent or very stale
            time.sleep(STARTUP_UPDATE_DELAY)
            cache_age = time.time() - CACHE_PATH.stat().st_mtime if CACHE_PATH.exists() else float("inf")
            if cache_age > interval:
                _log("Cache is stale — triggering initial auto-update")
                self.start_update()
                # Wait for it to finish before sleeping
                while self._state.state == "running":
                    time.sleep(5)

            while True:
                time.sleep(interval)
                if self._state.state != "running":
                    _log("Auto-update triggered (24-hour schedule)")
                    self.start_update()

        self._auto_update_thread = threading.Thread(target=_loop, daemon=True, name="auto-update-scheduler")
        self._auto_update_thread.start()
        _log("Auto-update scheduler started (every 24 hours)")

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _head_request(self, url: str) -> tuple[int | None, float | None]:
        req = Request(url, headers={"User-Agent": "Cricket-Win-Predictor/1.0"}, method="HEAD")
        with urlopen(req, timeout=20, context=_ssl_context()) as resp:
            size = resp.headers.get("Content-Length")
            modified = resp.headers.get("Last-Modified")
        return (
            int(size) if size and size.isdigit() else None,
            parsedate_to_datetime(modified).timestamp() if modified else None,
        )

    def _download_archives(self) -> None:
        """Download IPL + T20I + ODI archives from Cricsheet with combined progress 1→70%."""
        DOWNLOAD_PERCENT_END = 70

        # Probe all archives first to know expected total size
        probes: list[tuple[int | None, float | None]] = []
        for _key, url, _path, label in CRICSHEET_ARCHIVES:
            try:
                size, modified = self._head_request(url)
                probes.append((size, modified))
                _log(f"Probe {label}: {_format_megabytes(size) if size else 'unknown size'}")
            except Exception as exc:
                _log(f"Probe failed for {label}: {exc}")
                probes.append((None, None))

        # Decide which archives need downloading
        need_download: list[bool] = []
        for (key, url, path, label), (remote_size, remote_modified) in zip(CRICSHEET_ARCHIVES, probes):
            local_size = path.stat().st_size if path.exists() else 0
            up_to_date = (
                path.exists()
                and remote_size is not None
                and local_size == remote_size
                and (remote_modified is None or abs(path.stat().st_mtime - remote_modified) <= 60)
            )
            need_download.append(not up_to_date)
            if up_to_date:
                _log(f"{label} archive already up to date ({_format_megabytes(local_size)})")

        # Calculate total bytes we expect to download (for combined progress bar)
        expected_total = 0
        for (_, _, path, _), (remote_size, _), will_download in zip(CRICSHEET_ARCHIVES, probes, need_download):
            if will_download:
                expected_total += remote_size or 60 * 1024 * 1024  # guess 60 MB if unknown
            else:
                expected_total += path.stat().st_size if path.exists() else 0

        self._set_state(
            stage="Downloading",
            percent=2,
            downloaded=0,
            total=expected_total,
            message="Starting archive downloads...",
        )

        cumulative_done = sum(
            path.stat().st_size if path.exists() else 0
            for (_, _, path, _), will_dl in zip(CRICSHEET_ARCHIVES, need_download)
            if not will_dl
        )

        for (key, url, path, label), will_download in zip(CRICSHEET_ARCHIVES, need_download):
            if not will_download:
                continue

            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = path.with_suffix(".zip.tmp")
            req = Request(url, headers={"User-Agent": "Cricket-Win-Predictor/1.0"})
            dl_start = time.time()
            file_dl = 0

            _log(f"Downloading {label} from {url} ...")
            self._set_state(message=f"Downloading {label} archive...")

            try:
                with urlopen(req, timeout=300, context=_ssl_context()) as resp, temp_path.open("wb") as fh:
                    file_total = int(resp.headers.get("Content-Length", "0") or 0)
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        fh.write(chunk)
                        file_dl += len(chunk)
                        total_done = cumulative_done + file_dl
                        percent = max(2, min(DOWNLOAD_PERCENT_END - 1, int(total_done / expected_total * DOWNLOAD_PERCENT_END))) if expected_total else 35
                        elapsed = max(time.time() - dl_start, 0.001)
                        eta = ((file_total - file_dl) / (file_dl / elapsed)) if file_dl and file_total else None
                        self._set_state(
                            stage="Downloading",
                            percent=percent,
                            downloaded=total_done,
                            total=expected_total,
                            eta_seconds=eta,
                            message=f"Downloading {label} — {_format_megabytes(file_dl)} / {_format_megabytes(file_total) if file_total else '?'}",
                        )
            except Exception:
                if temp_path.exists():
                    temp_path.unlink(missing_ok=True)
                raise

            temp_path.replace(path)
            if not path.exists() or path.stat().st_size == 0:
                raise FileNotFoundError(f"{label} archive download failed: file missing or empty")

            cumulative_done += path.stat().st_size
            _log(f"{label} downloaded: {_format_megabytes(path.stat().st_size)}")

        total_archive_size = sum(p.stat().st_size for p in ARCHIVE_PATHS if p.exists())
        self._set_state(
            stage="Processing",
            percent=DOWNLOAD_PERCENT_END,
            downloaded=total_archive_size,
            total=total_archive_size,
            eta_seconds=15,
            message="Archives ready. Building player cache...",
        )

    # ------------------------------------------------------------------
    # Cache build
    # ------------------------------------------------------------------

    def _process_archives(self) -> None:
        missing = [p for p in ARCHIVE_PATHS if not p.exists()]
        if missing:
            raise FileNotFoundError(f"Missing archives: {[str(p) for p in missing]}")

        total_size = sum(p.stat().st_size for p in ARCHIVE_PATHS)
        self._set_state(
            stage="Processing",
            percent=72,
            downloaded=total_size,
            total=total_size,
            eta_seconds=30,
            message="Launching cache build process...",
        )
        _log("Starting cache build...")

        process = subprocess.Popen(
            [sys.executable, str(BUILD_SCRIPT)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        build_started = time.time()
        stdout_lines: list[str] = []
        assert process.stdout is not None

        for raw_line in process.stdout:
            text = raw_line.strip()
            if not text:
                continue
            stdout_lines.append(text)
            _log(text)

            if text.startswith("LOG "):
                msg = text[4:]
                low = msg.lower()
                stage = "Processing"
                floor = 72
                if "saving" in low or "writing" in low:
                    stage, floor = "Finalizing", 95
                elif "building" in low:
                    floor = 82
                elif "parsing" in low:
                    floor = 76
                self._set_state(
                    stage=stage,
                    percent=max(self._state.percent, floor),
                    downloaded=total_size,
                    total=total_size,
                    eta_seconds=3 if stage == "Finalizing" else 20,
                    message=msg,
                )
                continue

            if text.startswith("WARNING "):
                continue

            if text.startswith("BUILD_PROGRESS "):
                parts = text.split()
                if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                    processed, total = int(parts[1]), int(parts[2])
                    ratio = processed / total if total else 0.0
                    percent = 72 + int(ratio * 23)
                    elapsed = max(time.time() - build_started, 0.001)
                    eta = ((total - processed) / (processed / elapsed)) if processed else None
                    stage = "Finalizing" if percent >= 95 else "Processing"
                    self._set_state(
                        stage=stage,
                        percent=min(percent, 99),
                        downloaded=total_size,
                        total=total_size,
                        eta_seconds=eta,
                        processed_items=processed,
                        total_items=total,
                        message="Finalizing player stats." if stage == "Finalizing" else "Building player stats from match data.",
                    )
                continue

            if text.startswith("ERROR "):
                raise RuntimeError(text[6:])

            if text.startswith("Wrote "):
                self._set_state(stage="Finalizing", percent=99, eta_seconds=1, message="Saving player stats cache.")

        stderr_output = process.stderr.read() if process.stderr else ""
        return_code = process.wait(timeout=3600)
        if return_code != 0:
            details = stderr_output.strip() or "\n".join(stdout_lines).strip() or "Unknown cache build error."
            raise RuntimeError(details.splitlines()[-1])
        if not CACHE_PATH.exists() or CACHE_PATH.stat().st_size == 0:
            raise FileNotFoundError(f"Cache build finished but output missing: {CACHE_PATH}")

    # ------------------------------------------------------------------
    # Main update flow
    # ------------------------------------------------------------------

    def _run_update(self) -> None:
        try:
            _log("Starting update run")
            self._download_archives()
            if self._cache_is_fresh():
                _log("Cache is fresh — skipping rebuild")
                total = sum(p.stat().st_size for p in ARCHIVE_PATHS if p.exists())
                self._set_state(stage="Finalizing", percent=99, downloaded=total, total=total, eta_seconds=0, message="Cache already up to date.")
            else:
                self._process_archives()
            self._set_success()
            _log("Update completed successfully")
            try:  # read the new match totals now, so History doesn't wait for them later
                from . import tracking
                tracking.warm_totals()
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:
            _log(traceback.format_exc())
            self._set_failure(str(exc))

    # ------------------------------------------------------------------
    # Player stats read-back
    # ------------------------------------------------------------------

    def get_player_stats(self) -> dict[str, Any]:
        if not CACHE_PATH.exists():
            return {"players": []}
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        players: list[dict[str, Any]] = []
        for name, payload in cache.get("players", {}).items():
            career = payload.get("career", {})
            players.append({
                "name": name,
                "runs": int(career.get("runs", 0) or 0),
                "wickets": int(career.get("wickets", 0) or 0),
                "matches": int(career.get("matches", 0) or 0),
            })
        players.sort(key=lambda item: (item["runs"], item["wickets"], item["matches"]), reverse=True)
        return {"players": players[:12]}


UPDATE_SERVICE = DataUpdateService()
