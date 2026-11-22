# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
"""How loudly an incident is announced: silent test mode and per-camera relaxed hours.

Pure functions (no Qt, no network) so the rules are easy to test.

* **Silent mode** (school-wide): the app detects and records everything but sends nothing -
  no pop-up, no sound, no phone alert, no phone push. Use it for the first week or two at a
  school to see how many false alarms there would have been before anyone is bothered.
* **Relaxed hours** (per camera): between two times (for example the gym during sports period)
  a detection is still recorded with its clip, but graded LOW and announced to nobody.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from campusguard.tuning import in_quiet_hours

NOT_SUPPRESSED = ""
SILENT = "silent"      # would have alerted, but silent mode is on
RELAXED = "relaxed"    # inside the camera's relaxed hours; would not have alerted anyway


def severity_for_score(score: float) -> str:
    """Same grading everywhere: LOW below 70, MEDIUM below 85, HIGH below 95, else CRITICAL."""
    return "LOW" if score < 70.0 else "MEDIUM" if score < 85.0 else "HIGH" if score < 95.0 else "CRITICAL"


@dataclass(frozen=True)
class AlertDecision:
    severity: str
    suppressed: str = NOT_SUPPRESSED

    @property
    def announce(self) -> bool:
        """True when staff should hear about it (pop-up, sound, phone alert)."""
        return not self.suppressed


def decide(
    confidence: float,
    *,
    silent_mode: bool = False,
    relaxed_start: str = "",
    relaxed_end: str = "",
    now: datetime | None = None,
) -> AlertDecision:
    score = confidence * 100.0 if confidence <= 1.0 else confidence
    severity = severity_for_score(score)
    if in_quiet_hours(relaxed_start, relaxed_end, now):
        return AlertDecision("LOW", RELAXED)
    if silent_mode:
        return AlertDecision(severity, SILENT)
    return AlertDecision(severity, NOT_SUPPRESSED)
