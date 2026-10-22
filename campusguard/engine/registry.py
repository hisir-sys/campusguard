"""Process-wide count of running camera analysers (drives automatic profile choice)."""
from __future__ import annotations

import threading


class ActiveCameras:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._count = 0

    def enter(self) -> None:
        with self._lock:
            self._count += 1

    def leave(self) -> None:
        with self._lock:
            self._count = max(0, self._count - 1)

    @property
    def count(self) -> int:
        with self._lock:
            return self._count


ACTIVE_CAMERAS = ActiveCameras()
