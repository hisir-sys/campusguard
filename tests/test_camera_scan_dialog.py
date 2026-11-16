"""The camera form's scan dialog: scan, enter credentials, test, then add."""
from __future__ import annotations

import ipaddress
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from campusguard.camera_discovery import FoundCamera
from campusguard.ui import camera_scan
from campusguard.ui.common import CameraFormDialog


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _finish_scan_threads():
    """Let scan and test threads end before the next test so none is destroyed while running."""
    yield
    for thread in list(camera_scan._ACTIVE):
        try:
            if hasattr(thread, "cancel"):
                thread.cancel()
            thread.wait(8000)
        except RuntimeError:
            pass


@pytest.fixture
def fake_network(monkeypatch):
    probes = []

    def scan(cancel, progress):
        progress(100, 254)
        progress(254, 254)
        return [FoundCamera("192.168.1.14", {554}, True), FoundCamera("192.168.1.21", {554, 8554}), FoundCamera("192.168.1.77", set(), True)]

    def probe(source_type, address, credentials):
        probes.append((source_type, address, credentials.username, credentials.password))
        if credentials.password == "right":
            return True, "Connection successful — 1280x720"
        return False, "Connection failed. Check the source address and camera credentials."

    monkeypatch.setattr(camera_scan, "_scan", scan)
    monkeypatch.setattr(camera_scan, "_probe", probe)
    monkeypatch.setattr(camera_scan.camera_discovery, "local_network", lambda address=None: ipaddress.ip_network("192.168.1.0/24"))
    monkeypatch.setattr(camera_scan.camera_discovery, "local_address", lambda: "192.168.1.5")
    return probes


def _wait(app, condition, seconds=8.0):
    end = time.time() + seconds
    while time.time() < end and not condition():
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert condition(), "timed out waiting for the dialog"


def _scanned(app):
    dialog = camera_scan.CameraScanDialog()
    dialog.show()
    dialog.scan_button.click()
    _wait(app, lambda: len(dialog._rows) == 3 and dialog.scan_button.isEnabled())
    return dialog


def test_scan_lists_cameras_with_add_locked_until_tested(app, fake_network):
    dialog = _scanned(app)
    assert [row.camera.host for row in dialog._rows] == ["192.168.1.14", "192.168.1.21", "192.168.1.77"]
    assert dialog.table.item(0, 1).text() == "ONVIF, port 554"
    assert all(not row.add_button.isEnabled() for row in dialog._rows)
    assert "Found 3 possible cameras" in dialog.scan_status.text()
    assert "permission to scan" in camera_scan.PERMISSION_NOTE
    dialog.close()


def test_failed_test_keeps_add_locked_and_a_good_one_unlocks_it(app, fake_network):
    dialog = _scanned(app)
    row = dialog._rows[0]
    row.username.setText("admin")
    row.password.setText("wrong")
    row.path.setCurrentText("/Streaming/Channels/101")
    dialog.test_row(row)
    _wait(app, lambda: not row.busy)
    assert not row.add_button.isEnabled() and "failed" in row.status.text().lower()
    row.password.setText("right")
    dialog.test_row(row)
    _wait(app, lambda: row.tested_ok)
    assert row.add_button.isEnabled() and "successful" in row.status.text()
    # credentials travel separately, never inside the URL
    assert fake_network[-1] == ("RTSP", "rtsp://192.168.1.14:554/Streaming/Channels/101", "admin", "right")
    assert all("@" not in probe[1] for probe in fake_network)
    # changing anything after a good test invalidates it
    row.password.setText("right!")
    assert not row.add_button.isEnabled() and row.status.text() == "Not tested"
    dialog.close()


def test_adding_a_tested_camera_returns_its_details(app, fake_network):
    dialog = _scanned(app)
    row = dialog._rows[1]
    row.username.setText("viewer")
    row.password.setText("right")
    dialog.test_row(row)
    _wait(app, lambda: row.tested_ok)
    dialog.add_row(row)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected == {
        "host": "192.168.1.21", "port": 554, "path": "/stream1",
        "username": "viewer", "password": "right", "message": "Connection successful — 1280x720",
    }


def test_untested_camera_cannot_be_added(app, fake_network):
    dialog = _scanned(app)
    dialog.add_row(dialog._rows[0])
    assert dialog.selected is None and dialog.isVisible()
    dialog.close()


def test_bad_stream_path_is_reported_not_raised(app, fake_network):
    dialog = _scanned(app)
    row = dialog._rows[0]
    row.camera.host = "999.1.1.1"
    dialog.test_row(row)
    assert "not a valid IP" in row.status.text() and not row.busy
    dialog.close()


def test_empty_scan_explains_what_to_do(app, monkeypatch, fake_network):
    monkeypatch.setattr(camera_scan, "_scan", lambda cancel, progress: [])
    dialog = camera_scan.CameraScanDialog()
    dialog.show()
    dialog.scan_button.click()
    _wait(app, lambda: dialog.empty_label.isVisible())
    assert "No cameras found" in dialog.scan_status.text() and "type the address" in dialog.empty_label.text()
    dialog.close()


def test_scan_failure_is_shown(app, monkeypatch, fake_network):
    def boom(cancel, progress):
        raise RuntimeError("This computer is not on a private network, so there is nothing safe to scan.")

    monkeypatch.setattr(camera_scan, "_scan", boom)
    dialog = camera_scan.CameraScanDialog()
    dialog.show()
    dialog.scan_button.click()
    _wait(app, lambda: "Scan failed" in dialog.scan_status.text())
    assert "nothing safe to scan" in dialog.scan_status.text()
    dialog.close()


def test_no_private_network_disables_scanning(app, monkeypatch, fake_network):
    monkeypatch.setattr(camera_scan.camera_discovery, "local_network", lambda address=None: None)
    dialog = camera_scan.CameraScanDialog()
    assert not dialog.scan_button.isEnabled() and "nothing safe to scan" in dialog.network_label.text()


def test_closing_during_a_scan_cancels_it(app, monkeypatch, fake_network):
    started = []

    def slow(cancel, progress):
        started.append(True)
        while not cancel.is_set():
            time.sleep(0.01)
        return []

    monkeypatch.setattr(camera_scan, "_scan", slow)
    dialog = camera_scan.CameraScanDialog()
    dialog.show()
    dialog.scan_button.click()
    _wait(app, lambda: bool(started))
    dialog.reject()
    assert not dialog._thread.isRunning()


def test_form_scan_button_fills_the_form_without_credentials_in_the_url(app, monkeypatch, fake_network):
    form = CameraFormDialog()
    form.show()
    assert form.scan_widget.isVisible()
    form.type_input.setCurrentText("USB")
    assert not form.scan_widget.isVisible()
    form.type_input.setCurrentText("IP")
    assert form.scan_widget.isVisible()

    class Pick(camera_scan.CameraScanDialog):
        def exec(self):
            self.start_scan()
            _wait(app, lambda: len(self._rows) == 3)
            row = self._rows[1]
            row.username.setText("viewer")
            row.password.setText("right")
            self.test_row(row)
            _wait(app, lambda: row.tested_ok)
            self.add_row(row)
            return self.result()

    monkeypatch.setattr(camera_scan, "CameraScanDialog", Pick)
    form.scan_network_button.click()
    assert form.type_input.currentText() == "RTSP"
    assert form.address_input.text() == "rtsp://192.168.1.21:554/stream1"
    assert (form.username_input.text(), form.password_input.text()) == ("viewer", "right")
    assert form.name_input.text() == "Camera 192.168.1.21"
    assert "successful" in form.test_status.text()
    form._save()
    assert form.form_data["source_address"] == "rtsp://192.168.1.21:554/stream1" and "@" not in form.form_data["source_address"]


def test_internet_address_shows_the_port_forwarding_warning(app):
    form = CameraFormDialog()
    form.show()
    assert not form.network_note.isVisible()
    form.type_input.setCurrentText("RTSP")
    form.address_input.setText("rtsp://8.8.8.8:554/live")
    assert form.network_note.isVisible() and "port" in form.network_note.text() and "password" in form.network_note.text()
    form.address_input.setText("rtsp://192.168.1.50:554/live")
    assert not form.network_note.isVisible()
    form.type_input.setCurrentText("IP")
    form.address_input.setText("cam.myschool.in:8080/video")
    assert form.network_note.isVisible()
    form.type_input.setCurrentText("USB")
    assert not form.network_note.isVisible()
    form.close()


def test_a_public_ip_can_be_saved(app):
    form = CameraFormDialog()
    form.name_input.setText("Remote gate")
    form.type_input.setCurrentText("RTSP")
    form.address_input.setText("rtsp://8.8.8.8:554/live")
    form._save()
    assert form.form_data is not None and form.form_data["source_address"] == "rtsp://8.8.8.8:554/live"
    assert not form.validation_status.isVisible() or not form.validation_status.text()
