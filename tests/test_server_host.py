"""Host + API end to end: real Repository/API/Qt bridge, fake camera manager."""
import http.client
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QObject, Signal

from campusguard.server.api import ApiServer
from campusguard.server.config import ServerConfig
from campusguard.server.host import HostBackend, ServerHost
from campusguard.server.qt_bridge import MainThreadInvoker
from campusguard.settings import AppSettings, CameraCredentials

TOKEN = "k" * 32


class FakeManager(QObject):
    camera_status_changed = Signal(str, str, str)
    camera_stats_changed = Signal(str, float, str)
    model_status_changed = Signal(str, str, str)
    event_detected = Signal(str, str, float, str)
    footage_saved = Signal(str, str)
    snapshot_ready = Signal(str, bytes)

    def __init__(self):
        super().__init__()
        self.default_preview = True
        self.started, self.stopped, self.ai, self.reconnected = [], [], {}, []
        self.snapshot_enabled = {}

    def set_settings(self, settings): self.settings = settings
    def start_camera(self, camera): self.started.append(camera.camera_id)
    def stop_camera(self, camera_id): self.stopped.append(camera_id)
    def set_camera_ai(self, camera_id, enabled): self.ai[camera_id] = enabled
    def set_camera_snapshot(self, camera_id, enabled): self.snapshot_enabled[camera_id] = enabled
    def reconnect(self, camera_id, camera=None): self.reconnected.append(camera_id)
    def stop_all(self): self.stopped.append("ALL")


class FakeVault:
    def __init__(self): self.saved = {}
    def save(self, camera_id, credentials): self.saved[camera_id] = credentials
    def load(self, camera_id): return self.saved.get(camera_id, CameraCredentials())
    def delete(self, camera_id): self.saved.pop(camera_id, None)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    import campusguard.storage as storage
    monkeypatch.setattr(storage, "application_data_dir", lambda: tmp_path)
    repo = storage.Repository(tmp_path / "campusguard.db")
    manager, vault, invoker = FakeManager(), FakeVault(), MainThreadInvoker()
    host = ServerHost(repo, vault, manager, ServerConfig(token=TOKEN), invoker)
    server = ApiServer("127.0.0.1", 0, TOKEN, HostBackend(host))
    server.start()
    pool = ThreadPoolExecutor(max_workers=4)

    def call(method, path, body=None, raw=None):
        def work():
            connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=15)
            data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
            connection.request(method, "/api/v1" + path, body=data, headers={"Authorization": f"Bearer {TOKEN}"})
            response = connection.getresponse()
            payload = response.read()
            connection.close()
            return response.status, response.getheader("Content-Type"), payload
        future = pool.submit(work)
        deadline = time.monotonic() + 20
        while not future.done() and time.monotonic() < deadline:
            app.processEvents()           # the Qt thread serves camera operations
            time.sleep(0.005)
        status, ctype, payload = future.result(timeout=1)
        return status, (json.loads(payload) if ctype and "json" in ctype else payload)

    yield SimpleNamespace_(app=app, repo=repo, manager=manager, vault=vault, host=host, call=call, tmp=tmp_path)
    server.stop()
    pool.shutdown()
    host.stop_all()


class SimpleNamespace_:
    def __init__(self, **kw): self.__dict__.update(kw)


def pump(app, seconds=0.0):
    end = time.monotonic() + seconds
    app.processEvents()
    while time.monotonic() < end:
        app.processEvents(); time.sleep(0.005)


def test_server_mode_disables_live_preview(env):
    assert env.manager.default_preview is False


def test_add_list_remove_camera_with_credentials(env):
    status, body = env.call("POST", "/cameras", {"name": "Gate", "type": "RTSP", "address": "rtsp://10.0.0.5/s2",
                                                  "username": "admin", "password": "pw"})
    assert status == 201 and body["camera_id"] == "CAM-001" and body["name"] == "Gate"
    assert "password" not in json.dumps(body) and "pw" not in json.dumps(body).replace("rtsp", "")
    assert env.vault.saved["CAM-001"].password == "pw"
    pump(env.app, 1.0)                                          # staggered start
    assert env.manager.started == ["CAM-001"]
    status, body = env.call("GET", "/cameras")
    assert [c["camera_id"] for c in body["cameras"]] == ["CAM-001"] and body["cameras"][0]["health"] == "connecting"
    status, body = env.call("POST", "/cameras", {"name": "Dup", "address": "rtsp://10.0.0.5/s2"})
    assert status == 400 and "already configured" in body["error"]
    assert env.call("POST", "/cameras", {"name": "Bad", "address": "http://x"})[0] == 400
    assert env.call("POST", "/cameras/CAM-001/ai", {"enabled": False})[0] == 200
    assert env.manager.ai["CAM-001"] is False and env.repo.list_cameras()[0].ai_enabled is False
    assert env.call("POST", "/cameras/CAM-001/reconnect")[0] == 200 and env.manager.reconnected == ["CAM-001"]
    assert env.call("DELETE", "/cameras/CAM-001")[0] == 200
    assert env.call("DELETE", "/cameras/CAM-001")[0] == 404
    assert env.repo.list_cameras() == [] and "CAM-001" not in env.vault.saved and env.manager.stopped == ["CAM-001"]
    assert env.call("GET", "/cameras")[1]["cameras"] == []


def test_bulk_import_staggers_camera_start(env):
    rows = "name,address\n" + "".join(f"Cam {i},rtsp://10.1.0.{i}/s2\n" for i in range(1, 11)) + "Bad,http://x\n"
    status, body = env.call("POST", "/cameras/import", raw=rows.encode())
    assert status == 200 and body["added"] == 10 and len(body["errors"]) == 1
    assert len(env.repo.list_cameras()) == 10
    pump(env.app, 0.1)
    assert 0 < len(env.manager.started) <= 4                    # first batch only
    pump(env.app, 2.2)
    assert sorted(env.manager.started) == sorted(c.camera_id for c in env.repo.list_cameras())


def test_removed_before_start_is_never_started(env):
    env.call("POST", "/cameras/import", raw=b"name,address\nA,rtsp://h/1\nB,rtsp://h/2\nC,rtsp://h/3\nD,rtsp://h/4\nE,rtsp://h/5\n")
    env.call("DELETE", "/cameras/CAM-005")
    pump(env.app, 1.5)
    assert "CAM-005" not in env.manager.started and len(env.manager.started) == 4


def test_saved_cameras_start_on_boot(env):
    env.repo.add_camera("Old", "RTSP", "rtsp://h/old", True)
    env.host.load_saved_cameras()
    pump(env.app, 1.0)
    assert env.manager.started == ["CAM-001"]


def test_event_becomes_incident_with_footage_and_api_access(env):
    env.call("POST", "/cameras", {"name": "Hall", "address": "rtsp://h/hall"})
    env.manager.event_detected.emit("CAM-001", "FIGHT DETECTED", 0.93, "HIGH")
    pump(env.app)
    status, body = env.call("GET", "/incidents")
    incident = body["incidents"][0]
    assert incident["public_id"] == "INC-00001" and incident["severity"] == "MEDIUM" and incident["has_footage"] is False
    assert "footage_path" not in incident
    env.manager.event_detected.emit("CAM-001", "FIGHT DETECTED", 0.99, "HIGH")      # cooldown: no second incident
    pump(env.app)
    assert len(env.call("GET", "/incidents")[1]["incidents"]) == 1

    clip = env.repo.footage_dir / "FIGHT_1.mp4"
    clip.write_bytes(b"video-bytes")
    env.manager.footage_saved.emit("CAM-001", str(clip))
    pump(env.app)
    assert env.call("GET", "/incidents")[1]["incidents"][0]["has_footage"] is True
    status, data = env.call("GET", "/incidents/INC-00001/clip")
    assert status == 200 and data == b"video-bytes"
    assert env.call("GET", "/incidents?after_id=1")[1]["incidents"] == []
    status, body = env.call("GET", "/alerts")
    assert body["alerts"][0]["acknowledged"] is False and "alert_id" in body["alerts"][0]
    assert env.call("POST", "/incidents/INC-00001/status", {"status": "RESOLVED"})[0] == 200
    assert env.call("GET", "/incidents")[1]["incidents"][0]["status"] == "RESOLVED"
    assert env.call("POST", "/incidents/INC-09999/status", {"status": "RESOLVED"})[0] == 404


def test_clip_outside_footage_folder_is_never_served(env):
    secret = env.tmp / "secret.mp4"
    secret.write_bytes(b"secret")
    env.call("POST", "/cameras", {"name": "Hall", "address": "rtsp://h/hall"})
    env.manager.event_detected.emit("CAM-001", "FIGHT DETECTED", 0.9, "HIGH")
    pump(env.app)
    env.repo.attach_incident_footage("INC-00001", str(secret))
    assert env.call("GET", "/incidents/INC-00001/clip")[0] == 404


def test_snapshot_cache_is_camera_scoped_and_watch_can_stop(env):
    env.call("POST", "/cameras", {"name": "Hall", "address": "rtsp://h/hall"})
    env.manager.snapshot_ready.emit("CAM-001", b"jpeg-data")
    pump(env.app)
    status, payload = env.call("GET", "/cameras/CAM-001/snapshot")
    assert status == 200 and payload == b"jpeg-data"
    assert env.manager.snapshot_enabled["CAM-001"] is True
    assert env.call("GET", "/cameras/CAM-404/snapshot")[0] == 404
    status, _ = env.call("GET", "/cameras/CAM-001/snapshot?watch=0")
    assert status == 204 and env.manager.snapshot_enabled["CAM-001"] is False
    assert env.host.snapshot_bytes("CAM-001") is None


def test_health_and_status_from_camera_signals(env):
    env.call("POST", "/cameras", {"name": "Hall", "address": "rtsp://h/hall"})
    env.manager.camera_status_changed.emit("CAM-001", "LIVE", "")
    env.manager.camera_stats_changed.emit("CAM-001", 14.8, "640x360")
    pump(env.app)
    camera = env.call("GET", "/cameras")[1]["cameras"][0]
    assert camera["status"] == "LIVE" and camera["health"] == "ok" and camera["fps"] == 14.8 and camera["resolution"] == "640x360"
    assert any(n["kind"] == "camera_connected" for n in env.repo.list_notifications())
    env.manager.camera_status_changed.emit("CAM-001", "OFFLINE", "lost")
    pump(env.app)
    assert any(n["kind"] == "camera_disconnected" for n in env.repo.list_notifications())
    status, body = env.call("GET", "/status")
    assert status == 200 and body["cameras"]["total"] == 1 and body["cameras"]["offline"] == 1
    assert body["profile"] in {"lite", "standard", "server"} and "footage_disk_free_gb" in body


def test_retention_removes_old_clips_and_incidents(env):
    env.call("POST", "/cameras", {"name": "Hall", "address": "rtsp://h/hall"})
    env.manager.event_detected.emit("CAM-001", "FIGHT DETECTED", 0.9, "HIGH")
    pump(env.app)
    clip = env.repo.footage_dir / "FIGHT_old.mp4"
    clip.write_bytes(b"x")
    old = time.time() - 40 * 86400
    os.utime(clip, (old, old))
    env.repo.attach_incident_footage("INC-00001", str(clip))
    result = env.host.run_retention()
    assert result["clips_removed"] == 1 and not clip.exists()
    assert env.call("GET", "/incidents")[1]["incidents"][0]["has_footage"] is False
    env.host.config.retention_days_incidents = 1
    import sqlite3
    with sqlite3.connect(env.repo.database_path) as conn:
        conn.execute("UPDATE incidents SET happened_at = '2020-01-01T00:00:00+00:00'")
    assert env.host.run_retention()["incidents_removed"] == 1
    assert env.call("GET", "/incidents")[1]["incidents"] == []


# ------------------------------------------------------------- run_server()
def test_run_server_refuses_to_start_when_not_signed_in(tmp_path, monkeypatch):
    import campusguard.server.host as host_module
    monkeypatch.setattr(host_module, "application_data_dir", lambda: tmp_path)
    monkeypatch.setattr(host_module.auth, "resume", lambda: None)
    assert host_module.run_server() == host_module.EXIT_NOT_SIGNED_IN
    assert not (tmp_path / "server.json").exists()            # nothing started, no token minted


def test_run_server_full_start_serve_and_clean_stop(tmp_path, monkeypatch):
    import socket
    from unittest.mock import MagicMock
    try:
        import torch  # noqa: F401
    except ImportError:
        for name in ("torch", "torch.nn", "torch.nn.functional", "torch.jit", "torchvision",
                     "torchvision.models", "torchvision.models.video", "ultralytics"):
            monkeypatch.setitem(sys.modules, name, MagicMock())
    for name in ("campusguard.camera_runtime", "campusguard.ai_pipeline", "campusguard.model_registry",
                 "campusguard.model_adapters"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    import campusguard.camera_runtime as runtime
    import campusguard.server.host as host_module
    import campusguard.storage as storage

    monkeypatch.setattr(host_module, "application_data_dir", lambda: tmp_path)
    monkeypatch.setattr(storage, "application_data_dir", lambda: tmp_path)
    monkeypatch.setattr(host_module.auth, "resume", lambda: SimpleNamespace_(email="admin@school.org"))
    monkeypatch.setattr(host_module, "Repository", lambda: storage.Repository(tmp_path / "campusguard.db"))
    monkeypatch.setattr(host_module, "CredentialVault", FakeVault)
    monkeypatch.setattr(runtime, "CameraManager", lambda vault, footage_dir=None: FakeManager())
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    (tmp_path / "server.json").write_text(json.dumps({"port": port, "token": TOKEN}))
    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    results = {}

    def client():
        time.sleep(0.6)
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", "/api/v1/status", headers={"Authorization": f"Bearer {TOKEN}"})
        response = connection.getresponse()
        results["status"], results["body"] = response.status, json.loads(response.read())
        connection.request("GET", "/api/v1/status")
        results["anon"] = connection.getresponse().status
        connection.close()
        QCoreApplication.instance().quit()          # (thread-safe in Qt)

    threading.Thread(target=client, daemon=True).start()
    code = host_module.run_server()
    assert code == 0
    assert results["status"] == 200 and results["body"]["cameras"]["total"] == 0 and results["anon"] == 401
    assert (tmp_path / "logs" / "server.log").is_file()
    for name in ("campusguard.camera_runtime", "campusguard.ai_pipeline", "campusguard.model_registry",
                 "campusguard.model_adapters"):
        sys.modules.pop(name, None)
