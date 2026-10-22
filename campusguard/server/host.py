"""Headless CampusGuard server: runs every camera, records incidents, serves the API."""
from __future__ import annotations

import logging
import logging.handlers
import shutil
import signal
import sys
import threading
import time
from collections import deque
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer

from campusguard import auth
from campusguard.build_info import BUILD_VERSION as VERSION
from campusguard.credentials import CredentialVault
from campusguard.engine.hardware import detect_hardware, read_engine_override, resolve_profile
from campusguard.server.api import ApiError, ApiServer
from campusguard.server.config import ServerConfig, load_config
from campusguard.server.csv_import import NewCamera, parse_cameras_csv
from campusguard.server.health import HealthTracker
from campusguard.server.qt_bridge import MainThreadInvoker
from campusguard.server.recorder import IncidentRecorder
from campusguard.server.retention import enforce_disk_budget, purge_old_footage
from campusguard.settings import CameraConfig, CameraCredentials
from campusguard.sources import build_capture_source
from campusguard.storage import Repository, application_data_dir

log = logging.getLogger("campusguard.server")

START_BATCH = 4              # cameras opened per tick, so 120 RTSP handshakes don't pile up
START_INTERVAL_MS = 600
RETENTION_INTERVAL_MS = 60 * 60 * 1000
EXIT_NOT_SIGNED_IN = 2
EXIT_ACCESS_LOST = 3


def configure_logging(data_dir: Path) -> None:
    logs = data_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("campusguard.server")
    for handler in list(root.handlers):      # reconfigure cleanly if called again
        root.removeHandler(handler)
        handler.close()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.handlers.RotatingFileHandler(
        logs / "server.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    if sys.stderr is not None:               # windowed Windows builds have no console stream
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        root.addHandler(stream)


class ServerHost:
    """Owns the camera manager, repository and API. Camera operations run on the Qt thread."""

    def __init__(self, repository: Repository, vault, manager, config: ServerConfig,
                 invoker: MainThreadInvoker) -> None:
        self.repository = repository
        self.vault = vault
        self.manager = manager
        self.config = config
        self.invoker = invoker
        self.health = HealthTracker()
        self.recorder = IncidentRecorder(repository)
        self.cameras: dict[str, CameraConfig] = {}
        self._start_queue: deque[CameraConfig] = deque()
        self._start_timer = QTimer()
        self._start_timer.setInterval(START_INTERVAL_MS)
        self._start_timer.timeout.connect(self._start_next_batch)
        self.started_at = time.time()
        self.last_retention: dict = {}
        manager.default_preview = False
        manager.set_settings(repository.get_settings())
        manager.camera_status_changed.connect(self._on_status)
        manager.camera_stats_changed.connect(self.health.set_stats)
        manager.model_status_changed.connect(self.health.set_model_status)
        manager.event_detected.connect(self._on_event)
        manager.footage_saved.connect(self._on_footage)
        self._previous_status: dict[str, str] = {}

    # -- Qt-thread slots ------------------------------------------------
    def _on_status(self, camera_id: str, status: str, message: str) -> None:
        self.health.set_status(camera_id, status, message)
        camera = self.cameras.get(camera_id)
        previous = self._previous_status.get(camera_id)
        self._previous_status[camera_id] = status
        if camera is None:
            return
        if status == "LIVE" and previous != "LIVE":
            self.repository.add_notification("camera_connected", f"{camera.name} ({camera_id}) is live.")
        elif status in {"OFFLINE", "ERROR"} and previous == "LIVE":
            self.repository.add_notification("camera_disconnected", f"{camera.name} ({camera_id}) disconnected.")
            log.warning("camera %s (%s) went %s: %s", camera_id, camera.name, status, message)

    def _on_event(self, camera_id: str, event: str, confidence: float, severity: str) -> None:
        camera = self.cameras.get(camera_id)
        if camera is None:
            return
        cooldown = self.repository.get_settings().alert_cooldown_seconds
        incident = self.recorder.record_event(camera, event, confidence, cooldown)
        if incident is not None:
            log.info("incident %s: %s on %s (%.0f%%)", incident["public_id"], event, camera.name, confidence * 100)

    def _on_footage(self, camera_id: str, path: str) -> None:
        public_id = self.recorder.attach_footage(camera_id, path)
        if public_id:
            log.info("footage saved for %s", public_id)

    # -- camera lifecycle --------------------------------------------------
    def load_saved_cameras(self) -> None:
        for camera in self.repository.list_cameras():
            self.cameras[camera.camera_id] = camera
            self.health.set_status(camera.camera_id, "CONNECTING")
            self._start_queue.append(camera)
        log.info("starting %d saved cameras", len(self._start_queue))
        self._kick_start_queue()

    def _kick_start_queue(self) -> None:
        """Open the first batch right away, the rest every START_INTERVAL_MS."""
        if self._start_queue and not self._start_timer.isActive():
            self._start_timer.start()
            QTimer.singleShot(0, self._start_next_batch)

    def _start_next_batch(self) -> None:
        for _ in range(START_BATCH):
            if not self._start_queue:
                self._start_timer.stop()
                return
            camera = self._start_queue.popleft()
            if camera.camera_id in self.cameras:        # may have been removed meanwhile
                self.manager.start_camera(camera)

    def _create_camera(self, new: NewCamera) -> CameraConfig:
        camera = self.repository.add_camera(new.name, new.source_type, new.address, new.ai_enabled)
        try:
            self.vault.save(camera.camera_id, new.credentials)
        except Exception as error:
            self.repository.remove_camera(camera.camera_id)
            raise ApiError(500, "Could not store the camera credentials in the Windows credential vault.") from error
        self.cameras[camera.camera_id] = camera
        self.health.set_status(camera.camera_id, "CONNECTING")
        self._start_queue.append(camera)
        self._kick_start_queue()
        return camera

    def _existing_keys(self) -> set[tuple[str, str]]:
        return {(c.source_type.upper(), c.source_address.lower()) for c in self.cameras.values()}

    def _camera_dict(self, camera: CameraConfig) -> dict:
        health = self.health.snapshot().get(camera.camera_id, {})
        return {
            "camera_id": camera.camera_id, "name": camera.name, "type": camera.source_type,
            "address": camera.source_address, "ai_enabled": camera.ai_enabled,
            "created_at": camera.created_at, **{k: health.get(k) for k in
            ("status", "health", "message", "fps", "resolution", "seconds_since_frame", "ai")},
        }

    # -- retention ---------------------------------------------------------
    def run_retention(self) -> dict:
        directory = self.repository.footage_dir
        removed = purge_old_footage(directory, self.config.retention_days_footage)
        removed += enforce_disk_budget(directory, int(self.config.max_footage_gb * 1024 ** 3))
        self.repository.forget_footage_paths([str(p) for p in removed])
        incidents = self.repository.purge_incidents_older_than(self.config.retention_days_incidents)
        self.last_retention = {"at": time.time(), "clips_removed": len(removed), "incidents_removed": incidents}
        if removed or incidents:
            log.info("retention removed %d clips and %d incidents", len(removed), incidents)
        return self.last_retention

    def stop_all(self) -> None:
        self._start_timer.stop()
        self.manager.stop_all()


class HostBackend:
    """What the HTTP API calls. Anything touching cameras is marshalled to the Qt thread."""

    def __init__(self, host: ServerHost) -> None:
        self.host = host

    def _on_qt(self, function):
        return self.host.invoker.call(function)

    # reads (thread-safe)
    def status(self) -> dict:
        host = self.host
        hardware = detect_hardware()
        profile = resolve_profile(read_engine_override(application_data_dir()), hardware, len(host.cameras))
        try:
            free_gb = round(shutil.disk_usage(host.repository.footage_dir).free / 1024 ** 3, 1)
        except OSError:
            free_gb = None
        return {
            "version": VERSION,
            "uptime_seconds": int(time.time() - host.started_at),
            "profile": profile.name,
            "hardware": {"cpu_count": hardware.cpu_count, "ram_gb": hardware.ram_gb, "cuda": hardware.cuda,
                         "gpu": hardware.gpu_name, "gpu_memory_gb": hardware.gpu_memory_gb},
            "cameras": host.health.summary(),
            "open_incidents": host.repository.open_incident_count(),
            "footage_disk_free_gb": free_gb,
            "last_retention": host.last_retention,
        }

    def list_cameras(self) -> list[dict]:
        return [self.host._camera_dict(c) for c in list(self.host.cameras.values())]

    @staticmethod
    def _incident(row: dict) -> dict:
        return {
            "id": row["id"], "public_id": row["public_id"], "camera_id": row["camera_id"],
            "camera_name": row["camera_name"], "happened_at": row["happened_at"], "event": row["event"],
            "confidence": row["confidence"], "severity": row["severity"], "status": row["status"],
            "has_footage": bool(row.get("footage_path")),
            **({"alert_id": row["alert_id"], "acknowledged": bool(row["acknowledged"])} if "alert_id" in row else {}),
        }

    def list_incidents(self, after_id: int, limit: int) -> list[dict]:
        if after_id > 0:
            rows = self.host.repository.list_incidents_after(after_id, limit)
        else:
            rows = self.host.repository.list_incidents(limit)
        return [self._incident(r) for r in rows]

    def list_alerts(self, limit: int) -> list[dict]:
        return [self._incident(r) for r in self.host.repository.list_alerts(limit)]

    def footage_path(self, public_id: str) -> Path | None:
        incident = self.host.repository.get_incident(public_id)
        if not incident or not incident.get("footage_path"):
            return None
        path = Path(str(incident["footage_path"])).resolve()
        root = self.host.repository.footage_dir.resolve()
        return path if root in path.parents else None      # never serve files outside the footage folder

    def set_incident_status(self, public_id: str, status: str) -> None:
        if self.host.repository.get_incident(public_id) is None:
            raise ApiError(404, "Unknown incident.")
        self.host.repository.update_incident_status(public_id, status)

    # writes (Qt thread)
    def add_camera(self, spec: dict) -> dict:
        def work() -> dict:
            try:
                new = parse_cameras_csv_row(spec, self.host._existing_keys())
            except ValueError as error:
                raise ApiError(400, str(error))
            return self.host._camera_dict(self.host._create_camera(new))
        return self._on_qt(work)

    def import_cameras(self, csv_text: str) -> dict:
        def work() -> dict:
            plan = parse_cameras_csv(csv_text, self.host._existing_keys())
            added = []
            errors = list(plan.errors)
            for new in plan.valid:
                try:
                    added.append(self.host._create_camera(new).camera_id)
                except ApiError as error:
                    errors.append({"row": None, "name": new.name, "error": error.message})
            log.info("camera import: %d added, %d rejected", len(added), len(errors))
            return {"added": len(added), "camera_ids": added, "errors": errors}
        return self._on_qt(work)

    def _require(self, camera_id: str) -> CameraConfig:
        camera = self.host.cameras.get(camera_id)
        if camera is None:
            raise ApiError(404, "Unknown camera.")
        return camera

    def remove_camera(self, camera_id: str) -> None:
        def work() -> None:
            self._require(camera_id)
            self.host.manager.stop_camera(camera_id)
            self.host.repository.remove_camera(camera_id)
            try:
                self.host.vault.delete(camera_id)
            except Exception:
                pass
            self.host.cameras.pop(camera_id, None)
            self.host.health.remove(camera_id)
        self._on_qt(work)

    def set_camera_ai(self, camera_id: str, enabled: bool) -> None:
        def work() -> None:
            camera = self._require(camera_id)
            self.host.repository.set_camera_ai(camera_id, enabled)
            self.host.cameras[camera_id] = replace(camera, ai_enabled=enabled)
            self.host.manager.set_camera_ai(camera_id, enabled)
        self._on_qt(work)

    def reconnect_camera(self, camera_id: str) -> None:
        def work() -> None:
            camera = self._require(camera_id)
            self.host.manager.reconnect(camera_id, camera)
        self._on_qt(work)


def parse_cameras_csv_row(spec: dict, existing: set[tuple[str, str]]) -> NewCamera:
    """Validate one camera given as a JSON object, using the same rules as the CSV import."""
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["name", "type", "address", "username", "password", "ai_enabled"])
    writer.writerow([
        str(spec.get("name", "")), str(spec.get("type", "RTSP")), str(spec.get("address", "")),
        str(spec.get("username", "")), str(spec.get("password", "")),
        "yes" if spec.get("ai_enabled", True) else "no",
    ])
    plan = parse_cameras_csv(buffer.getvalue(), existing)
    if plan.errors:
        raise ValueError(plan.errors[0]["error"])
    return plan.valid[0]


def run_server(host_override: str | None = None, port_override: int | None = None) -> int:
    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    app.setOrganizationName("CampusGuard")
    app.setApplicationName("CampusGuard")
    data_dir = application_data_dir()
    configure_logging(data_dir)
    log.info("CampusGuard server %s starting", VERSION)

    # The same website account / approval rules as the desktop app apply.
    session = auth.resume()
    if session is None:
        log.error("Not signed in. Run `CampusGuard.exe --server-login` once as this Windows user, then start the server again.")
        return EXIT_NOT_SIGNED_IN
    log.info("signed in as %s", session.email)

    config = load_config(data_dir)
    if host_override:
        config.host = host_override
    if port_override:
        config.port = port_override

    from campusguard.camera_runtime import CameraManager   # imports torch: after the cheap checks

    repository = Repository()
    invoker = MainThreadInvoker()
    manager = CameraManager(CredentialVault(), footage_dir=repository.footage_dir)
    host = ServerHost(repository, CredentialVault(), manager, config, invoker)
    try:
        api = ApiServer(config.host, config.port, config.token, HostBackend(host), log=log.info,
                        tls_cert_file=config.tls_cert_file, tls_key_file=config.tls_key_file)
    except OSError as error:
        log.error("Could not open %s:%s — %s", config.host, config.port, error)
        return 1
    api.start()
    scheme = "https" if config.tls_cert_file and config.tls_key_file else "http"
    log.info("API listening on %s://%s:%d/api/v1 (token in %s)", scheme, config.host, api.port, data_dir / "server.json")

    exit_code = {"value": 0}

    def shutdown(code: int = 0) -> None:
        exit_code["value"] = code or exit_code["value"]
        app.quit()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: shutdown(0))
    keepalive = QTimer()               # lets Python-level signal handlers run
    keepalive.timeout.connect(lambda: None)
    keepalive.start(500)

    host.load_saved_cameras()
    threading.Thread(target=host.run_retention, name="retention", daemon=True).start()
    retention_timer = QTimer()
    retention_timer.timeout.connect(
        lambda: threading.Thread(target=host.run_retention, name="retention", daemon=True).start()
    )
    retention_timer.start(RETENTION_INTERVAL_MS)

    def recheck() -> None:
        def work() -> None:
            result = auth.resume()
            if result is None:
                invoker.call(lambda: (log.error("Account access could not be verified any more — stopping."), shutdown(EXIT_ACCESS_LOST)))
        threading.Thread(target=work, name="access-recheck", daemon=True).start()

    recheck_timer = QTimer()
    recheck_timer.timeout.connect(recheck)
    recheck_timer.start(int(config.recheck_hours * 3600 * 1000))

    app.exec()
    log.info("shutting down")
    api.stop()
    host.stop_all()
    return exit_code["value"]
