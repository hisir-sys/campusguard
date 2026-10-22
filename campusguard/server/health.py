"""Thread-safe per-camera health, fed by the camera manager's signals."""
from __future__ import annotations

import threading
import time
from typing import Callable


class HealthTracker:
    STALE_AFTER_SECONDS = 15.0

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._cameras: dict[str, dict] = {}

    def _entry(self, camera_id: str) -> dict:
        return self._cameras.setdefault(
            camera_id,
            {"status": "CONNECTING", "message": "", "fps": None, "resolution": "N/A",
             "live_since": None, "last_frame": None, "ai": ""},
        )

    def set_status(self, camera_id: str, status: str, message: str = "") -> None:
        with self._lock:
            entry = self._entry(camera_id)
            if status == "LIVE" and entry["status"] != "LIVE":
                entry["live_since"] = self._clock()
                entry["last_frame"] = None
            if status != "LIVE":
                entry["live_since"] = None
            entry["status"], entry["message"] = status, message

    def set_stats(self, camera_id: str, fps: float, resolution: str) -> None:
        with self._lock:
            entry = self._entry(camera_id)
            entry["fps"], entry["resolution"] = round(float(fps), 1), resolution
            entry["last_frame"] = self._clock()

    def set_model_status(self, camera_id: str, component: str, message: str) -> None:
        if component in {"engine", "fight"}:
            with self._lock:
                self._entry(camera_id)["ai"] = f"{component}: {message}"

    def remove(self, camera_id: str) -> None:
        with self._lock:
            self._cameras.pop(camera_id, None)

    def _health(self, entry: dict, now: float) -> tuple[str, float | None]:
        age = None if entry["last_frame"] is None else now - entry["last_frame"]
        status = entry["status"]
        if status == "LIVE":
            reference = entry["last_frame"] if entry["last_frame"] is not None else entry["live_since"]
            stalled = reference is None or now - reference > self.STALE_AFTER_SECONDS
            return ("stalled" if stalled else "ok"), age
        if status == "CONNECTING":
            return "connecting", age
        return "offline", age

    def snapshot(self) -> dict[str, dict]:
        now = self._clock()
        with self._lock:
            result = {}
            for camera_id, entry in self._cameras.items():
                health, age = self._health(entry, now)
                result[camera_id] = {
                    "status": entry["status"],
                    "health": health,
                    "message": entry["message"],
                    "fps": entry["fps"],
                    "resolution": entry["resolution"],
                    "seconds_since_frame": None if age is None else round(age, 1),
                    "ai": entry["ai"],
                }
            return result

    def summary(self) -> dict[str, int]:
        counts = {"ok": 0, "stalled": 0, "offline": 0, "connecting": 0}
        for entry in self.snapshot().values():
            counts[entry["health"]] += 1
        counts["total"] = sum(counts.values())
        return counts
