from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QWidget

from campusguard.settings import CameraConfig, CameraStats
from campusguard.ui.cameras_v3 import CamerasPage
from campusguard.ui.footage_player import InlineClipPlayer


def _app():
    return QApplication.instance() or QApplication([])


def test_camera_card_shows_live_frames_and_opens(tmp_path):
    _app()
    page = CamerasPage()
    page.resize(1000, 600)
    page.show()
    camera = CameraConfig("C1", "Gate", "rtsp", "rtsp://x", True, "2026-01-01")
    page.sync_cameras([camera], {"C1": CameraStats(status="LIVE")})
    card = page._cards["C1"]
    assert not card.body.thumb.has_frame()
    image = QImage(320, 180, QImage.Format.Format_RGB32)
    image.fill(QColor("#336699"))
    page.update_frame("C1", image)
    assert card.body.thumb.has_frame()
    opened = []
    page.open_requested.connect(opened.append)
    card.body.open_requested.emit("C1")
    assert opened == ["C1"]
    page.update_camera_stats("C1", CameraStats(status="OFFLINE"))
    assert not card.body.thumb.has_frame()          # no stale picture for a dead camera


def test_inline_player_plays_pauses_and_seeks(tmp_path):
    _app()
    path = str(tmp_path / "clip.avi")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 10, (160, 90))
    for i in range(20):
        writer.write(np.full((90, 160, 3), i * 10, dtype=np.uint8))
    writer.release()
    host = QWidget()
    player = InlineClipPlayer(host)
    host.resize(500, 400)
    host.show()
    assert not player.play_button.isEnabled()
    assert player.load(path) and player.play_button.isEnabled()
    assert player.timeline.maximum() == 19
    player.toggle()
    assert player.timer.isActive() and player.play_button.text() == "Pause"
    player._next()
    player.toggle()
    assert not player.timer.isActive()
    player._seek(10)
    assert player.video.pixmap() is not None
    player.clear("none")
    assert not player.play_button.isEnabled() and player.capture is None
    assert not player.load(str(tmp_path / "missing.avi"))
