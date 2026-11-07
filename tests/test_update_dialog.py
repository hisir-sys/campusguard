import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from campusguard import updater
from campusguard.ui.update_dialog import UpdateDialog

APP = QApplication.instance() or QApplication([])


def _release(body, assets=("CampusGuard-Setup.exe", "checksum.txt")):
    return {"body": body, "assets": [{"name": n, "browser_download_url": f"https://x/{n}"} for n in assets]}


def test_newer_release_offers_update():
    info = updater.select_update(_release("120"), "119")
    assert info and info["version"] == "120" and info["url"].endswith("CampusGuard-Setup.exe")


def test_same_older_or_incomplete_release_is_ignored():
    assert updater.select_update(_release("119"), "119") is None
    assert updater.select_update(_release("118"), "119") is None
    assert updater.select_update(_release("120", assets=("CampusGuard-Setup.exe",)), "119") is None
    assert updater.select_update(_release("garbage"), "119") is None


def test_dialog_buttons():
    dialog = UpdateDialog("120")
    assert dialog.now_button.text() == "Update now" and dialog.later_button.text() == "Not now"
    fired = []
    dialog.update_requested.connect(lambda: fired.append(1))
    dialog.now_button.click()
    assert fired == [1]
    dialog.show_downloading()
    assert not dialog.now_button.isEnabled() and not dialog.progress.isHidden()
    dialog.show_failed()
    assert dialog.now_button.isEnabled() and dialog.now_button.text() == "Try again"
    dialog.later_button.click()
    assert dialog.result() == 0


def test_done_dialog_has_single_continue_button():
    dialog = UpdateDialog("145", done=True)
    assert dialog.now_button.text() == "Continue"
    assert dialog.later_button.isHidden()
    dialog.now_button.click()
    assert dialog.result() == 1


def test_dev_build_reports_plainly_instead_of_failing():
    info, message = updater.check_for_update_detailed()
    assert info is None and "installed" in message.lower()


def test_update_marker_confirms_once(tmp_path, monkeypatch):
    monkeypatch.setattr("campusguard.storage.application_data_dir", lambda: tmp_path)
    monkeypatch.setattr(updater, "BUILD_VERSION", "143")
    updater.mark_update_started("145")
    assert updater.consume_update_marker() is None  # still on 143: not updated yet
    updater.mark_update_started("145")
    monkeypatch.setattr(updater, "BUILD_VERSION", "145")
    assert updater.consume_update_marker() == {"from": "143", "to": "145"}
    assert updater.consume_update_marker() is None  # shown only once


def test_manual_check_button_flow():
    from PySide6.QtWidgets import QApplication

    from campusguard.settings import AppSettings
    from campusguard.ui.settings_page import SettingsPage

    page = SettingsPage(AppSettings())
    seen = []
    page.update_check_requested.connect(lambda: seen.append(1))
    page.check_updates_button.click()
    assert seen == [1] and not page.check_updates_button.isEnabled()
    page.set_update_status("You are up to date (build 145).")
    assert page.check_updates_button.isEnabled() and "145" in page.update_status_label.text()
