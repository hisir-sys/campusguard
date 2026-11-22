# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
"""Per-camera tuning helpers: quiet hours and clip lead-in / follow-on lengths.

Everything here is pure (no Qt, no camera access) so it is easy to test.
"""
from __future__ import annotations

import re
from datetime import datetime, time as dtime

MIN_ROLL_SECONDS = 1.0
MAX_PRE_ROLL_SECONDS = 15.0
MAX_POST_ROLL_SECONDS = 30.0

_HHMM = re.compile(r"^\s*(\d{1,2})\s*[:.]\s*(\d{2})\s*$")


def parse_hhmm(value: object) -> dtime | None:
    """'22:30' / '7.05' -> time. Anything else (empty, 25:00, text) -> None."""
    match = _HHMM.match(str(value or ""))
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return dtime(hour, minute)


def normalise_hhmm(value: object) -> str:
    parsed = parse_hhmm(value)
    return "" if parsed is None else f"{parsed.hour:02d}:{parsed.minute:02d}"


def normalise_quiet_window(start: object, end: object) -> tuple[str, str]:
    """Both ends are needed for a quiet window; a half-filled window is dropped."""
    first, second = normalise_hhmm(start), normalise_hhmm(end)
    if not first or not second or first == second:
        return "", ""
    return first, second


def in_quiet_hours(start: object, end: object, now: datetime | dtime | None = None) -> bool:
    """True when `now` is inside [start, end). Windows may cross midnight (22:00 -> 06:00)."""
    begin, finish = parse_hhmm(start), parse_hhmm(end)
    if begin is None or finish is None or begin == finish:
        return False
    if now is None:
        now = datetime.now()
    current = now.time() if isinstance(now, datetime) else now
    current = current.replace(second=0, microsecond=0)
    if begin < finish:
        return begin <= current < finish
    return current >= begin or current < finish


def clamp_roll(value: object, default: float, maximum: float) -> float:
    """0 or empty means 'use the default'; otherwise a number of seconds inside a sane range."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return float(default)
    if seconds <= 0:
        return float(default)
    return max(MIN_ROLL_SECONDS, min(float(maximum), seconds))


def clamp_pre_roll(value: object, default: float = 5.0) -> float:
    return clamp_roll(value, default, MAX_PRE_ROLL_SECONDS)


def clamp_post_roll(value: object, default: float = 8.0) -> float:
    return clamp_roll(value, default, MAX_POST_ROLL_SECONDS)
