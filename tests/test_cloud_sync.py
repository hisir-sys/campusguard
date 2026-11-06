"""App -> website sync: metadata only, cursor resume, failure isolation, real HTTP round trip."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from campusguard import auth_config
from campusguard.cloud_sync import CloudSync, build_payload
from campusguard.settings import CameraConfig
from campusguard.storage import Repository


def make_repo(tmp_path):
    return Repository(database_path=tmp_path / "a.db", footage_dir=tmp_path / "f")


def fight(repo, camera="CAM-001", severity="HIGH", confidence=0.9):
    cam = CameraConfig(camera, "Gate " + camera[-1], "RTSP", "rtsp://secret-address", True, "now")
    return repo.create_incident(cam, "Fight detected", confidence, severity, 0)


def test_payload_has_metadata_only(tmp_path):
    repo = make_repo(tmp_path)
    repo.add_camera("Gate 1", "RTSP", "rtsp://user:pw@10.0.0.5/stream")
    incident = fight(repo)
    repo.attach_incident_footage(incident["public_id"], str(tmp_path / "clip.mp4"))
    events, _ = repo.list_sync_events(0, 100)
    payload = build_payload(repo, "srv", "Server One", "1.2", {"online": 1}, events)
    text = json.dumps(payload)
    assert "rtsp://" not in text and "clip.mp4" not in text and "pw" not in payload["server"]
    assert payload["server"]["cameras_total"] == 1 and payload["server"]["cameras_online"] == 1
    assert payload["incidents"][0]["has_footage"] is True
    assert set(payload["incidents"][0]) == {"incident_id", "camera_name", "happened_at", "event",
                                            "confidence", "severity", "status", "has_footage", "seq"}


def test_cursor_resumes_and_only_changes_are_sent(tmp_path):
    repo = make_repo(tmp_path)
    sent = []
    sync = CloudSync(repo, "srv", "S", "1", lambda: "tok", tmp_path / "c.json", post=lambda u, p, t: sent.append(p) or 200)
    fight(repo)
    assert sync.sync_once() and len(sent[-1]["incidents"]) == 1
    sync.sync_once()
    assert sent[-1]["incidents"] == []                    # nothing new: only the server summary
    repo.update_incident_status(repo.list_incidents(1)[0]["public_id"], "RESOLVED")
    sync.sync_once()
    assert [i["status"] for i in sent[-1]["incidents"]] == ["RESOLVED"]
    again = CloudSync(repo, "srv", "S", "1", lambda: "tok", tmp_path / "c.json", post=lambda u, p, t: sent.append(p) or 200)
    again.sync_once()
    assert sent[-1]["incidents"] == []                    # restart keeps the cursor


def test_failure_does_not_advance_cursor_and_is_retried(tmp_path):
    repo = make_repo(tmp_path)
    results = iter([500, 200])
    sync = CloudSync(repo, "srv", "S", "1", lambda: "tok", tmp_path / "c.json", post=lambda u, p, t: next(results))
    fight(repo)
    with pytest.raises(RuntimeError):
        sync.sync_once()
    assert sync._cursor == 0
    assert sync.sync_once() and sync._cursor > 0


def test_not_signed_in_is_a_quiet_failure(tmp_path):
    repo = make_repo(tmp_path)
    sync = CloudSync(repo, "srv", "S", "1", lambda: "", tmp_path / "c.json", post=lambda u, p, t: 200)
    with pytest.raises(RuntimeError):
        sync.sync_once()


def test_real_http_round_trip(tmp_path, monkeypatch):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((self.path, self.headers["Authorization"], json.loads(body)))
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(b'{"ok":true}')
        def log_message(self, *args): pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setattr(auth_config, "WEBSITE_URL", f"http://127.0.0.1:{httpd.server_port}")
    repo = make_repo(tmp_path)
    fight(repo, severity="CRITICAL", confidence=0.97)
    try:
        assert CloudSync(repo, "srv", "Server One", "1", lambda: "abc", tmp_path / "c.json").sync_once()
    finally:
        httpd.shutdown()
    path, auth, body = received[0]
    assert path == "/api/sync-push" and auth == "Bearer abc"
    assert body["incidents"][0]["severity"] == "CRITICAL" and body["server"]["server_name"] == "Server One"
