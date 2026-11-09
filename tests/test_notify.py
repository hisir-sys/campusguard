import json
import time
from datetime import datetime

from campusguard import notify
from campusguard.notify import AlertDispatcher, AlertInfo, AlertPlan, parse_numbers, whatsapp_link
from campusguard.settings import AppSettings


def _info(severity="HIGH", clip=None):
    return AlertInfo("INC-1", "Gate 2", "cam-2", 0.91, severity, datetime(2026, 11, 9, 15, 0), clip)


def test_parse_numbers_and_link():
    assert parse_numbers("98765 43210, +44 7700 900123\n09876543210; 12", "91") == ["919876543210", "447700900123"]
    assert whatsapp_link("919876543210", "Hi there") == "https://wa.me/919876543210?text=Hi%20there"


def test_message_has_video_time_place_percentage():
    text = notify.format_message(_info(clip="/x.mp4"))
    assert "91%" in text and "Gate 2" in text and "09 Nov 2026" in text


def test_settings_roundtrip_and_validation():
    s = AppSettings.from_dict({"alert_numbers": "98765 43210", "escalate_minutes": 999, "whatsapp_mode": "bogus",
                               "alert_confirm_predictions": 99})
    assert s.alert_numbers == "98765 43210"
    assert s.escalate_minutes <= 60 and s.whatsapp_mode == "off" and 2 <= s.alert_confirm_predictions <= 6


def test_cloud_send_text(monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "_http", lambda url, data, headers, method="POST", timeout=20.0: (calls.append((url, data)) or (200, "{}")))
    ok, _ = notify.send_whatsapp_cloud("123", "tok", "919876543210", _info(), "msg")
    assert ok and "123/messages" in calls[0][0]
    assert not notify.send_whatsapp_cloud("", "", "9", _info(), "m")[0]


def test_dispatcher_threshold_and_escalation(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send_whatsapp_cloud", lambda *a, **k: (sent.append(a[2]) or (True, "ok")))
    d = AlertDispatcher()
    d.set_plan(AlertPlan(numbers=("1",), escalation_numbers=("2",), whatsapp_mode="cloud", phone_id="p", token="t", min_severity="HIGH"))
    d.dispatch(_info("MEDIUM"))
    time.sleep(0.2)
    assert sent == []
    d.dispatch(_info("HIGH"))
    time.sleep(0.2)
    assert sent == ["1"]
    d.cancel_all()
