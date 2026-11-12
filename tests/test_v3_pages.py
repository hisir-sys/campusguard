"""v3 pages: incidents list and detail, alerts channels, services, widgets, autostart."""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from campusguard import autostart
from campusguard.storage import Repository
from campusguard.ui.alerts_v3 import AlertsPage
from campusguard.ui.incidents_v3 import IncidentsPage, status_label, tab_matches
from campusguard.ui.services_v3 import ServicesPage
from campusguard.ui.v3widgets import BarChart, Segmented, Switch


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def repo(tmp_path):
    repository = Repository(tmp_path / "cg.db", tmp_path / "footage")
    repository.add_camera("Gate 1", "RTSP", "rtsp://x/1")
    return repository


def _incident(repo, confidence=0.9, severity="HIGH"):
    camera = repo.list_cameras()[0]
    return repo.create_incident(camera, "FIGHT DETECTED", confidence, severity, 0)


def test_tabs_group_statuses():
    assert tab_matches("New", "NEW") and tab_matches("New", "ACKNOWLEDGED")
    assert tab_matches("Confirmed", "RESOLVED") and not tab_matches("Confirmed", "NEW")
    assert tab_matches("False alarm", "DISMISSED") and tab_matches("All", "ANYTHING")
    assert status_label("FALSE_ALARM") == "false alarm" and status_label("NEW") == "new"


def test_incidents_page_selects_newest_and_filters(app, repo):
    first = _incident(repo)
    second = _incident(repo, 0.7, "MEDIUM")
    page = IncidentsPage(repo)
    page.resize(1100, 700)
    assert page._selected == second["public_id"]
    assert page.detail_title.text() == second["public_id"]
    page.tabs.set_current("Confirmed", emit=True)
    assert page.count_label.text() == "0 of 2"
    page.tabs.set_current("All", emit=True)
    page.search_input.setText(first["public_id"])
    assert page.count_label.text() == "1 of 2"


def test_incidents_page_status_buttons_emit(app, repo):
    incident = _incident(repo)
    page = IncidentsPage(repo)
    seen = []
    page.status_change_requested.connect(lambda p, s: seen.append((p, s)))
    page.confirm_button.click()
    page.false_button.click()
    assert seen == [(incident["public_id"], "CONFIRMED"), (incident["public_id"], "FALSE_ALARM")]


def test_incident_note_is_saved_to_audit_log(app, repo):
    incident = _incident(repo)
    page = IncidentsPage(repo)
    page.note.setPlainText("Staff spoke to both students")
    page._save_note()
    page._load_note(incident["public_id"])
    assert page.note.toPlainText() == "Staff spoke to both students"


def test_alerts_page_lists_and_acknowledges(app, repo):
    _incident(repo)
    page = AlertsPage(repo)
    assert "1 active" in page.count_label.text()
    alert = repo.list_alerts()[0]
    page._acknowledge(alert["alert_id"])
    assert "0 active" in page.count_label.text()


def test_alert_channels_mirror_and_emit(app, repo):
    page = AlertsPage(repo)
    got = []
    page.channel_toggled.connect(lambda k, v: got.append((k, v)))
    page.set_channel_states({"alert_sound_toggle": True})
    assert page._switches["alert_sound_toggle"].isChecked() and got == []
    page._switches["alert_sound_toggle"].click()
    assert got == [("alert_sound_toggle", False)]


def test_services_page_states_and_signals(app):
    page = ServicesPage()
    seen = []
    page.detection_toggled.connect(seen.append)
    page.update_state(True, 3, 4, "local", "", 2, 12.0)
    assert page.detection_row.pill.text() == "Running" and page.detection_button.text() == "Pause"
    assert page.ingest_row.detail.text() == "3 of 4 live"
    page.detection_button.click()
    page.update_state(False, 0, 4, "remote", "10.0.0.5", 0, 0.0)
    assert page.detection_button.text() == "Resume" and page.link_row.pill.text() == "Connected"
    page.detection_button.click()
    assert seen == [False, True]


def test_switch_and_segmented(app):
    switch = Switch(True)
    assert switch.isChecked()
    switch.click()
    assert not switch.isChecked()
    tabs = Segmented(["24h", "7d", "30d"], "7d")
    got = []
    tabs.changed.connect(got.append)
    tabs.set_current("30d", emit=True)
    assert tabs.current() == "30d" and got == ["30d"]
    tabs.set_current("nope", emit=True)
    assert got == ["30d"]


def test_bar_chart_keeps_data(app):
    chart = BarChart()
    chart.set_data([("Mon", 1), ("Tue", 3)], animate=False)
    assert chart.data() == [("Mon", 1), ("Tue", 3)]


def test_autostart_is_a_safe_noop_off_windows(monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "linux")
    assert not autostart.supported() and not autostart.is_enabled() and not autostart.set_enabled(True)
    assert autostart.command().startswith('"')


def test_cameras_page_grid_edit_and_toggle(app, repo):
    from campusguard.settings import CameraConfig, CameraCredentials, CameraStats
    from campusguard.ui.cameras_v3 import CamerasPage
    from campusguard.ui.common import CameraFormDialog

    camera = repo.list_cameras()[0]
    repo.update_camera(camera.camera_id, "Gate One", "HTTP", "http://x/v")
    edited = repo.list_cameras()[0]
    assert (edited.name, edited.source_type, edited.source_address) == ("Gate One", "HTTP", "http://x/v")
    page = CamerasPage()
    cams = [
        CameraConfig("CAM-001", "Gate 1", "RTSP", "rtsp://x/1", True, "2026-01-01", 0.0, "Entrances"),
        CameraConfig("CAM-002", "Library", "RTSP", "rtsp://x/2", False, "2026-01-01", 0.0, "Indoor"),
    ]
    page.sync_cameras(cams, {"CAM-001": CameraStats(status="LIVE"), "CAM-002": CameraStats(status="OFFLINE")})
    assert page.summary_label.text() == "2 cameras · 1 online"
    assert page._cards["CAM-001"].toggle.text() == "Disable"
    assert page._cards["CAM-002"].toggle.text() == "Enable"
    seen = []
    page.ai_changed.connect(lambda cid, on: seen.append((cid, on)))
    page._cards["CAM-002"].toggle.click()
    assert seen == [("CAM-002", True)]
    page.attention_filter.setChecked(True)
    assert page._visible_ids() == ["CAM-002"]
    page.attention_filter.setChecked(False)

    dialog = CameraFormDialog(camera=cams[0], credentials=CameraCredentials("u", "p"), groups=["Entrances"])
    assert dialog.name_input.text() == "Gate 1"
    assert dialog.address_input.text() == "rtsp://x/1"
    assert dialog.username_input.text() == "u"
    dialog.name_input.setText("Gate One")
    dialog._save()
    assert dialog.form_data["name"] == "Gate One"
    assert dialog.form_data["group_name"] == "Entrances"


def test_incident_list_leaves_no_stale_rows(app, repo):
    from campusguard.ui.incidents_v3 import _ClickRow

    for _ in range(3):
        _incident(repo)
    page = IncidentsPage(repo)
    page.show()
    for row_id in [r["public_id"] for r in repo.list_incidents(limit=10)]:
        page.select(row_id)  # each select rebuilds the list in the same event-loop pass
    rows = page.findChildren(_ClickRow)
    assert len(rows) == 3
    assert all(row.parent() is not None for row in rows)
