# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
"""Bulk camera import from CSV (name,type,address,username,password,ai_enabled)."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from campusguard.settings import CameraCredentials
from campusguard.sources import build_capture_source
from campusguard.tuning import normalise_quiet_window

MAX_ROWS = 1000
SOURCE_TYPES = {"USB", "RTSP", "HTTP", "MJPEG", "IP"}
_ALIASES = {
    "name": "name", "camera": "name", "camera_name": "name", "label": "name",
    "type": "type", "source_type": "type",
    "address": "address", "url": "address", "source": "address", "source_address": "address",
    "username": "username", "user": "username",
    "password": "password", "pass": "password",
    "ai": "ai_enabled", "ai_enabled": "ai_enabled",
    "group": "group_name", "zone": "group_name", "building": "group_name", "group_name": "group_name",
    "sensitivity": "sensitivity",
    "quiet_start": "quiet_start", "quiet_from": "quiet_start",
    "quiet_end": "quiet_end", "quiet_to": "quiet_end",
    "pre_roll": "pre_roll", "pre_roll_seconds": "pre_roll",
    "post_roll": "post_roll", "post_roll_seconds": "post_roll",
}
SENSITIVITY_WORDS = {"sensitive": -0.10, "default": 0.0, "normal": 0.0, "cautious": 0.10, "strict": 0.20}


@dataclass(frozen=True)
class NewCamera:
    name: str
    source_type: str
    address: str
    credentials: CameraCredentials
    ai_enabled: bool
    group_name: str = ""
    threshold_offset: float = 0.0
    quiet_start: str = ""
    quiet_end: str = ""
    pre_roll_seconds: float = 0.0
    post_roll_seconds: float = 0.0


def _sensitivity(text: str) -> float:
    text = text.strip().lower()
    if not text:
        return 0.0
    if text in SENSITIVITY_WORDS:
        return SENSITIVITY_WORDS[text]
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"Unknown sensitivity '{text}' (use sensitive, default, cautious, strict or a number).")
    return max(-0.25, min(0.25, value))


def _roll(text: str, maximum: float, label: str) -> float:
    text = text.strip()
    if not text:
        return 0.0
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"{label} must be a number of seconds.")
    return max(0.0, min(maximum, value))


@dataclass
class ImportPlan:
    valid: list[NewCamera] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


def _truthy(value: str, default: bool = True) -> bool:
    value = value.strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "y", "on"}


def parse_cameras_csv(text: str, existing: set[tuple[str, str]] | None = None) -> ImportPlan:
    """existing: {(TYPE, address.lower())} already configured, for duplicate detection."""
    plan = ImportPlan()
    text = text.lstrip("﻿")
    seen = set(existing or ())
    try:
        sample = text[:2048]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample.strip() else csv.excel
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        plan.errors.append({"row": 1, "error": "The file is empty."})
        return plan
    header = [_ALIASES.get(cell.strip().lower().replace(" ", "_"), "") for cell in rows[0]]
    if "name" not in header or "address" not in header:
        plan.errors.append({"row": 1, "error": "The header row must contain at least: name, address."})
        return plan
    if len(rows) - 1 > MAX_ROWS:
        plan.errors.append({"row": 1, "error": f"Too many rows (maximum {MAX_ROWS} per import)."})
        return plan
    for offset, row in enumerate(rows[1:], start=2):
        values = {key: "" for key in set(_ALIASES.values())}
        for key, cell in zip(header, row):
            if key:
                values[key] = cell.strip()
        name = values["name"]
        source_type = (values["type"] or "RTSP").upper()
        address = values["address"]
        try:
            if not name:
                raise ValueError("Camera name is missing.")
            if len(name) > 80:
                raise ValueError("Camera name is longer than 80 characters.")
            if source_type not in SOURCE_TYPES:
                raise ValueError(f"Unknown type '{source_type}' (use RTSP, HTTP, MJPEG, IP or USB).")
            credentials = CameraCredentials(values["username"], values["password"])
            build_capture_source(source_type, address, credentials)
            key = (source_type, address.lower())
            if key in seen:
                raise ValueError("This camera address is already configured.")
            offset_value = _sensitivity(values["sensitivity"])
            pre = _roll(values["pre_roll"], 15.0, "pre_roll")
            post = _roll(values["post_roll"], 30.0, "post_roll")
            quiet_start, quiet_end = normalise_quiet_window(values["quiet_start"], values["quiet_end"])
            if (values["quiet_start"] or values["quiet_end"]) and not quiet_start:
                raise ValueError("Quiet hours need both quiet_start and quiet_end as HH:MM (for example 22:00 and 06:00).")
            seen.add(key)
        except ValueError as error:
            plan.errors.append({"row": offset, "error": str(error)})
            continue
        plan.valid.append(
            NewCamera(
                name, source_type, address, credentials, _truthy(values["ai_enabled"]),
                " ".join(values["group_name"].split())[:40], offset_value,
                quiet_start, quiet_end, pre, post,
            )
        )
    return plan
