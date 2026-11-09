"""Phone alerts: WhatsApp (free click-to-chat or Meta Cloud API) and ntfy push.

Cost, honestly:
  * ``whatsapp_link``  free. Opens WhatsApp with the message already typed; a person taps Send.
                       A video cannot be attached this way.
  * ``whatsapp_cloud`` automatic text + video, but needs a Meta WhatsApp Business Cloud API account
                       (free to set up; Meta charges per business-started conversation).
  * ``ntfy``           free automatic push to a phone with the ntfy app. Public ntfy.sh is a third
                       party: leave "attach clip" off, or self-host ntfy, for children's footage.

All network calls go through ``_http`` so tests can replace it.
"""
from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
MAX_NUMBERS = 10
GRAPH_URL = "https://graph.facebook.com/v20.0"
MAX_VIDEO_BYTES = 16 * 1024 * 1024  # WhatsApp's video limit


def parse_numbers(text: str, country_code: str = "91") -> list[str]:
    """'98765 43210, +44 7700 900123' -> ['919876543210', '447700900123'] (digits only, deduped)."""
    code = re.sub(r"\D", "", country_code or "")
    seen: list[str] = []
    for part in re.split(r"[,\n;]+", text or ""):
        raw = part.strip()
        if not raw:
            continue
        digits = re.sub(r"\D", "", raw)
        if raw.startswith("00"):
            digits = digits[2:]
        elif not raw.startswith("+") and code and len(digits) == 10:
            digits = code + digits          # national number: add the country code
        elif not raw.startswith("+") and code and digits.startswith("0") and len(digits) == 11:
            digits = code + digits[1:]
        if 8 <= len(digits) <= 15 and digits not in seen:
            seen.append(digits)
    return seen[:MAX_NUMBERS]


def severity_passes(severity: str, minimum: str) -> bool:
    return SEVERITY_ORDER.get(str(severity).upper(), 0) >= SEVERITY_ORDER.get(str(minimum).upper(), 1)


@dataclass(frozen=True)
class AlertInfo:
    incident_id: str
    camera_name: str
    camera_id: str
    confidence: float        # 0..1 or 0..100
    severity: str
    when: datetime
    clip_path: str | None = None

    @property
    def percent(self) -> float:
        return self.confidence * 100.0 if self.confidence <= 1.0 else self.confidence


def format_message(info: AlertInfo, escalated: bool = False) -> str:
    lines = [
        "CampusGuard ESCALATED ALERT - not yet acknowledged" if escalated else "CampusGuard ALERT",
        f"Possible fight: {info.percent:.0f}% confidence ({info.severity.title()})",
        f"Place: {info.camera_name} ({info.camera_id})",
        f"Time: {info.when.strftime('%d %b %Y, %H:%M')}",
        f"Incident: {info.incident_id}",
    ]
    if info.clip_path:
        lines.append("Video: saved on the CampusGuard computer (see the incident).")
    lines.append("This is an automatic detection - please verify before acting.")
    return "\n".join(lines)


def whatsapp_link(number: str, message: str) -> str:
    digits = re.sub(r"\D", "", number)
    return f"https://wa.me/{digits}?text={urllib.parse.quote(message)}"


# ----------------------------------------------------------------------------
# HTTP (replaceable in tests)
# ----------------------------------------------------------------------------
def _http(url: str, data: bytes | None, headers: dict[str, str], method: str = "POST", timeout: float = 20.0):
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def _multipart(fields: dict[str, str], file_field: str, filename: str, content: bytes, mime: str) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for key, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n".encode() + content + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _clip_bytes(path: str | None) -> bytes | None:
    if not path:
        return None
    try:
        file = Path(path)
        if not file.is_file() or file.stat().st_size > MAX_VIDEO_BYTES:
            return None
        return file.read_bytes()
    except OSError:
        return None


# ----------------------------------------------------------------------------
# Senders: each returns (ok, detail)
# ----------------------------------------------------------------------------
def send_ntfy(server: str, topic: str, info: AlertInfo, message: str, attach_clip: bool) -> tuple[bool, str]:
    topic = re.sub(r"[^A-Za-z0-9_-]", "", topic or "")
    if not topic:
        return False, "ntfy topic is empty"
    base = (server or "https://ntfy.sh").rstrip("/")
    priority = "5" if info.severity.upper() == "CRITICAL" else "4" if info.severity.upper() == "HIGH" else "3"
    headers = {"Title": f"CampusGuard: {info.camera_name} {info.percent:.0f}%", "Priority": priority, "Tags": "rotating_light"}
    clip = _clip_bytes(info.clip_path) if attach_clip else None
    if clip is not None:
        headers.update({"Filename": f"{info.incident_id}.mp4", "Message": message.replace("\n", " | ")})
        status, body = _http(f"{base}/{topic}", clip, headers, "PUT", timeout=60)
    else:
        status, body = _http(f"{base}/{topic}", message.encode("utf-8"), headers, "POST")
    return 200 <= status < 300, f"ntfy {status}" if not 200 <= status < 300 else "ntfy ok"


def _graph_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def send_whatsapp_cloud(
    phone_id: str, token: str, number: str, info: AlertInfo, message: str,
    template: str = "", send_clip: bool = True,
) -> tuple[bool, str]:
    if not (phone_id and token):
        return False, "WhatsApp Cloud API phone number ID or token is missing"
    url = f"{GRAPH_URL}/{urllib.parse.quote(phone_id)}/messages"
    if template:
        body = {
            "messaging_product": "whatsapp", "to": number, "type": "template",
            "template": {"name": template, "language": {"code": "en"}, "components": [{
                "type": "body", "parameters": [{"type": "text", "text": text} for text in (
                    info.camera_name, f"{info.percent:.0f}%", info.when.strftime("%d %b %Y %H:%M"), info.incident_id)],
            }]},
        }
    else:
        body = {"messaging_product": "whatsapp", "to": number, "type": "text", "text": {"body": message}}
    status, text = _http(url, json.dumps(body).encode(), _graph_headers(token))
    if not 200 <= status < 300:
        return False, f"WhatsApp {status}: {text[:160]}"
    clip = _clip_bytes(info.clip_path) if send_clip else None
    if clip is not None:
        payload, content_type = _multipart(
            {"messaging_product": "whatsapp", "type": "video/mp4"}, "file", f"{info.incident_id}.mp4", clip, "video/mp4"
        )
        status, text = _http(f"{GRAPH_URL}/{urllib.parse.quote(phone_id)}/media", payload,
                             {"Authorization": f"Bearer {token}", "Content-Type": content_type}, timeout=90)
        if 200 <= status < 300:
            try:
                media_id = json.loads(text)["id"]
            except (ValueError, KeyError):
                return True, "text sent; video upload gave no id"
            video = {"messaging_product": "whatsapp", "to": number, "type": "video",
                     "video": {"id": media_id, "caption": f"{info.camera_name} {info.when.strftime('%H:%M')} - {info.incident_id}"}}
            status, text = _http(url, json.dumps(video).encode(), _graph_headers(token))
            if not 200 <= status < 300:
                return True, f"text sent; video failed ({status})"
        else:
            return True, f"text sent; video upload failed ({status})"
    return True, "whatsapp ok"


# ----------------------------------------------------------------------------
# Dispatcher
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class AlertPlan:
    numbers: tuple[str, ...] = ()
    escalation_numbers: tuple[str, ...] = ()
    escalate_minutes: int = 3
    min_severity: str = "MEDIUM"
    whatsapp_mode: str = "off"           # off | link | cloud
    phone_id: str = ""
    template: str = ""
    token: str = ""
    ntfy_topic: str = ""
    ntfy_server: str = "https://ntfy.sh"
    ntfy_attach_clip: bool = False

    @property
    def active(self) -> bool:
        return bool((self.numbers and self.whatsapp_mode != "off") or self.ntfy_topic)


class AlertDispatcher:
    """Sends alerts on background threads and escalates unacknowledged incidents."""

    def __init__(self, log: Callable[[str, str], None] | None = None) -> None:
        self.plan = AlertPlan()
        self._log = log or (lambda kind, message: None)
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def set_plan(self, plan: AlertPlan) -> None:
        self.plan = plan

    def should_send(self, severity: str) -> bool:
        return self.plan.active and severity_passes(severity, self.plan.min_severity)

    def dispatch(self, info: AlertInfo, is_acknowledged: Callable[[], bool] | None = None, escalated: bool = False) -> None:
        """Send now (background) and schedule escalation when nobody acknowledges."""
        plan = self.plan
        if not self.should_send(info.severity):
            return
        threading.Thread(target=self._send_all, args=(plan, info, escalated), daemon=True).start()
        if not escalated and is_acknowledged is not None and plan.escalate_minutes > 0 and plan.escalation_numbers:
            self._schedule_escalation(plan, info, is_acknowledged)

    def send_clip_later(self, info: AlertInfo) -> None:
        """The clip finished recording after the first alert: send the video now."""
        plan = self.plan
        if not self.should_send(info.severity) or not info.clip_path:
            return
        def work() -> None:
            self._send_all(plan, info, False, clip_only=True)
        threading.Thread(target=work, daemon=True).start()

    def cancel_all(self) -> None:
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()

    def _schedule_escalation(self, plan: AlertPlan, info: AlertInfo, is_acknowledged: Callable[[], bool]) -> None:
        def fire() -> None:
            with self._lock:
                self._timers.pop(info.incident_id, None)
            try:
                if is_acknowledged():
                    return
            except Exception:
                return
            self._send_all(plan, info, True)

        timer = threading.Timer(plan.escalate_minutes * 60, fire)
        timer.daemon = True
        with self._lock:
            old = self._timers.pop(info.incident_id, None)
            if old:
                old.cancel()
            self._timers[info.incident_id] = timer
        timer.start()

    def _send_all(self, plan: AlertPlan, info: AlertInfo, escalated: bool, clip_only: bool = False) -> None:
        message = format_message(info, escalated)
        targets = plan.escalation_numbers if escalated and plan.escalation_numbers else plan.numbers
        results: list[tuple[bool, str]] = []
        if plan.ntfy_topic and not (clip_only and not plan.ntfy_attach_clip):
            results.append(send_ntfy(plan.ntfy_server, plan.ntfy_topic, info, message, plan.ntfy_attach_clip and bool(info.clip_path)))
        if plan.whatsapp_mode == "cloud":
            for number in targets:
                if clip_only:
                    # text was already sent at detection time; send only the video
                    results.append(self._video_only(plan, number, info))
                else:
                    results.append(send_whatsapp_cloud(plan.phone_id, plan.token, number, info, message, plan.template,
                                                       send_clip=bool(info.clip_path)))
        for ok, detail in results:
            if not ok:
                self._log("phone_alert_failed", f"Phone alert for {info.incident_id} failed: {detail}")

    @staticmethod
    def _video_only(plan: AlertPlan, number: str, info: AlertInfo) -> tuple[bool, str]:
        clip = _clip_bytes(info.clip_path)
        if clip is None:
            return False, "clip unavailable or over 16 MB"
        token, phone_id = plan.token, plan.phone_id
        payload, content_type = _multipart(
            {"messaging_product": "whatsapp", "type": "video/mp4"}, "file", f"{info.incident_id}.mp4", clip, "video/mp4")
        status, text = _http(f"{GRAPH_URL}/{urllib.parse.quote(phone_id)}/media", payload,
                             {"Authorization": f"Bearer {token}", "Content-Type": content_type}, timeout=90)
        if not 200 <= status < 300:
            return False, f"video upload {status}"
        try:
            media_id = json.loads(text)["id"]
        except (ValueError, KeyError):
            return False, "video upload gave no id"
        video = {"messaging_product": "whatsapp", "to": number, "type": "video",
                 "video": {"id": media_id, "caption": f"{info.camera_name} - {info.incident_id}"}}
        status, text = _http(f"{GRAPH_URL}/{urllib.parse.quote(phone_id)}/messages", json.dumps(video).encode(), _graph_headers(token))
        return 200 <= status < 300, f"video {status}"
