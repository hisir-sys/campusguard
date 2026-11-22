# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
"""Turns detector events into incidents and attaches the saved footage."""
from __future__ import annotations

import threading
from typing import Any

from campusguard.settings import CameraConfig


def severity_for(confidence: float) -> str:
    from campusguard.alert_policy import severity_for_score
    return severity_for_score(confidence * 100.0 if confidence <= 1.0 else confidence)


class IncidentRecorder:
    """Same rules as the desktop app: cooldown per camera, footage follows its incident."""

    def __init__(self, repository) -> None:
        self.repository = repository
        self._lock = threading.Lock()
        self._pending_footage: dict[str, str] = {}

    def record_event(
        self, camera: CameraConfig, event: str, confidence: float, cooldown_seconds: int,
        silent_mode: bool = False,
    ) -> dict[str, Any] | None:
        from campusguard.alert_policy import decide

        decision = decide(confidence, silent_mode=silent_mode,
                          relaxed_start=getattr(camera, "relaxed_start", ""), relaxed_end=getattr(camera, "relaxed_end", ""))
        incident = self.repository.create_incident(
            camera, event, confidence, decision.severity, cooldown_seconds, decision.suppressed
        )
        if incident is None:
            return None
        with self._lock:
            self._pending_footage[camera.camera_id] = str(incident["public_id"])
        return incident

    def update_assessment(self, camera_id: str, confidence: float, relaxed: bool = False) -> str | None:
        """Update the existing incident's peak confidence without creating a new row."""
        with self._lock:
            public_id = self._pending_footage.get(camera_id)
        if public_id is None:
            return None
        incident = self.repository.get_incident(public_id)
        if incident is None:
            return None
        previous = float(incident.get("confidence", 0.0))
        previous_score = previous * 100.0 if previous <= 1.0 else previous
        score = confidence * 100.0 if confidence <= 1.0 else confidence
        if score <= previous_score:
            return public_id
        self.repository.update_incident_assessment(
            public_id, confidence, "LOW" if relaxed else severity_for(confidence)
        )
        return public_id

    def attach_footage(self, camera_id: str, footage_path: str) -> str | None:
        with self._lock:
            public_id = self._pending_footage.pop(camera_id, None)
        if public_id is None:
            return None
        self.repository.attach_incident_footage(public_id, footage_path)
        return public_id
