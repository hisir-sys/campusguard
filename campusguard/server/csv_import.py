"""Bulk camera import from CSV (name,type,address,username,password,ai_enabled)."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from campusguard.settings import CameraCredentials
from campusguard.sources import build_capture_source

MAX_ROWS = 1000
SOURCE_TYPES = {"USB", "RTSP", "HTTP", "MJPEG", "IP"}
_ALIASES = {
    "name": "name", "camera": "name", "camera_name": "name", "label": "name",
    "type": "type", "source_type": "type",
    "address": "address", "url": "address", "source": "address", "source_address": "address",
    "username": "username", "user": "username",
    "password": "password", "pass": "password",
    "ai": "ai_enabled", "ai_enabled": "ai_enabled",
}


@dataclass(frozen=True)
class NewCamera:
    name: str
    source_type: str
    address: str
    credentials: CameraCredentials
    ai_enabled: bool


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
            seen.add(key)
        except ValueError as error:
            plan.errors.append({"row": offset, "error": str(error)})
            continue
        plan.valid.append(
            NewCamera(name, source_type, address, credentials, _truthy(values["ai_enabled"]))
        )
    return plan
