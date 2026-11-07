import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from campusguard import storage
from campusguard.settings import AppSettings
from campusguard.ui.dashboard_page import DashboardPage

APP = QApplication.instance() or QApplication([])


def _page(tmp_path) -> DashboardPage:
    page = DashboardPage(storage.Repository(tmp_path / "campusguard.db"))
    page._settings = AppSettings()
    return page


def test_all_models_ready_is_active_not_partial(tmp_path):
    page = _page(tmp_path)
    for component in ("detector", "pose", "fight"):
        page.update_model_status("cam-1", component, "READY — model.pt")
    assert page._current_model_status() == ("ACTIVE", "good")


def test_one_missing_model_is_partial(tmp_path):
    page = _page(tmp_path)
    page.update_model_status("cam-1", "detector", "READY — yolo.pt")
    page.update_model_status("cam-1", "pose", "READY — pose.pt")
    page.update_model_status("cam-1", "fight", "MODEL NOT LOADED — file not found")
    assert page._current_model_status()[0] == "PARTIAL"


def test_second_camera_still_loading_does_not_mask_ready_first(tmp_path):
    page = _page(tmp_path)
    for component in ("detector", "pose", "fight"):
        page.update_model_status("cam-1", component, "READY — x")
    page.update_model_status("cam-2", "fight", "Loading model…")
    assert page._current_model_status() == ("ACTIVE", "good")



def test_dashboard_close_detaches_card_event_filters(tmp_path):
    page = _page(tmp_path)
    assert page._event_filter_targets
    page.close()
    assert page._closing
    assert not page._event_filter_targets
