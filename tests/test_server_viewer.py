from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from campusguard.ui.server_viewer import ServerViewerPage


@pytest.fixture()
def app():
    return QApplication.instance() or QApplication([])


def fixture_camera(index: int) -> dict:
    return {
        "camera_id": f"TEST-CAM-{index:03d}",
        "name": f"Layout fixture {index:03d}",
        "health": "connecting",
        "status": "CONNECTING",
        "message": "Fixture only",
        "fps": None,
        "resolution": "N/A",
    }


def test_viewer_handles_zero_five_and_120_camera_cards(app):
    page = ServerViewerPage(lambda: (_ for _ in ()).throw(AssertionError("Network must not run in this test.")))
    page._closing = True
    for count in (0, 5, 120):
        page._sync_camera_cards([fixture_camera(i + 1) for i in range(count)])
        assert len(page._cards) == count
        assert page.empty_cameras_label.isHidden() is (count != 0)
        app.processEvents()
    page.shutdown()
    page.close()


def test_incident_and_alert_rows_both_offer_status_actions(app):
    page = ServerViewerPage(lambda: (_ for _ in ()).throw(AssertionError("Network must not run in this test.")))
    page._closing = True
    row = {
        "public_id": "INC-00001",
        "camera_name": "Hall",
        "event": "FIGHT DETECTED",
        "confidence": 0.9,
        "severity": "HIGH",
        "status": "NEW",
        "has_footage": False,
    }
    page._populate_table(page.incidents_table, [row], allow_status_actions=True)
    page._populate_table(page.alerts_table, [row], allow_status_actions=True)
    for table in (page.incidents_table, page.alerts_table):
        action_widget = table.cellWidget(0, 6)
        assert action_widget is not None
        selector = action_widget.findChild(__import__("PySide6.QtWidgets", fromlist=["QComboBox"]).QComboBox)
        assert selector is not None
        assert [selector.itemText(i) for i in range(selector.count())] == [
            "Confirm", "Dismiss", "False alarm", "Resolve"
        ]
    page.shutdown()
    page.close()


def test_viewer_removes_stale_cards_without_rebuilding_existing_ones(app):
    page = ServerViewerPage(lambda: (_ for _ in ()).throw(AssertionError("Network must not run in this test.")))
    page._closing = True
    page._sync_camera_cards([fixture_camera(i + 1) for i in range(5)])
    first = page._cards["TEST-CAM-001"]
    page._sync_camera_cards([fixture_camera(i + 1) for i in range(3)])
    assert len(page._cards) == 3
    assert page._cards["TEST-CAM-001"] is first
    assert "TEST-CAM-005" not in page._cards
    page.shutdown()
    page.close()
