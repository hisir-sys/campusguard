import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from campusguard.server.recorder import severity_for
from campusguard.ui.severity import SEVERITY_TITLES, URGENT, severity_color, severity_title


def test_every_server_severity_has_one_title_and_a_color():
    for confidence in (0.5, 0.7, 0.85, 0.95, 1.0):
        severity = severity_for(confidence)
        assert severity in SEVERITY_TITLES
        assert severity_title(severity) and severity_color(severity).startswith("#")


def test_titles_match_the_popup_alert_and_critical_is_urgent():
    from campusguard.ui.severity_alert import SeverityAlertToast
    levels = SeverityAlertToast._LEVELS
    assert severity_title("MEDIUM") == levels["medium"]["title"]
    assert severity_title("HIGH") == levels["high"]["title"]
    assert severity_title("CRITICAL") == levels["critical"]["title"]
    assert {"HIGH", "CRITICAL"} == URGENT
