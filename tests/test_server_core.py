import http.client
import json
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest

from campusguard.server.api import ApiError, ApiServer, FAILED_AUTH_LIMIT
from campusguard.server.cli import build_task_xml
from campusguard.server.config import load_config, normalise
from campusguard.server.csv_import import parse_cameras_csv
from campusguard.server.health import HealthTracker
from campusguard.server.recorder import IncidentRecorder, severity_for
from campusguard.server.retention import enforce_disk_budget, purge_old_footage

TOKEN = "t" * 32


# ---------------------------------------------------------------- config
def test_config_creates_token_once_and_clamps_values(tmp_path):
    first = load_config(tmp_path)
    assert len(first.token) >= 32 and first.host == "127.0.0.1" and first.port == 8765
    assert load_config(tmp_path).token == first.token
    (tmp_path / "server.json").write_text(json.dumps({**json.loads((tmp_path / "server.json").read_text()), "port": 99999, "retention_days_footage": -5, "host": " 0.0.0.0 "}))
    again = load_config(tmp_path)
    assert again.port == 65535 and again.retention_days_footage == 1 and again.host == "0.0.0.0"
    assert again.token == first.token


def test_config_survives_garbage_file(tmp_path):
    (tmp_path / "server.json").write_text("{ not json")
    assert len(load_config(tmp_path).token) >= 32
    assert normalise({"port": "abc"}).port == 8765


# ---------------------------------------------------------------- health
def test_health_states_and_stall_detection():
    clock = [100.0]
    tracker = HealthTracker(clock=lambda: clock[0])
    tracker.set_status("CAM-001", "CONNECTING")
    assert tracker.snapshot()["CAM-001"]["health"] == "connecting"
    tracker.set_status("CAM-001", "LIVE")
    tracker.set_stats("CAM-001", 14.97, "640x360")
    assert tracker.snapshot()["CAM-001"]["health"] == "ok"
    assert tracker.snapshot()["CAM-001"]["fps"] == 15.0
    clock[0] += 16
    snap = tracker.snapshot()["CAM-001"]
    assert snap["health"] == "stalled" and snap["seconds_since_frame"] == 16.0
    tracker.set_stats("CAM-001", 15, "640x360")
    assert tracker.snapshot()["CAM-001"]["health"] == "ok"
    tracker.set_status("CAM-001", "OFFLINE", "lost")
    assert tracker.snapshot()["CAM-001"]["health"] == "offline"
    tracker.set_status("CAM-002", "LIVE")                      # LIVE but never any frame stats
    clock[0] += 20
    assert tracker.snapshot()["CAM-002"]["health"] == "stalled"
    assert tracker.summary() == {"ok": 0, "stalled": 1, "offline": 1, "connecting": 0, "total": 2}
    tracker.remove("CAM-001")
    assert "CAM-001" not in tracker.snapshot()


# ---------------------------------------------------------------- recorder
def test_severity_bands_match_desktop_app():
    assert severity_for(0.70) == "LOW" and severity_for(0.85) == "MEDIUM"
    assert severity_for(0.95) == "HIGH" and severity_for(97) == "HIGH" and severity_for(50) == "LOW"


def test_recorder_cooldown_and_footage_pairing():
    created = []

    class Repo:
        def create_incident(self, camera, event, confidence, severity, cooldown):
            if created and cooldown:
                return None
            row = {"public_id": f"INC-{len(created) + 1:05d}", "severity": severity}
            created.append(row)
            return row

        def attach_incident_footage(self, public_id, path):
            created.append(("footage", public_id, path))

    recorder = IncidentRecorder(Repo())
    camera = SimpleNamespace(camera_id="CAM-001", name="Gate")
    assert recorder.attach_footage("CAM-001", "x.mp4") is None             # nothing pending
    assert recorder.record_event(camera, "FIGHT DETECTED", 0.9, 0)["public_id"] == "INC-00001"
    assert recorder.record_event(camera, "FIGHT DETECTED", 0.9, 45) is None  # cooldown
    assert recorder.attach_footage("CAM-001", "a.mp4") == "INC-00001"
    assert recorder.attach_footage("CAM-001", "b.mp4") is None             # consumed once
    assert created[-1] == ("footage", "INC-00001", "a.mp4")


# ---------------------------------------------------------------- retention
def make_clip(directory: Path, name: str, size: int, age_days: float):
    path = directory / name
    path.write_bytes(b"x" * size)
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))
    return path


def test_purge_old_footage(tmp_path):
    old = make_clip(tmp_path, "FIGHT_old.mp4", 10, 40)
    new = make_clip(tmp_path, "FIGHT_new.mp4", 10, 2)
    other = tmp_path / "keep.txt"; other.write_text("x")
    removed = purge_old_footage(tmp_path, 30)
    assert removed == [old] and new.exists() and other.exists() and not old.exists()


def test_disk_budget_removes_oldest_first(tmp_path):
    a = make_clip(tmp_path, "a.mp4", 100, 5)
    b = make_clip(tmp_path, "b.mp4", 100, 3)
    c = make_clip(tmp_path, "c.mp4", 100, 1)
    removed = enforce_disk_budget(tmp_path, 150)
    assert removed == [a, b] and c.exists()
    assert enforce_disk_budget(tmp_path, 1000) == []
    assert enforce_disk_budget(tmp_path / "missing", 1) == []


# ---------------------------------------------------------------- csv import
CSV = """Name,Type,Address,Username,Password,AI
Gate 1,RTSP,rtsp://10.0.0.11/stream2,admin,s3cret,yes
Corridor A,rtsp,rtsp://10.0.0.12/stream2,,,no
,RTSP,rtsp://10.0.0.13/x,,,
Bad type,FTP,ftp://x,,,
Dup,RTSP,rtsp://10.0.0.11/stream2,,,
Creds in url,RTSP,rtsp://u:p@10.0.0.14/x,,,
USB cam,USB,2,,,
USB with login,USB,1,bob,pw,
Bad rtsp,RTSP,http://10.0.0.15/x,,,
"""


def test_csv_import_accepts_good_rows_and_explains_bad_ones():
    plan = parse_cameras_csv(CSV, existing={("RTSP", "rtsp://10.0.0.99/x")})
    assert [c.name for c in plan.valid] == ["Gate 1", "Corridor A", "USB cam"]
    gate = plan.valid[0]
    assert gate.credentials.username == "admin" and gate.credentials.password == "s3cret" and gate.ai_enabled
    assert plan.valid[1].source_type == "RTSP" and plan.valid[1].ai_enabled is False
    rows = {e["row"]: e["error"] for e in plan.errors}
    assert set(rows) == {4, 5, 6, 7, 9, 10}
    assert "name" in rows[4].lower() and "Unknown type" in rows[5] and "already configured" in rows[6]
    assert "credentials" in rows[7].lower() and "username" in rows[9].lower()


def test_csv_import_existing_duplicates_header_and_limits():
    assert parse_cameras_csv("").errors[0]["row"] == 1
    assert "header" in parse_cameras_csv("foo,bar\n1,2\n").errors[0]["error"]
    dup = parse_cameras_csv("name,address\nA,rtsp://h/x\n", existing={("RTSP", "rtsp://h/x")})
    assert not dup.valid and "already configured" in dup.errors[0]["error"]
    bom = parse_cameras_csv("\ufeffname;address\nA;rtsp://h/y\n")
    assert [c.address for c in bom.valid] == ["rtsp://h/y"]
    many = "name,address\n" + "".join(f"c{i},rtsp://h/{i}\n" for i in range(1001))
    assert "Too many" in parse_cameras_csv(many).errors[0]["error"]
    long_name = parse_cameras_csv(f"name,address\n{'x' * 81},rtsp://h/z\n")
    assert "80" in long_name.errors[0]["error"]
    same_in_file = parse_cameras_csv("name,address\nA,rtsp://h/q\nB,RTSP://H/q\n")
    assert len(same_in_file.valid) == 1 and len(same_in_file.errors) == 1


# ---------------------------------------------------------------- scheduled task
def test_task_xml_is_well_formed_and_escapes():
    xml = build_task_xml(r"C:\Program Files\CampusGuard\CampusGuard.exe", "--server", r"SCHOOL\a&b")
    root = ET.fromstring(xml.replace('encoding="UTF-16"', ""))
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    assert root.find(".//t:Exec/t:Command", ns).text.endswith("CampusGuard.exe")
    assert root.find(".//t:Exec/t:Arguments", ns).text == "--server"
    assert root.find(".//t:Principal/t:UserId", ns).text == r"SCHOOL\a&b"
    assert root.find(".//t:RestartOnFailure/t:Count", ns).text == "999"
    assert root.find(".//t:BootTrigger", ns) is not None


# ---------------------------------------------------------------- HTTP API
class FakeBackend:
    def __init__(self, root: Path):
        self.root = root
        self.calls = []
        self.snapshot_payload = b"jpeg-bytes"
        self.clip = root / "clip.mp4"
        self.clip.write_bytes(bytes(range(256)) * 4)       # 1024 bytes

    def status(self): return {"version": "t"}
    def list_cameras(self): return [{"camera_id": "CAM-001"}]
    def validate_camera_snapshot(self, camera_id):
        if camera_id != "CAM-001": raise ApiError(404, "Unknown camera.")
    def set_camera_snapshot_enabled(self, camera_id, enabled):
        if camera_id != "CAM-001": raise ApiError(404, "Unknown camera.")
        self.calls.append(("snapshot_watch", camera_id, enabled))
    def camera_snapshot(self, camera_id):
        if camera_id != "CAM-001": raise ApiError(404, "Unknown camera.")
        return self.snapshot_payload
    def add_camera(self, spec):
        if not spec.get("name"): raise ApiError(400, "Camera name is missing.")
        self.calls.append(("add", spec)); return {"camera_id": "CAM-002", **spec}
    def import_cameras(self, text): self.calls.append(("import", text)); return {"added": 1, "errors": []}
    def remove_camera(self, camera_id):
        if camera_id == "CAM-404": raise ApiError(404, "Unknown camera.")
        self.calls.append(("remove", camera_id))
    def set_camera_ai(self, camera_id, enabled): self.calls.append(("ai", camera_id, enabled))
    def reconnect_camera(self, camera_id): self.calls.append(("reconnect", camera_id))
    def list_incidents(self, after_id, limit): return [{"after": after_id, "limit": limit}]
    def list_alerts(self, limit): return [{"limit": limit}]
    def set_incident_status(self, public_id, status): self.calls.append(("status", public_id, status))
    def footage_path(self, public_id): return self.clip if public_id == "INC-00001" else None


@pytest.fixture()
def api(tmp_path):
    backend = FakeBackend(tmp_path)
    server = ApiServer("127.0.0.1", 0, TOKEN, backend)
    server.start()
    yield server, backend
    server.stop()


def request(server, method, path, body=None, token=TOKEN, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    sent = {"Authorization": f"Bearer {token}"} if token else {}
    sent.update(headers or {})
    payload = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    connection.request(method, path, body=payload, headers=sent)
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response.status, response, data


def test_health_is_open_everything_else_needs_the_token(api):
    server, _ = api
    assert request(server, "GET", "/health", token=None)[0] == 200
    for token in (None, "wrong", TOKEN[:-1]):
        assert request(server, "GET", "/api/v1/status", token=token)[0] == 401
    assert request(server, "GET", "/api/v1/status")[0] == 200
    assert request(server, "GET", f"/api/v1/status?token={TOKEN}", token=None)[0] == 401   # never via URL
    assert request(server, "GET", "/nope")[0] == 404
    assert request(server, "GET", "/api/v1/nope")[0] == 404


def test_repeated_bad_tokens_are_rate_limited(api):
    server, _ = api
    codes = [request(server, "GET", "/api/v1/status", token="bad")[0] for _ in range(FAILED_AUTH_LIMIT + 2)]
    assert codes[0] == 401 and codes[-1] == 429
    assert request(server, "GET", "/api/v1/status")[0] == 429      # even the right token waits


def test_camera_routes(api):
    server, backend = api
    assert json.loads(request(server, "GET", "/api/v1/cameras")[2]) == {"cameras": [{"camera_id": "CAM-001"}]}
    status, _, data = request(server, "POST", "/api/v1/cameras", {"name": "Gate", "address": "rtsp://x/y"})
    assert status == 201 and json.loads(data)["camera_id"] == "CAM-002"
    status, _, data = request(server, "POST", "/api/v1/cameras", {"address": "rtsp://x/y"})
    assert status == 400 and "name" in json.loads(data)["error"]
    assert request(server, "POST", "/api/v1/cameras", b"not json")[0] == 400
    assert request(server, "POST", "/api/v1/cameras", b"[1,2]")[0] == 400
    assert request(server, "POST", "/api/v1/cameras/import", b"name,address\nA,rtsp://h/x\n")[0] == 200
    assert backend.calls[-1] == ("import", "name,address\nA,rtsp://h/x\n")
    assert request(server, "DELETE", "/api/v1/cameras/CAM-001")[0] == 200
    assert request(server, "DELETE", "/api/v1/cameras/CAM-404")[0] == 404
    assert request(server, "POST", "/api/v1/cameras/CAM-001/ai", {"enabled": False})[0] == 200
    assert backend.calls[-1] == ("ai", "CAM-001", False)
    assert request(server, "POST", "/api/v1/cameras/CAM-001/ai", {"enabled": "yes"})[0] == 400
    assert request(server, "POST", "/api/v1/cameras/CAM-001/reconnect")[0] == 200
    assert request(server, "GET", "/api/v1/cameras/CAM-001/reconnect")[0] == 405
    assert request(server, "DELETE", "/api/v1/cameras/../x")[0] == 404


def test_incident_routes_and_validation(api):
    server, backend = api
    assert json.loads(request(server, "GET", "/api/v1/incidents?after_id=7&limit=5")[2])["incidents"] == [{"after": 7, "limit": 5}]
    assert json.loads(request(server, "GET", "/api/v1/incidents?limit=99999")[2])["incidents"][0]["limit"] == 1000
    assert request(server, "GET", "/api/v1/incidents?limit=abc")[0] == 400
    assert request(server, "GET", "/api/v1/alerts")[0] == 200
    assert request(server, "POST", "/api/v1/incidents/INC-00001/status", {"status": "RESOLVED"})[0] == 200
    assert backend.calls[-1] == ("status", "INC-00001", "RESOLVED")
    assert request(server, "POST", "/api/v1/incidents/INC-00001/status", {"status": "DELETE"})[0] == 400
    for decision in ("CONFIRMED", "DISMISSED", "FALSE_ALARM"):
        assert request(server, "POST", "/api/v1/incidents/INC-00001/status", {"status": decision})[0] == 200
    assert request(server, "POST", "/api/v1/incidents/../status", {"status": "NEW"})[0] == 404


def test_oversized_body_is_rejected_and_connection_closed(api):
    server, _ = api
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    connection.putrequest("POST", "/api/v1/cameras/import")
    connection.putheader("Authorization", f"Bearer {TOKEN}")
    connection.putheader("Content-Length", str(2 * 1024 * 1024 + 1))   # declared, never sent
    connection.endheaders()
    response = connection.getresponse()
    response.read()
    connection.close()
    assert response.status == 413 and response.getheader("Connection") == "close"


def test_snapshot_endpoint_auth_size_watch_and_unknown_camera(api):
    server, backend = api
    status, response, data = request(server, "GET", "/api/v1/cameras/CAM-001/snapshot")
    assert status == 200 and data == b"jpeg-bytes"
    assert response.getheader("Content-Type") == "image/jpeg"
    assert backend.calls[-1] == ("snapshot_watch", "CAM-001", True)
    assert request(server, "GET", "/api/v1/cameras/CAM-001/snapshot")[0] == 429
    assert request(server, "GET", "/api/v1/cameras/CAM-404/snapshot")[0] == 404
    assert request(server, "GET", "/api/v1/cameras/CAM-001/snapshot?watch=bad")[0] == 400
    time.sleep(0.51)
    backend.snapshot_payload = b"x" * (512 * 1024 + 1)
    assert request(server, "GET", "/api/v1/cameras/CAM-001/snapshot")[0] == 413
    status, _, _ = request(server, "GET", "/api/v1/cameras/CAM-001/snapshot?watch=0")
    assert status == 204 and backend.calls[-1] == ("snapshot_watch", "CAM-001", False)
    assert request(server, "GET", "/api/v1/cameras/CAM-001/snapshot", token=None)[0] == 401


def test_clip_streaming_and_ranges(api):
    server, backend = api
    status, response, data = request(server, "GET", "/api/v1/incidents/INC-00001/clip")
    assert status == 200 and data == backend.clip.read_bytes() and response.getheader("Accept-Ranges") == "bytes"
    status, response, data = request(server, "GET", "/api/v1/incidents/INC-00001/clip", headers={"Range": "bytes=10-19"})
    assert status == 206 and data == backend.clip.read_bytes()[10:20]
    assert response.getheader("Content-Range") == "bytes 10-19/1024"
    status, _, data = request(server, "GET", "/api/v1/incidents/INC-00001/clip", headers={"Range": "bytes=-4"})
    assert status == 206 and data == backend.clip.read_bytes()[-4:]
    status, _, data = request(server, "GET", "/api/v1/incidents/INC-00001/clip", headers={"Range": "bytes=1000-"})
    assert status == 206 and len(data) == 24
    assert request(server, "GET", "/api/v1/incidents/INC-00001/clip", headers={"Range": "bytes=5000-6000"})[0] == 416
    assert request(server, "GET", "/api/v1/incidents/INC-00009/clip")[0] == 404


def test_server_refuses_weak_token():
    with pytest.raises(ValueError):
        ApiServer("127.0.0.1", 0, "short", object())


def test_unexpected_backend_error_does_not_leak_details(api):
    server, backend = api
    backend.status = lambda: (_ for _ in ()).throw(RuntimeError("secret path C:\\x"))
    status, _, data = request(server, "GET", "/api/v1/status")
    assert status == 500 and b"secret" not in data
