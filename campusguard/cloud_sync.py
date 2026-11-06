"""One-way sync of school summary + incident metadata to the CampusGuard website.

The website account that signs in to the app *is* the CampusGuard ID: pushed data is
stored under that account, so the website dashboard shows exactly what the app shows.

Privacy: only metadata leaves the school (counts, camera names, time, severity,
confidence, status and a "has footage" flag). Video, images and file paths are never sent.
A sync failure never affects detection, recording or alerts: every error is caught here.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from campusguard import auth_config

log = logging.getLogger("campusguard.cloud_sync")

PAGE_SIZE = 100
INTERVAL_SECONDS = 30.0
MAX_BACKOFF_SECONDS = 600.0
TIMEOUT_SECONDS = 15.0
_USER_AGENT = "CampusGuard-Sync/1.0"


def enabled() -> bool:
    return os.environ.get("CAMPUSGUARD_CLOUD_SYNC", "1").strip().lower() not in {"0", "false", "no", "off"}


def build_payload(repository, server_id: str, server_name: str, version: str,
                  live_counts: dict | None, events: list[dict]) -> dict[str, Any]:
    cameras = repository.list_cameras()
    counts = live_counts or {}
    return {
        "server": {
            "server_id": server_id, "server_name": server_name, "version": version,
            "cameras_total": len(cameras),
            "cameras_ai_enabled": sum(1 for camera in cameras if getattr(camera, "ai_enabled", True)),
            "cameras_online": counts.get("online"),
            "open_incidents": repository.open_incident_count(),
        },
        "incidents": [
            {
                "incident_id": event["incident_id"], "camera_name": event["camera_name"],
                "happened_at": event["happened_at"], "event": event["event"],
                "confidence": event["confidence"], "severity": event["severity"],
                "status": event["status"], "has_footage": bool(event["has_footage"]), "seq": event["seq"],
            }
            for event in events
        ],
    }


class CloudSync:
    def __init__(self, repository, server_id: str, server_name: str, version: str,
                 token_provider: Callable[[], str], state_path: Path,
                 live_counts: Callable[[], dict] | None = None,
                 post: Callable[[str, dict, str], int] | None = None,
                 interval: float = INTERVAL_SECONDS) -> None:
        self.repository = repository
        self.server_id = server_id
        self.server_name = server_name
        self.version = version
        self._token_provider = token_provider
        self._live_counts = live_counts
        self._post = post or self._http_post
        self._state_path = state_path
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._failures = 0
        self.last_ok: float | None = None
        self.last_error = ""
        self._cursor = self._load_cursor()

    # -- state -------------------------------------------------------------
    def _load_cursor(self) -> int:
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            if data.get("server_id") == self.server_id:
                return max(0, int(data.get("cursor", 0)))
        except (OSError, ValueError, TypeError):
            pass
        return 0

    def _save_cursor(self) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(json.dumps({"server_id": self.server_id, "cursor": self._cursor}), encoding="utf-8")
        except OSError:
            pass

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self._thread is None and enabled():
            self._thread = threading.Thread(target=self._loop, name="cloud-sync", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.sync_once()
                delay = self.interval
            except Exception as error:       # never let sync touch anything else
                self._failures += 1
                self.last_error = str(error)[:200]
                (log.debug if self.last_error == "not signed in" else log.warning)("cloud sync failed: %s", self.last_error)
                delay = min(MAX_BACKOFF_SECONDS, self.interval * (2 ** min(self._failures, 5)))
            self._stop.wait(delay)

    # -- one pass ----------------------------------------------------------
    def sync_once(self) -> bool:
        """Push everything new. Returns True when the website accepted it."""
        token = self._token_provider()
        if not token:
            raise RuntimeError("not signed in")
        while True:
            events, _latest = self.repository.list_sync_events(self._cursor, PAGE_SIZE)
            counts = None
            if self._live_counts is not None:
                try:
                    counts = self._live_counts()
                except Exception:
                    counts = None
            payload = build_payload(self.repository, self.server_id, self.server_name, self.version, counts, events)
            status = self._post(f"{auth_config.WEBSITE_URL}/api/sync-push", payload, token)
            if status != 200:
                raise RuntimeError(f"website returned HTTP {status}")
            if events:
                self._cursor = max(int(event["seq"]) for event in events)
                self._save_cursor()
            if len(events) < PAGE_SIZE:
                break
        import time
        self.last_ok = time.time()
        self.last_error = ""
        self._failures = 0
        return True

    @staticmethod
    def _http_post(url: str, payload: dict, token: str) -> int:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=body, method="POST", headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                response.read(4096)
                return response.status
        except urllib.error.HTTPError as error:
            error.close()
            return error.code
