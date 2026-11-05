"""Phase 6C: School tab, source labels and the remote-footage notice (real servers, offscreen Qt)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from campusguard.server.api import ApiServer
from campusguard.server.client import RemoteServerClient
from campusguard.ui.server_viewer import ServerViewerPage
from tests.test_server_core import FakeBackend
from tests.test_sync import Node, SyncBackend


class _Backend(FakeBackend):
    """FakeBackend + real sync endpoints + a real incident list, like a live server."""

    def __init__(self, root, node: Node):
        super().__init__(root)
        self.node = node
        self.sync = node.facade

    def status(self): return {"version": "t", "cameras": {}}
    def list_incidents(self, after_id, limit):
        return [{"public_id": r["public_id"], "camera_name": r["camera_name"], "event": r["event"],
                 "confidence": r["confidence"], "severity": r["severity"], "status": r["status"],
                 "has_footage": False} for r in self.node.repo.list_incidents(limit)]
    def sync_identity(self): return self.sync.identity()
    def sync_events(self, since, limit): return self.sync.events(since, limit)
    def sync_overview(self): return self.sync.overview()
    def sync_alerts(self, limit): return self.sync.remote_alerts(limit)


class _Tokens:
    def __init__(self): self.saved = {}
    def load_peer_token(self, address): return self.saved.get(address, "")
    def save_peer_token(self, address, token): self.saved[address] = token


def _pump(app, seconds=3.0, until=lambda: False):
    end = time.time() + seconds
    while time.time() < end and not until():
        app.processEvents()
        time.sleep(0.03)


@pytest.fixture
def pair(tmp_path):
    one, two = Node(tmp_path, "one"), Node(tmp_path, "two")
    one.api.stop(); two.api.stop()
    one.api = ApiServer("127.0.0.1", 0, one.token, _Backend(tmp_path, one)); one.api.start()
    two.api = ApiServer("127.0.0.1", 0, two.token, _Backend(tmp_path, two)); two.api.start()
    two.connect(one)
    yield one, two
    one.close(); two.close()


def test_school_tab_shows_source_server_camera_and_totals(pair):
    one, two = pair
    app = QApplication.instance() or QApplication([])
    one.fight("CAM-24", "HIGH", 0.91)
    two.fight("CAM-05", "MEDIUM", 0.7)
    two.sync.sync_once()
    page = ServerViewerPage(lambda: RemoteServerClient(two.address, two.token, retries=0))
    page.resize(1100, 700); page.show(); page.refresh()
    _pump(app, until=lambda: page.remote_table.rowCount() == 1)
    assert "School-wide fight alerts: 2" in page.school_summary.text()
    assert "1 detected by two" in page.school_detail.text() and "1 reported by other servers" in page.school_detail.text()
    assert page.servers_table.item(0, 0).text() == "one" and "online" in page.servers_table.item(0, 2).text()
    assert page.remote_table.item(0, 1).text() == "one · Camera 24"
    page.shutdown(); page.close()


def test_remote_footage_notice_never_plays_a_local_copy(pair, monkeypatch):
    one, two = pair
    app = QApplication.instance() or QApplication([])
    inc = one.fight("CAM-24")
    one.repo.attach_incident_footage(inc["public_id"], "/footage/clip.mp4")
    two.sync.sync_once()
    page = ServerViewerPage(lambda: RemoteServerClient(two.address, two.token, retries=0))
    page.show(); page.refresh()
    _pump(app, until=lambda: page.remote_table.rowCount() == 1)
    button = page.remote_table.cellWidget(0, 6)
    assert button is not None and button.text() == "View footage"
    seen = {}

    def fake_exec(box):
        seen["title"], seen["text"], seen["info"] = box.windowTitle(), box.text(), box.informativeText()
        seen["buttons"] = [b.text() for b in box.buttons()]
        return 0

    played = []
    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(page, "_play_clip", lambda pid: played.append(pid))
    button.click()
    assert seen["title"] == "Footage is stored on another server"
    assert "not stored on the current machine" in seen["text"] and "Open one to review" in seen["text"]
    assert one.address in seen["info"] and "Go to one" in seen["buttons"]
    assert played == [] and page._player is None
    page.shutdown(); page.close()


def test_go_to_server_switches_view_and_can_return(pair, monkeypatch):
    one, two = pair
    app = QApplication.instance() or QApplication([])
    inc = one.fight("CAM-24")
    two.sync.sync_once()
    tokens = _Tokens()
    page = ServerViewerPage(lambda: RemoteServerClient(two.address, two.token, retries=0), peer_tokens=tokens)
    from PySide6.QtWidgets import QInputDialog
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: (one.token, True)))
    page.show(); page.refresh()
    _pump(app, until=lambda: page.remote_table.rowCount() == 1)
    assert page.go_to_server("one", one.address, inc["public_id"])
    assert page.viewing_banner.isVisibleTo(page) and "one" in page.viewing_label.text()
    _pump(app, until=lambda: tokens.saved)
    assert tokens.saved == {one.address: one.token}                     # remembered after it worked
    _pump(app, until=lambda: page.incidents_table.rowCount() == 1)
    assert page.incidents_table.item(0, 0).text() == inc["public_id"]
    assert "School-wide fight alerts: 1" in page.school_summary.text()     # server one's own view
    page.leave_other_server()
    _pump(app, until=lambda: page.remote_table.rowCount() == 1)
    assert not page.viewing_banner.isVisibleTo(page) and page._override is None
    page.shutdown(); page.close()


def test_go_to_server_declined_token_changes_nothing(pair, monkeypatch):
    one, two = pair
    QApplication.instance() or QApplication([])
    page = ServerViewerPage(lambda: RemoteServerClient(two.address, two.token, retries=0), peer_tokens=_Tokens())
    from PySide6.QtWidgets import QInputDialog
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))
    assert page.go_to_server("one", one.address) is False and page._override is None
    page.shutdown(); page.close()


