"""Real ApiServer <-> real RemoteServerClient <-> real ServerViewerPage (offscreen)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import time

import pytest
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from campusguard.server.api import ApiServer
from campusguard.server.client import RemoteServerClient, ServerConnectionError
from campusguard.ui.server_viewer import ServerViewerPage
from tests.test_server_core import FakeBackend, TOKEN


def _jpeg() -> bytes:
    image = QImage(64, 36, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    buf = QBuffer(); buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "JPEG")
    return bytes(buf.data())


@pytest.fixture
def live(tmp_path):
    backend = FakeBackend(tmp_path)
    backend.snapshot_payload = _jpeg()
    server = ApiServer("127.0.0.1", 0, TOKEN, backend)
    server.start()
    yield server, backend
    server.stop()


def client_for(server, token=TOKEN):
    return RemoteServerClient(f"http://127.0.0.1:{server.port}", token, timeout=3.0, retries=0)


def test_client_against_real_server(live, tmp_path):
    server, backend = live
    c = client_for(server)
    assert c.test_connection()["version"] == "t"
    assert c.list_cameras()[0]["camera_id"] == "CAM-001"
    assert c.snapshot("CAM-001")[:2] == b"\xff\xd8"
    c.stop_snapshot("CAM-001")
    assert ("snapshot_watch", "CAM-001", False) in backend.calls
    c.set_incident_status("INC-00001", "RESOLVED")
    assert ("status", "INC-00001", "RESOLVED") in backend.calls
    out = c.stream_clip_to_file("INC-00001", tmp_path / "c.mp4")
    assert out.read_bytes() == backend.clip.read_bytes()
    with pytest.raises(ServerConnectionError):
        client_for(server, "x" * 20).test_connection()
    with pytest.raises(ServerConnectionError):
        c.snapshot("CAM-999")


def test_viewer_page_populates_from_real_server(live):
    server, _ = live
    app = QApplication.instance() or QApplication([])
    page = ServerViewerPage(lambda: client_for(server))
    page.resize(1100, 700)
    page.show()
    page.refresh()
    for _ in range(100):
        app.processEvents(); time.sleep(0.05)
    assert "CAM-001" in page._cards
    text = page.connection_status.text()
    assert "fail" not in text.lower() and "denied" not in text.lower(), text
    page.shutdown()
    page.close()
    page.deleteLater()
    for _ in range(10):
        app.processEvents()
        time.sleep(0.02)
