"""DPDP-driven controls: opt-in account sync, retention the school chooses, no surprise deletion."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from campusguard import cloud_sync
from campusguard.data_retention import apply_retention
from campusguard.server import config as server_config
from campusguard.settings import AppSettings
from campusguard.storage import Repository
from campusguard.ui import theme
from campusguard.ui.settings_page import SettingsPage
from campusguard.ui.sync_consent import SyncConsentDialog

APP = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _theme():
    theme.set_current("dark")
    yield
    theme.set_current("dark")


# ------------------------------------------------------------------ settings
def test_new_installs_and_upgrades_send_nothing_and_delete_nothing_by_default():
    defaults = AppSettings()
    assert defaults.cloud_sync == "ask"
    assert defaults.footage_retention_days == 0 and defaults.incident_retention_days == 0
    # an old settings row with none of the new keys must land on the safe defaults
    upgraded = AppSettings.from_dict({"theme": "light", "confidence_threshold": 0.7})
    assert upgraded.cloud_sync == "ask" and upgraded.footage_retention_days == 0


def test_bad_privacy_values_fall_back_safely():
    bad = AppSettings.from_dict({"cloud_sync": "yes please", "footage_retention_days": "abc", "incident_retention_days": -9})
    assert bad.cloud_sync == "ask" and bad.footage_retention_days == 0 and bad.incident_retention_days == 0
    capped = AppSettings.from_dict({"footage_retention_days": 10**9, "incident_retention_days": 10**9})
    assert capped.footage_retention_days == 3650 and capped.incident_retention_days == 36500


@pytest.mark.parametrize("choice,action", [("on", "start"), ("ask", "ask"), ("off", "skip"), ("", "skip"), ("true", "skip")])
def test_only_an_explicit_yes_starts_sync(choice, action):
    assert cloud_sync.consent_action(choice) == action


# ------------------------------------------------------------------ the notice
def test_notice_defaults_to_no_and_enter_is_not_a_yes():
    dialog = SyncConsentDialog()
    assert dialog.choice == "off"
    assert dialog.decline_button.isDefault() and not dialog.accept_button.isDefault()
    dialog.close()
    assert dialog.choice == "off"  # closing the window is not consent


def test_notice_buttons_set_the_choice():
    yes = SyncConsentDialog()
    yes.accept_button.click()
    assert yes.choice == "on" and yes.result() == SyncConsentDialog.DialogCode.Accepted
    no = SyncConsentDialog()
    no.decline_button.click()
    assert no.choice == "off" and no.result() == SyncConsentDialog.DialogCode.Rejected


def test_notice_lists_what_is_and_is_not_sent():
    dialog = SyncConsentDialog()
    from PySide6.QtWidgets import QLabel

    text = " ".join(label.text() for label in dialog.findChildren(QLabel))
    for must_say in ("camera name", "Whether a clip exists", "Video, images, file locations", "Clips stay on this PC"):
        assert must_say in text
    assert "Privacy Policy" in dialog.policy_link.text()


# ------------------------------------------------------------------ settings page
def _capture(page):
    seen = []
    page.settings_changed.connect(seen.append)
    return seen


def test_settings_page_reflects_and_records_the_sync_choice():
    page = SettingsPage(AppSettings())
    seen = _capture(page)
    assert not page.cloud_sync_toggle.isChecked()
    page.reconnect_toggle.toggle()  # an unrelated change must not decide anything about sync
    assert seen[-1].cloud_sync == "ask"
    page.cloud_sync_toggle.setChecked(True)
    assert seen[-1].cloud_sync == "on"
    page.cloud_sync_toggle.setChecked(False)  # withdrawing is one click
    assert seen[-1].cloud_sync == "off"


def test_first_run_answer_is_saved_through_the_page():
    page = SettingsPage(AppSettings())
    seen = _capture(page)
    page.set_cloud_sync_choice("off")
    assert seen[-1].cloud_sync == "off" and not page.cloud_sync_toggle.isChecked()
    page.set_cloud_sync_choice("on")
    assert seen[-1].cloud_sync == "on" and page.cloud_sync_toggle.isChecked()


def test_shortening_retention_needs_confirmation(monkeypatch):
    page = SettingsPage(AppSettings())
    seen = _capture(page)
    asked = []

    def decline(*args, **kwargs):
        asked.append(args[2])
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", decline)
    page.footage_retention_input.setCurrentIndex(page.footage_retention_input.findData(30))
    assert asked and "permanently delete" in asked[0] and "30 days" in asked[0]
    assert page.footage_retention_input.currentData() == 0  # reverted
    assert not seen, "declining must not save anything"

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    page.footage_retention_input.setCurrentIndex(page.footage_retention_input.findData(30))
    assert seen[-1].footage_retention_days == 30
    # lengthening needs no confirmation because it deletes nothing
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: pytest.fail("no prompt expected"))
    page.footage_retention_input.setCurrentIndex(page.footage_retention_input.findData(90))
    assert seen[-1].footage_retention_days == 90
    page.footage_retention_input.setCurrentIndex(page.footage_retention_input.findData(0))
    assert seen[-1].footage_retention_days == 0


def test_reset_to_defaults_does_not_touch_privacy_choices():
    page = SettingsPage(AppSettings(cloud_sync="on", footage_retention_days=30))
    seen = _capture(page)
    page._reset_defaults()
    assert seen[-1].cloud_sync == "on" and seen[-1].footage_retention_days == 30


# ------------------------------------------------------------------ retention
def _clip(directory, name, age_days):
    path = directory / name
    path.write_bytes(b"x" * 10)
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))
    return path


def test_retention_keeps_everything_when_no_period_was_chosen(tmp_path):
    repo = Repository(tmp_path / "db.sqlite3", footage_dir=tmp_path / "clips")
    old = _clip(repo.footage_dir, "FIGHT_old.mp4", 900)
    assert apply_retention(repo, 0, 0) == {"clips_removed": 0, "incidents_removed": 0}
    assert old.exists()


def test_retention_removes_only_items_older_than_the_chosen_period(tmp_path):
    repo = Repository(tmp_path / "db.sqlite3", footage_dir=tmp_path / "clips")
    old = _clip(repo.footage_dir, "FIGHT_old.mp4", 45)
    fresh = _clip(repo.footage_dir, "FIGHT_new.mp4", 3)
    first = repo.add_camera("Gate", "RTSP", "rtsp://127.0.0.1:9/a", False)
    second = repo.add_camera("Canteen", "RTSP", "rtsp://127.0.0.1:9/b", False)
    for camera in repo.list_cameras():
        repo.create_incident(camera, "FIGHT DETECTED", 0.9, "HIGH", 0)
    long_ago = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat(timespec="seconds")
    with repo._lock, repo._connection() as connection:
        connection.execute("UPDATE incidents SET happened_at = ? WHERE rowid = (SELECT MIN(rowid) FROM incidents)", (long_ago,))

    result = apply_retention(repo, footage_days=30, incident_days=365)
    assert result == {"clips_removed": 1, "incidents_removed": 1}
    assert fresh.exists() and not old.exists()
    assert len(repo.list_incidents()) == 1
    _ = (first, second)


# ------------------------------------------------------------------ server mode
def test_server_sync_is_off_until_an_administrator_turns_it_on():
    assert server_config.ServerConfig().cloud_sync is False
    assert server_config.normalise({}).cloud_sync is False
    assert server_config.normalise({"cloud_sync": True}).cloud_sync is True
    assert server_config.normalise({"cloud_sync": "true"}).cloud_sync is True
    assert server_config.normalise({"cloud_sync": "false"}).cloud_sync is False
    assert server_config.normalise({"cloud_sync": "off"}).cloud_sync is False
