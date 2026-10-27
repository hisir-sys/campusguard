"""Turns detector events into incidents and attaches the saved footage."""
from __future__ import annotations

import threading
from typing import Any

from campusguard.settings import CameraConfig


def severity_for(confidence: float) -> str:
    score = confidence * 100.0 if confidence <= 1.0 else confidence
    return (
        "LOW" if score < 70.0
        else "MEDIUM" if score < 85.0
        else "HIGH" if score < 95.0
        else "CRITICAL"
    )


class IncidentRecorder:
    """Same rules as the desktop app: cooldown per camera, footage follows its incident."""

    def __init__(self, repository) -> None:
        self.repository = repository
        self._lock = threading.Lock()
        self._pending_footage: dict[str, str] = {}

    def record_event(
        self, camera: CameraConfig, event: str, confidence: float, cooldown_seconds: int
    ) -> dict[str, Any] | None:
        incident = self.repository.create_incident(
            camera, event, confidence, severity_for(confidence), cooldown_seconds
        )
        if incident is None:
            return None
        with self._lock:
            self._pending_footage[camera.camera_id] = str(incident["public_id"])
        return incident

    def update_assessment(self, camera_id: str, confidence: float) -> str | None:
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
            public_id, confidence, severity_for(confidence)
        )
        return public_id

    def attach_footage(self, camera_id: str, footage_path: str) -> str | None:
        with self._lock:
            public_id = self._pending_footage.pop(camera_id, None)
        if public_id is None:
            return None
        self.repository.attach_incident_footage(public_id, footage_path)
        return public_id
