"""Read many cameras from a CSV file (a spreadsheet saved as CSV) and check every row before anything is added.

This module has no Qt code, so the rules are easy to test. The dialog shows the result of `parse_camera_csv`
as a preview; only rows that pass every check are added.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urlsplit

from campusguard.settings import SENSITIVITY_LEVELS, CameraCredentials
from campusguard.sources import build_capture_source, build_rtsp_url
from campusguard.tuning import normalise_quiet_window

MAX_FILE_BYTES = 1_000_000
MAX_ROWS = 1000     # a whole school's list in one file (700-1000 cameras)
MAX_NAME_LENGTH = 80
MAX_GROUP_LENGTH = 40
DEFAULT_RTSP_PORT = 554
DEFAULT_RTSP_PATH = "/stream1"
SOURCE_TYPES = ("RTSP", "HTTP", "MJPEG", "IP", "USB")

# Header names people actually use, compared after lower-casing and turning "_", "-" and "/" into spaces.
_ALIASES = {
    "name": ("name", "camera name", "camera", "label", "title"),
    "type": ("type", "source type", "camera type", "kind", "protocol"),
    "address": (
        "address", "source address", "ip address", "ip", "host", "hostname", "url", "stream url",
        "rtsp url", "source", "connect", "connection", "ip address host",
    ),
    "port": ("port", "rtsp port", "stream port"),
    "path": ("path", "stream path", "rtsp path", "stream", "url path"),
    "username": ("username", "user name", "user", "login", "camera user", "camera username"),
    "password": ("password", "pass", "pwd", "camera password"),
    "group": ("group", "zone", "zone group", "location", "area", "block", "group name"),
    "sensitivity": ("sensitivity", "alert sensitivity", "threshold"),
    "ai": ("ai", "ai enabled", "enabled", "detection", "ai detection"),
    "quiet_start": ("quiet start", "quiet from", "quiet hours start", "pause from"),
    "quiet_end": ("quiet end", "quiet to", "quiet until", "quiet hours end", "pause until"),
    "pre_roll": ("pre roll", "pre roll seconds", "clip before", "seconds before"),
    "post_roll": ("post roll", "post roll seconds", "clip after", "seconds after"),
}
_ALIAS_TO_FIELD = {alias: field_name for field_name, names in _ALIASES.items() for alias in names}

_TYPE_WORDS = {
    "rtsp": "RTSP", "rtsps": "RTSP",
    "http": "HTTP", "https": "HTTP",
    "mjpeg": "MJPEG", "mjpg": "MJPEG", "motion jpeg": "MJPEG",
    "ip": "IP", "ip camera": "IP", "ipcam": "IP", "ip cam": "IP", "ipcamera": "IP",
    "usb": "USB", "webcam": "USB", "usb camera": "USB", "local": "USB",
}

# Words for the four alert-sensitivity levels (see SENSITIVITY_LEVELS).
_SENSITIVITY_WORDS = {
    "sensitive": 0, "more alerts": 0, "high": 0,
    "default": 1, "normal": 1, "medium": 1, "standard": 1, "balanced": 1,
    "cautious": 2, "fewer false alarms": 2, "low": 2,
    "strict": 3, "very few alerts": 3, "very low": 3,
}
_TRUE_WORDS = {"yes", "y", "true", "1", "on", "enabled", "enable"}
_FALSE_WORDS = {"no", "n", "false", "0", "off", "disabled", "disable"}

TEMPLATE_HEADER = [
    "name", "type", "address", "port", "path", "username", "password", "group", "sensitivity", "ai",
    "quiet_start", "quiet_end", "pre_roll", "post_roll",
]
TEMPLATE_ROWS = [
    ["# One camera per row. Required: name, type and address. Everything else is optional. "
     "Rows that start with # are ignored, so delete these examples or remove the #. "
     "group = the building (alerts are sent to that building's numbers). "
     "quiet_start/quiet_end = HH:MM, AI paused in between. pre_roll/post_roll = seconds of video kept before/after a fight."],
    ["# Main Gate", "RTSP", "192.168.1.64", "554", "Streaming/Channels/102", "admin", "change-me", "Main Building", "Default", "yes", "", "", "", ""],
    ["# Library Corridor", "RTSP", "rtsp://192.168.1.65:554/stream1", "", "", "admin", "change-me", "Block A", "Sensitive", "yes", "", "", "5", "10"],
    ["# Playground", "IP", "192.168.1.70:8080/video", "", "", "", "", "Outdoors", "Cautious", "yes", "", "", "", ""],
    ["# Gym (used at night)", "USB", "0", "", "", "", "", "Sports Block", "Default", "yes", "22:00", "06:00", "", ""],
]


def template_csv() -> str:
    """A ready-to-fill file: the header and a few commented-out examples (Excel-friendly line endings)."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(TEMPLATE_HEADER)
    for row in TEMPLATE_ROWS:
        writer.writerow(row)
    return out.getvalue()


def sensitivity_help() -> str:
    return ", ".join(str(label).split(" ")[0] for label, _ in SENSITIVITY_LEVELS)


@dataclass
class ImportRow:
    line: int
    name: str = ""
    source_type: str = ""
    source_address: str = ""
    username: str = ""
    password: str = ""
    group_name: str = ""
    threshold_offset: float = 0.0
    ai_enabled: bool = True
    quiet_start: str = ""
    quiet_end: str = ""
    pre_roll_seconds: float = 0.0
    post_roll_seconds: float = 0.0
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    skip_reason: str = ""  # a valid row that is not imported because the camera already exists

    @property
    def ready(self) -> bool:
        return not self.problems and not self.skip_reason

    @property
    def status(self) -> str:
        if self.problems:
            return " ".join(self.problems)
        if self.skip_reason:
            return self.skip_reason
        return "Ready" + (f" · {' · '.join(self.notes)}" if self.notes else "")

    def values(self) -> dict:
        """The same shape the Add camera form produces, plus ai_enabled."""
        return {
            "name": self.name,
            "source_type": self.source_type,
            "source_address": self.source_address,
            "username": self.username,
            "password": self.password,
            "group_name": self.group_name,
            "threshold_offset": self.threshold_offset,
            "ai_enabled": self.ai_enabled,
            "quiet_start": self.quiet_start,
            "quiet_end": self.quiet_end,
            "pre_roll_seconds": self.pre_roll_seconds,
            "post_roll_seconds": self.post_roll_seconds,
        }


@dataclass
class ImportPlan:
    rows: list[ImportRow] = field(default_factory=list)
    ignored_columns: list[str] = field(default_factory=list)
    delimiter: str = ","
    problem: str = ""  # the file as a whole cannot be used
    commented_rows: int = 0  # rows starting with # (instructions or examples), which are ignored

    @property
    def ready(self) -> list[ImportRow]:
        return [row for row in self.rows if row.ready]

    @property
    def with_problems(self) -> list[ImportRow]:
        return [row for row in self.rows if row.problems]

    @property
    def skipped(self) -> list[ImportRow]:
        return [row for row in self.rows if row.skip_reason and not row.problems]

    def summary(self) -> str:
        if self.problem:
            return self.problem
        if not self.rows:
            if self.commented_rows > 1:
                return "Only example rows were found. Remove the # at the start of a row to use it, or add your own cameras."
            return "No cameras found in this file."
        parts = [f"{len(self.ready)} ready"]
        if self.with_problems:
            parts.append(f"{len(self.with_problems)} need fixing")
        if self.skipped:
            parts.append(f"{len(self.skipped)} already added or repeated")
        return " · ".join(parts)


def _plain(text: str) -> str:
    return re.sub(r"[\s_/\-]+", " ", text.strip().lower()).strip()


def decode_csv(data: bytes) -> str:
    """Excel on Windows saves "CSV (Comma delimited)" in the local code page, so fall back to it."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _delimiter(text: str) -> str:
    first = next((line for line in text.splitlines() if line.strip()), "")
    counts = {candidate: first.count(candidate) for candidate in (",", ";", "\t", "|")}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","


def camera_key(source_type: str, address: str) -> str:
    """Two entries for the same camera give the same key, however the address was typed."""
    try:
        source = build_capture_source(source_type, address)
    except ValueError:
        return f"{source_type.upper()}:{address.strip().lower()}"
    if isinstance(source, int):
        return f"usb:{source}"
    text = source.strip().lower()
    try:
        parts = urlsplit(text)
        default = {"rtsp": 554, "rtsps": 322, "http": 80, "https": 443}.get(parts.scheme)
        if parts.hostname and parts.port is not None and parts.port == default:
            host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
            text = parts._replace(netloc=host).geturl()
    except ValueError:
        pass
    return text.rstrip("/")


def _address_parts(address: str):
    """Split an address with or without a scheme. Returns (scheme, host, port, path_with_query) or None."""
    text = address.strip()
    try:
        parts = urlsplit(text if "://" in text else "//" + text)
        port = parts.port
    except ValueError:
        return None
    host = parts.hostname or ""
    if not host:
        return None
    path = parts.path + (f"?{parts.query}" if parts.query else "")
    return parts.scheme.lower(), host, port, path


def compose_address(source_type: str, address: str, port: str, path: str) -> tuple[str, list[str]]:
    """Fill in the optional port and path columns. An address that is already complete is left exactly as typed."""
    notes: list[str] = []
    address = address.strip()
    port = port.strip()
    path = path.strip()
    if source_type == "USB" or not address:
        return address, notes
    if address.count(":") > 1 and not address.startswith("[") and "://" not in address:
        # A bare IPv6 address such as 2001:db8::1: there is no port or path to read from it.
        parts = (("", address, None, ""))
    else:
        parts = _address_parts(address)
    if parts is None or (isinstance(parts, tuple) and parts[0] and parts[0] not in {"rtsp", "rtsps", "http", "https"}):
        return address, notes  # let the normal address check explain the problem
    scheme, host, embedded_port, embedded_path = parts
    if any(ch in address for ch in "@") and "://" in address:
        return address, notes  # credentials in the URL are rejected by the normal check
    port_text = port
    if port_text:
        try:
            port_number = int(port_text)
        except ValueError:
            raise ValueError("The port must be a number from 1 to 65535.") from None
        if not 1 <= port_number <= 65535:
            raise ValueError("The port must be a number from 1 to 65535.")

    if source_type == "RTSP" and not scheme:
        use_port = embedded_port or (int(port_text) if port_text else DEFAULT_RTSP_PORT)
        use_path = embedded_path or path
        if not use_path:
            use_path = DEFAULT_RTSP_PATH
            notes.append(f"no stream path given, using {DEFAULT_RTSP_PATH}")
        return build_rtsp_url(host, use_port, "", "", use_path), notes

    if not (port_text and embedded_port is None) and not (path and embedded_path in {"", "/"}):
        return address, notes  # nothing to add
    shown_host = f"[{host}]" if ":" in host else host
    netloc = f"{shown_host}:{port_text}" if port_text and embedded_port is None else (
        f"{shown_host}:{embedded_port}" if embedded_port else shown_host
    )
    use_path = embedded_path
    if path and embedded_path in {"", "/"}:
        use_path = path if path.startswith("/") else "/" + path
    default_scheme = "rtsp" if source_type == "RTSP" else "http"
    return f"{scheme or default_scheme}://{netloc}{use_path}", notes


def infer_type(address: str) -> str:
    """The type a blank cell can safely be read as: only an explicit scheme or a device number says."""
    lowered = address.strip().lower()
    if lowered.startswith(("rtsp://", "rtsps://")):
        return "RTSP"
    if lowered.startswith(("http://", "https://")):
        return "HTTP"
    if lowered.isdigit():
        return "USB"
    return ""


def parse_sensitivity(text: str) -> float:
    cleaned = _plain(text)
    if not cleaned:
        return 0.0
    try:  # a number such as -0.1 or 0,2 (checked before _plain turns the minus sign into a space)
        number = float(text.strip().replace(",", "."))
    except ValueError:
        number = None
    if number is not None:
        levels = [float(offset) for _, offset in SENSITIVITY_LEVELS]
        if not min(levels) - 0.05 <= number <= max(levels) + 0.05:
            raise ValueError(f"Sensitivity must be one of {sensitivity_help()}.")
        return min(levels, key=lambda level: abs(level - number))
    if cleaned in _SENSITIVITY_WORDS:
        return float(SENSITIVITY_LEVELS[_SENSITIVITY_WORDS[cleaned]][1])
    first = cleaned.split(" ")[0]
    if first in _SENSITIVITY_WORDS:
        return float(SENSITIVITY_LEVELS[_SENSITIVITY_WORDS[first]][1])
    raise ValueError(f"Sensitivity must be one of {sensitivity_help()}.")


def parse_flag(text: str) -> bool:
    cleaned = text.strip().lower()
    if not cleaned or cleaned in _TRUE_WORDS:
        return True
    if cleaned in _FALSE_WORDS:
        return False
    raise ValueError("AI must be yes or no.")


def _read_rows(text: str, delimiter: str) -> list[tuple[int, list[str]]]:
    rows: list[tuple[int, list[str]]] = []
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    for cells in reader:
        rows.append((reader.line_num, [cell for cell in cells]))
    return rows


def parse_camera_csv(
    data: bytes | str,
    existing: Iterable[tuple[str, str, str]] = (),
) -> ImportPlan:
    """Check a CSV file. `existing` is (name, source type, address) for the cameras already added."""
    plan = ImportPlan()
    if isinstance(data, bytes):
        if len(data) > MAX_FILE_BYTES:
            plan.problem = "This file is too large to be a list of cameras (over 1 MB). Check that it is the right file."
            return plan
        if data.startswith(b"PK"):
            plan.problem = "This looks like an Excel workbook. In Excel choose File → Save As → CSV (Comma delimited), then pick that file."
            return plan
        text = decode_csv(data)
    else:
        text = data
    text = text.lstrip("\ufeff")
    if "\x00" in text:
        plan.problem = "This does not look like a CSV text file."
        return plan

    plan.delimiter = _delimiter(text)
    try:
        table = _read_rows(text, plan.delimiter)
    except csv.Error as error:
        plan.problem = f"The file could not be read as CSV ({error})."
        return plan

    header: list[str] | None = None
    header_line = 0
    body: list[tuple[int, list[str]]] = []
    for line, cells in table:
        if not any(cell.strip() for cell in cells):
            continue
        if cells and cells[0].strip().startswith("#"):
            plan.commented_rows += 1
            continue
        if header is None:
            header, header_line = cells, line
        else:
            body.append((line, cells))
    if header is None:
        plan.problem = "The file is empty."
        return plan

    columns: dict[str, int] = {}
    for index, title in enumerate(header):
        field_name = _ALIAS_TO_FIELD.get(_plain(title))
        if field_name is None:
            if title.strip():
                plan.ignored_columns.append(title.strip())
        elif field_name in columns:
            plan.ignored_columns.append(title.strip())
        else:
            columns[field_name] = index
    if "address" not in columns or ("name" not in columns):
        missing = [label for key, label in (("name", "name"), ("address", "address")) if key not in columns]
        plan.problem = (
            f"The first row must name the columns. Missing: {', '.join(missing)}. "
            "Use a header like: name, type, address, username, password, group."
        )
        return plan
    if len(body) > MAX_ROWS:
        plan.problem = f"This file has {len(body)} cameras; import at most {MAX_ROWS} at a time."
        return plan

    existing_by_key: dict[str, str] = {}
    for name, source_type, address in existing:
        existing_by_key.setdefault(camera_key(source_type, address), name)
    seen: dict[str, ImportRow] = {}

    def cell(cells: list[str], key: str, strip: bool = True) -> str:
        index = columns.get(key)
        if index is None or index >= len(cells):
            return ""
        return cells[index].strip() if strip else cells[index]

    for line, cells in body:
        row = ImportRow(line=line)
        plan.rows.append(row)
        row.name = " ".join(cell(cells, "name").split())
        raw_address = cell(cells, "address")
        raw_type = cell(cells, "type")
        row.username = cell(cells, "username")
        row.password = cell(cells, "password", strip=False)
        row.group_name = " ".join(cell(cells, "group").split())

        if not row.name:
            row.problems.append("Name is missing.")
        elif len(row.name) > MAX_NAME_LENGTH:
            row.problems.append(f"Name is longer than {MAX_NAME_LENGTH} characters.")
        if len(row.group_name) > MAX_GROUP_LENGTH:
            row.problems.append(f"Zone is longer than {MAX_GROUP_LENGTH} characters.")
        if not raw_address:
            row.problems.append("Address is missing.")

        if raw_type:
            row.source_type = _TYPE_WORDS.get(_plain(raw_type), "")
            if not row.source_type:
                row.problems.append(f"Type “{raw_type}” is not one of {', '.join(SOURCE_TYPES)}.")
        elif raw_address:
            row.source_type = infer_type(raw_address)
            if not row.source_type:
                row.problems.append(f"Type is missing. Use one of {', '.join(SOURCE_TYPES)}.")

        try:
            row.threshold_offset = parse_sensitivity(cell(cells, "sensitivity"))
        except ValueError as error:
            row.problems.append(str(error))
        try:
            row.ai_enabled = parse_flag(cell(cells, "ai"))
        except ValueError as error:
            row.problems.append(str(error))
        raw_start, raw_end = cell(cells, "quiet_start"), cell(cells, "quiet_end")
        if raw_start or raw_end:
            row.quiet_start, row.quiet_end = normalise_quiet_window(raw_start, raw_end)
            if not row.quiet_start:
                row.problems.append("Quiet hours need two different times like 22:00 and 06:00.")
        for key, label, maximum in (("pre_roll", "pre_roll", 15.0), ("post_roll", "post_roll", 30.0)):
            raw_seconds = cell(cells, key)
            if not raw_seconds:
                continue
            try:
                seconds = float(raw_seconds)
                if not 0 <= seconds <= maximum:
                    raise ValueError
            except ValueError:
                row.problems.append(f"{label} must be a number of seconds from 0 to {maximum:g}.")
                continue
            if key == "pre_roll":
                row.pre_roll_seconds = seconds
            else:
                row.post_roll_seconds = seconds

        if raw_address and row.source_type:
            try:
                row.source_address, row.notes = compose_address(
                    row.source_type, raw_address, cell(cells, "port"), cell(cells, "path")
                )
                build_capture_source(
                    row.source_type, row.source_address, CameraCredentials(row.username, row.password)
                )
            except ValueError as error:
                row.source_address = raw_address
                row.problems.append(str(error))
        else:
            row.source_address = raw_address

        if row.problems:
            continue
        key = camera_key(row.source_type, row.source_address)
        if key in existing_by_key:
            row.skip_reason = f"Already added as {existing_by_key[key]}."
        elif key in seen:
            row.skip_reason = f"Same camera as line {seen[key].line}."
        else:
            seen[key] = row

    return plan
