from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from campusguard.server.client import RemoteServerClient, ServerConnectionError


TOKEN = "t" * 32


class FakeServerHandler(BaseHTTPRequestHandler):
    token = TOKEN
    online = True
    incident_status = "NEW"
    clip_bytes = b"fake-mp4-stream"

    def log_message(self, *_args):
        pass

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        if self.headers.get("Authorization") != f"Bearer {self.token}":
            self._json(401, {"error": "bad token"})
            return False
        if not self.online:
            self._json(503, {"error": "server temporarily unavailable"})
            return False
        return True

    def do_GET(self):
        if not self._authorized():
            return
        if self.path == "/api/v1/status":
            self._json(200, {"version": "test", "uptime_seconds": 4, "cameras": {"total": 1, "ok": 0, "stalled": 1, "offline": 0, "connecting": 0}})
        elif self.path == "/api/v1/cameras":
            self._json(200, {"cameras": [{"camera_id": "CAM-1", "name": "Test camera", "health": "stalled"}]})
        elif self.path == "/api/v1/incidents?limit=200":
            self._json(200, {"incidents": [{"public_id": "INC-1", "status": self.incident_status}]})
        elif self.path == "/api/v1/alerts?limit=200":
            self._json(200, {"alerts": []})
        elif self.path == "/api/v1/cameras/CAM-1/snapshot":
            body = b"\\xff\\xd8fake-jpeg\\xff\\xd9"
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/v1/incidents/INC-1/clip":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(self.clip_bytes)))
            self.end_headers()
            self.wfile.write(self.clip_bytes)
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._authorized():
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if self.path == "/api/v1/incidents/INC-1/status":
            payload = json.loads(body)
            type(self).incident_status = payload.get("status", "NEW")
            self._json(200, {"public_id": "INC-1", "status": self.incident_status})
        elif self.path == "/api/v1/cameras/import":
            if b"name,address" not in body or b"rtsp://" not in body:
                self._json(400, {"error": "CSV import row 2: invalid stream address"})
                return
            self._json(200, {"imported": 1, "errors": []})
        else:
            self._json(404, {"error": "not found"})

@pytest.fixture()
def fake_server():
    FakeServerHandler.online = True
    FakeServerHandler.incident_status = "NEW"
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeServerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", server
    server.shutdown()
    thread.join(timeout=3)
    server.server_close()


def test_address_validation_and_token_requirement():
    with pytest.raises(ServerConnectionError, match="valid server address"):
        RemoteServerClient("ftp://bad", TOKEN)
    with pytest.raises(ServerConnectionError, match="token"):
        RemoteServerClient("http://127.0.0.1:8765", "")
    with pytest.raises(ServerConnectionError, match="valid server address"):
        RemoteServerClient("https://user:pass@example.com", TOKEN)


def test_client_connects_and_rejects_bad_token(fake_server):
    address, _server = fake_server
    assert RemoteServerClient(address, TOKEN).test_connection()["version"] == "test"
    with pytest.raises(ServerConnectionError, match="token is wrong"):
        RemoteServerClient(address, "wrong-token", retries=0).test_connection()


def test_server_down_is_reported_without_hanging():
    import socket

    # Reserve an ephemeral port, then release it to create a reliably unused port
    # on Windows runners (port 1 may be reserved or intercepted by local services).
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        unused_port = probe.getsockname()[1]
    client = RemoteServerClient(f"http://127.0.0.1:{unused_port}", TOKEN, timeout=0.5, retries=0)
    with pytest.raises(ServerConnectionError, match="unreachable|timed out"):
        client.test_connection()


def test_client_recovers_after_server_returns(fake_server):
    address, _server = fake_server
    FakeServerHandler.online = False
    client = RemoteServerClient(address, TOKEN, retries=0)
    try:
        with pytest.raises(ServerConnectionError, match="temporarily unavailable"):
            client.test_connection()
        FakeServerHandler.online = True
        assert client.test_connection()["version"] == "test"
    finally:
        FakeServerHandler.online = True


def test_client_lists_stalled_camera_and_changes_incident_status(fake_server):
    address, _server = fake_server
    client = RemoteServerClient(address, TOKEN, retries=0)
    cameras = client.list_cameras()
    assert cameras[0]["health"] == "stalled"
    changed = client.set_incident_status("INC-1", "CONFIRMED")
    assert changed == {"public_id": "INC-1", "status": "CONFIRMED"}
    assert client.list_incidents()[0]["status"] == "CONFIRMED"


def test_client_streams_clip_and_reports_csv_import_errors(fake_server, tmp_path):
    address, _server = fake_server
    client = RemoteServerClient(address, TOKEN, retries=0)
    destination = tmp_path / "incident.mp4"
    assert client.stream_clip_to_file("INC-1", destination) == destination
    assert destination.read_bytes() == FakeServerHandler.clip_bytes
    assert client.import_cameras(b"name,address\nOffice,rtsp://camera/stream\n")["imported"] == 1
    with pytest.raises(ServerConnectionError, match="invalid stream address"):
        client.import_cameras(b"name,address\nOffice,not-a-stream\n")
