from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from campusguard.settings import CameraConfig, CameraStats
from campusguard.storage import Repository
from campusguard.ui.floor_map import FloorMapPage


def _camera(cid: str) -> CameraConfig:
    return CameraConfig(cid, f"Cam {cid}", "usb", "0", True, "2026-01-01")


def test_pins_survive_plan_and_camera_removal(tmp_path):
    repo = Repository(tmp_path / "t.db", tmp_path / "f")
    plan = repo.add_floor_plan("Ground", str(tmp_path / "a.png"))
    repo.set_camera_pin("C1", plan, 0.25, 0.5)
    repo.set_camera_pin("C1", plan, 2.0, -1.0)                  # clamped, and replaces the old pin
    assert repo.list_camera_pins() == {"C1": (plan, 1.0, 0.0)}
    repo.set_camera_pin("C2", plan, 0.1, 0.1)
    repo.remove_camera_pin("C2")
    assert "C2" not in repo.list_camera_pins()
    repo.remove_floor_plan(plan)
    assert repo.list_floor_plans() == [] and repo.list_camera_pins() == {}


def test_page_places_moves_and_unpins(tmp_path):
    app = QApplication.instance() or QApplication([])
    repo = Repository(tmp_path / "t.db", tmp_path / "f")
    image = QImage(400, 300, QImage.Format.Format_RGB32)
    image.fill(QColor("#cccccc"))
    source = tmp_path / "ground_floor.png"
    image.save(str(source))
    page = FloorMapPage(repo)
    page.resize(900, 560)
    page.show()
    page.sync_cameras([_camera("C1"), _camera("C2")], {"C1": CameraStats(status="LIVE")})
    assert "Import a floor plan" in page.tray_hint.text()
    plan_id = page.import_plan(str(source))
    assert plan_id and page.canvas.pixmap is not None
    assert [p["name"] for p in repo.list_floor_plans()] == ["Ground Floor"]
    page.canvas.pin_placed.emit("C1", 0.4, 0.6)
    assert repo.list_camera_pins()["C1"] == (plan_id, 0.4, 0.6)
    assert "1 of 2 cameras placed" in page.summary.text()
    # a new open incident on C1 makes its pin pulse
    assert repo.create_incident(_camera("C1"), "Fight detected", 0.93, "HIGH", 0) is not None
    page.refresh()
    assert page.canvas.hot == {"C1"} and "1 alerting" in page.summary.text()
    page.canvas.pin_removed.emit("C1")
    assert repo.list_camera_pins() == {}
    page.deleteLater()
