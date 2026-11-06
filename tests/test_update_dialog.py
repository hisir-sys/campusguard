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
