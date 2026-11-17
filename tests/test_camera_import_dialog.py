"""The Import CSV dialog and the one-go batch add in the main window."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from campusguard.camera_import import template_csv
from campusguard.settings import CameraConfig
from campusguard.ui.camera_import_dialog import CameraImportDialog
from campusguard.ui.main_window import CredentialVaultUnavailable, MainWindow


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


GOOD = (
    "name,type,address,username,password,group\n"
    "Gate,RTSP,192.168.1.2,admin,pw,Entrances\n"
    "Hall,IP,192.168.1.3:8080/video,,,\n"
    "Bad,RTSP,999.1.1.1,,,\n"
    "Old,HTTP,http://192.168.1.50/v,,,\n"
)


def test_dialog_previews_rows_and_imports_only_the_ready_ones(app):
    dialog = CameraImportDialog(existing=[("Front", "HTTP", "192.168.1.50/v")])
    assert not dialog.import_button.isEnabled()
    dialog.load_text(GOOD)
    assert dialog.table.rowCount() == 4
    assert dialog.summary_label.text() == "2 ready · 1 need fixing · 1 already added or repeated"
    assert dialog.import_button.isEnabled() and dialog.import_button.text() == "Import 2 cameras"
    assert "not a valid IP" in dialog.table.item(2, 5).text()
    assert "Already added as Front" in dialog.table.item(3, 5).text()
    assert all("pw" not in dialog.table.item(r, c).text() for r in range(4) for c in range(6))  # passwords are never shown
    dialog.import_button.click()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert [v["name"] for v in dialog.rows_to_import] == ["Gate", "Hall"]
    assert dialog.rows_to_import[0]["password"] == "pw" and dialog.rows_to_import[0]["group_name"] == "Entrances"


def test_dialog_with_nothing_importable_stays_locked(app):
    dialog = CameraImportDialog()
    dialog.load_text("name,type,address\nBad,RTSP,999.1.1.1\n")
    assert not dialog.import_button.isEnabled()
    dialog.load_text("nonsense")
    assert "first row" in dialog.summary_label.text() and dialog.table.rowCount() == 0


def test_dialog_reads_files_and_reports_unreadable_ones(app, tmp_path):
    path = tmp_path / "cams.csv"
    path.write_bytes(GOOD.encode("cp1252"))
    dialog = CameraImportDialog()
    dialog.load_file(str(path))
    assert dialog.file_label.text() == "cams.csv" and dialog.import_button.text() == "Import 3 cameras"
    dialog.load_file(str(tmp_path / "missing.csv"))
    assert "could not be opened" in dialog.summary_label.text() and not dialog.import_button.isEnabled()


def test_template_can_be_saved_and_loaded_back(app, tmp_path):
    dialog = CameraImportDialog()
    path = tmp_path / "template.csv"
    assert dialog.write_template(str(path))
    assert path.read_bytes().decode("utf-8-sig") == template_csv()
    dialog.load_file(str(path))
    assert dialog.table.rowCount() == 0 and "example" in dialog.summary_label.text().lower()
    assert not dialog.write_template(str(tmp_path / "no" / "such" / "dir.csv"))


class _Repo:
    def __init__(self):
        self.cameras, self.notifications, self.removed = [], [], []

    def add_camera(self, name, source_type, address, ai_enabled=True):
        camera = CameraConfig(camera_id=f"CAM-{len(self.cameras) + 1:03d}", name=name, source_type=source_type,
                              source_address=address, ai_enabled=ai_enabled, created_at="")
        self.cameras.append(camera)
        return camera

    def set_camera_group(self, *_):
        pass

    def set_camera_threshold_offset(self, *_):
        pass

    def set_camera_tuning(self, camera_id, quiet_start, quiet_end, pre, post):
        return quiet_start, quiet_end, float(pre or 0.0), float(post or 0.0)

    def remove_camera(self, camera_id):
        self.removed.append(camera_id)

    def add_notification(self, kind, message):
        self.notifications.append((kind, message))


class _Vault:
    def __init__(self, fail_after=None):
        self.saved, self.fail_after = {}, fail_after

    def save(self, camera_id, credentials):
        if self.fail_after is not None and len(self.saved) >= self.fail_after:
            raise OSError("vault down")
        self.saved[camera_id] = credentials


class _Host(QWidget):
    _store_camera = MainWindow._store_camera
    _import_cameras = MainWindow._import_cameras
    _show_vault_unavailable = MainWindow._show_vault_unavailable

    def __init__(self, vault, manager="ok"):
        super().__init__()
        self.repository, self.vault = _Repo(), vault
        self.cameras, self.camera_stats, self._previous_camera_status = {}, {}, {}
        self.started, self.toasts, self.notices, self.synced = [], [], [], 0
        self.camera_manager = SimpleNamespace(start_camera=self.started.append) if manager else None
        self._in_app_overlay = SimpleNamespace(show_notice=lambda title, body: self.notices.append((title, body)))

    def _toast(self, message, ms=4000):
        self.toasts.append(message)

    def _sync_cameras(self):
        self.synced += 1

    def _set_camera_status(self, *args):
        pass


def _items(count):
    return [{"name": f"C{i}", "source_type": "RTSP", "source_address": f"rtsp://10.0.0.{i}:554/s", "username": "u",
             "password": "p", "group_name": "Z", "threshold_offset": 0.1, "ai_enabled": i % 2 == 0} for i in range(1, count + 1)]


def test_batch_import_adds_everything_with_one_toast_and_one_notification(app):
    host = _Host(_Vault())
    host._import_cameras(_items(30))
    assert len(host.cameras) == 30 and len(host.started) == 30 and len(host.vault.saved) == 30
    assert host.toasts == ["Imported 30 cameras. Connecting now."]
    assert host.repository.notifications == [("camera_added", "30 camera(s) imported from a CSV file.")]
    assert host.synced == 1
    camera = host.cameras["CAM-002"]
    assert camera.group_name == "Z" and camera.threshold_offset == 0.1 and camera.ai_enabled is True
    assert host.cameras["CAM-001"].ai_enabled is False
    assert QApplication.overrideCursor() is None


def test_batch_import_stops_when_the_vault_fails_and_says_how_far_it_got(app):
    host = _Host(_Vault(fail_after=3))
    host._import_cameras(_items(10))
    assert len(host.cameras) == 3 and host.repository.removed == ["CAM-004"] and not host.toasts
    assert len(host.notices) == 1 and "3 camera(s)" in host.notices[0][1] and "other 7" in host.notices[0][1]
    assert QApplication.overrideCursor() is None


def test_batch_import_before_the_engine_is_ready_still_saves_the_cameras(app):
    host = _Host(_Vault(), manager=None)
    host._import_cameras(_items(2))
    assert len(host.cameras) == 2 and host.started == []
    assert "once the AI engine has started" in host.toasts[0] and host.synced == 1


def test_single_add_still_reports_a_vault_failure(app):
    host = _Host(_Vault(fail_after=0))
    host._add_camera = MainWindow._add_camera.__get__(host)
    host._add_camera(_items(1)[0])
    assert not host.cameras and host.notices and "was not saved" in host.notices[0][1]
    with pytest.raises(CredentialVaultUnavailable):
        host._store_camera(_items(1)[0])
