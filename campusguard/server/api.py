"""Token-protected JSON/HTTP API of the CampusGuard server (standard library only)."""
from __future__ import annotations

import hmac
import json
import re
import ssl
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

API_PREFIX = "/api/v1"
MAX_BODY_BYTES = 2 * 1024 * 1024
FAILED_AUTH_LIMIT = 10
FAILED_AUTH_WINDOW_SECONDS = 60.0
MAX_SNAPSHOT_BYTES = 512 * 1024
SNAPSHOT_MIN_INTERVAL_SECONDS = 0.5


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class _AuthLimiter:
    """Slow down token guessing: too many failures from one address -> 429."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: dict[str, list[float]] = {}

    def blocked(self, address: str) -> bool:
        now = self._clock()
        with self._lock:
            recent = [t for t in self._failures.get(address, []) if now - t < FAILED_AUTH_WINDOW_SECONDS]
            self._failures[address] = recent
            return len(recent) >= FAILED_AUTH_LIMIT

    def fail(self, address: str) -> None:
        with self._lock:
            self._failures.setdefault(address, []).append(self._clock())


_ROUTES: list[tuple[str, re.Pattern, str]] = [
    ("GET", re.compile(r"^/status$"), "status"),
    ("GET", re.compile(r"^/cameras$"), "list_cameras"),
    ("POST", re.compile(r"^/cameras$"), "add_camera"),
    ("POST", re.compile(r"^/cameras/import$"), "import_cameras"),
    ("GET", re.compile(r"^/cameras/(?P<camera_id>[A-Za-z0-9_-]+)/stream$"), "stream"),
    ("GET", re.compile(r"^/cameras/(?P<camera_id>[A-Za-z0-9_-]+)/snapshot$"), "snapshot"),
    ("DELETE", re.compile(r"^/cameras/(?P<camera_id>[A-Za-z0-9_-]+)$"), "remove_camera"),
    ("POST", re.compile(r"^/cameras/(?P<camera_id>[A-Za-z0-9_-]+)/ai$"), "set_camera_ai"),
    ("POST", re.compile(r"^/cameras/(?P<camera_id>[A-Za-z0-9_-]+)/reconnect$"), "reconnect_camera"),
    ("GET", re.compile(r"^/incidents$"), "list_incidents"),
    ("GET", re.compile(r"^/alerts$"), "list_alerts"),
    ("POST", re.compile(r"^/incidents/(?P<public_id>INC-\d+)/status$"), "set_incident_status"),
    ("GET", re.compile(r"^/incidents/(?P<public_id>INC-\d+)/clip$"), "clip"),
]


def _int_param(query: dict[str, list[str]], name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(query.get(name, [default])[0])))
    except (TypeError, ValueError):
        raise ApiError(HTTPStatus.BAD_REQUEST, f"'{name}' must be a whole number.")


class _Handler(BaseHTTPRequestHandler):
    server_version = "CampusGuardServer"
    protocol_version = "HTTP/1.1"

    # -- plumbing -----------------------------------------------------
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        self.server.log(f"{self.client_address[0]} {format % args}")  # type: ignore[attr-defined]

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if status >= 400:
            # An error may leave an unread request body behind: never reuse the connection.
            self.close_connection = True
            self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _authorised(self) -> bool:
        address = self.client_address[0]
        limiter: _AuthLimiter = self.server.limiter  # type: ignore[attr-defined]
        if limiter.blocked(address):
            raise ApiError(HTTPStatus.TOO_MANY_REQUESTS, "Too many failed attempts. Try again in a minute.")
        header = self.headers.get("Authorization", "")
        supplied = header[7:].strip() if header.lower().startswith("bearer ") else ""
        expected: str = self.server.token  # type: ignore[attr-defined]
        if supplied and hmac.compare_digest(supplied.encode(), expected.encode()):
            return True
        limiter.fail(address)
        return False

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid Content-Length.")
        if length < 0 or length > MAX_BODY_BYTES:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request body is too large.")
        return self.rfile.read(length) if length else b""

    def _read_json(self) -> dict:
        raw = self._read_body()
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "The request body is not valid JSON.")
        if not isinstance(data, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "The request body must be a JSON object.")
        return data

    # -- dispatch -----------------------------------------------------
    def _handle(self) -> None:
        try:
            parts = urlsplit(self.path)
            path = parts.path.rstrip("/") or "/"
            if path == "/health" and self.command == "GET":
                self._send_json(HTTPStatus.OK, {"status": "ok"})
                return
            if not path.startswith(API_PREFIX + "/"):
                raise ApiError(HTTPStatus.NOT_FOUND, "Unknown path.")
            if not self._authorised():
                raise ApiError(HTTPStatus.UNAUTHORIZED, "Missing or invalid access token.")
            route_path = path[len(API_PREFIX):]
            query = parse_qs(parts.query)
            allowed: list[str] = []
            for method, pattern, name in _ROUTES:
                match = pattern.match(route_path)
                if not match:
                    continue
                allowed.append(method)
                if method != self.command:
                    continue
                getattr(self, f"_route_{name}")(query, **match.groupdict())
                return
            if allowed:
                raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Method not allowed for this path.")
            raise ApiError(HTTPStatus.NOT_FOUND, "Unknown path.")
        except ApiError as error:
            self._send_json(error.status, {"error": error.message})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as error:  # never leak a traceback to the client
            self.server.log(f"unhandled error on {self.command} {self.path}: {error!r}")  # type: ignore[attr-defined]
            try:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Internal server error."})
            except OSError:
                pass

    do_GET = do_POST = do_DELETE = _handle

    @property
    def backend(self):
        return self.server.backend  # type: ignore[attr-defined]

    # -- routes -------------------------------------------------------
    def _route_status(self, query) -> None:
        self._send_json(HTTPStatus.OK, self.backend.status())

    def _route_list_cameras(self, query) -> None:
        self._send_json(HTTPStatus.OK, {"cameras": self.backend.list_cameras()})

    def _route_add_camera(self, query) -> None:
        self._send_json(HTTPStatus.CREATED, self.backend.add_camera(self._read_json()))

    def _route_import_cameras(self, query) -> None:
        text = self._read_body().decode("utf-8-sig", errors="replace")
        self._send_json(HTTPStatus.OK, self.backend.import_cameras(text))

    def _route_stream(self, query, camera_id: str) -> None:
        """Stream selected camera frames as authenticated multipart MJPEG."""
        limiter = self.server.stream_limiter  # type: ignore[attr-defined]
        address = self.client_address[0]
        if not limiter.acquire(address):
            raise ApiError(HTTPStatus.TOO_MANY_REQUESTS, "Too many live streams from this client. Close another live view first.")
        enabled = False
        try:
            self.backend.validate_camera_snapshot(camera_id)
            self.backend.set_camera_snapshot_rate(camera_id, 10.0)
            self.backend.set_camera_snapshot_enabled(camera_id, True)
            enabled = True
        except Exception:
            limiter.release(address)
            raise

        last_jpeg: bytes | None = None
        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                self.backend.touch_camera_snapshot(camera_id)
                jpeg = self.backend.camera_snapshot(camera_id)
                if jpeg and jpeg != last_jpeg and len(jpeg) <= MAX_SNAPSHOT_BYTES:
                    self.wfile.write(
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
                        + jpeg + b"\r\n"
                    )
                    self.wfile.flush()
                    last_jpeg = jpeg
                time.sleep(0.05)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            # Client closed the live view or the network dropped.
            pass
        except Exception as error:
            self.server.log(f"live stream stopped for {camera_id}: {error!r}")  # type: ignore[attr-defined]
        finally:
            if enabled:
                try:
                    self.backend.set_camera_snapshot_enabled(camera_id, False)
                    self.backend.set_camera_snapshot_rate(camera_id, 2.0)
                except Exception:
                    pass
            limiter.release(address)

    def _route_snapshot(self, query, camera_id: str) -> None:
        watch_values = query.get("watch", ["1"])
        if len(watch_values) != 1 or watch_values[0] not in {"0", "1"}:
            raise ApiError(HTTPStatus.BAD_REQUEST, "'watch' must be 0 or 1.")
        if watch_values[0] == "0":
            self.backend.set_camera_snapshot_enabled(camera_id, False)
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.backend.validate_camera_snapshot(camera_id)
        limiter = self.server.snapshot_limiter  # type: ignore[attr-defined]
        if not limiter.allow(self.client_address[0], camera_id):
            raise ApiError(HTTPStatus.TOO_MANY_REQUESTS, "Snapshot polling is limited to two requests per second per camera.")
        self.backend.set_camera_snapshot_enabled(camera_id, True)
        jpeg = self.backend.camera_snapshot(camera_id)
        if not jpeg:
            raise ApiError(HTTPStatus.SERVICE_UNAVAILABLE, "Snapshot is not ready yet; retry shortly.")
        if len(jpeg) > MAX_SNAPSHOT_BYTES:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Snapshot exceeds the size limit.")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(jpeg)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(jpeg)

    def _route_remove_camera(self, query, camera_id: str) -> None:
        self.backend.remove_camera(camera_id)
        self._send_json(HTTPStatus.OK, {"removed": camera_id})

    def _route_set_camera_ai(self, query, camera_id: str) -> None:
        data = self._read_json()
        if not isinstance(data.get("enabled"), bool):
            raise ApiError(HTTPStatus.BAD_REQUEST, "'enabled' must be true or false.")
        self.backend.set_camera_ai(camera_id, data["enabled"])
        self._send_json(HTTPStatus.OK, {"camera_id": camera_id, "ai_enabled": data["enabled"]})

    def _route_reconnect_camera(self, query, camera_id: str) -> None:
        self.backend.reconnect_camera(camera_id)
        self._send_json(HTTPStatus.OK, {"camera_id": camera_id, "reconnecting": True})

    def _route_list_incidents(self, query) -> None:
        after = _int_param(query, "after_id", 0, 0, 2**62)
        limit = _int_param(query, "limit", 200, 1, 1000)
        self._send_json(HTTPStatus.OK, {"incidents": self.backend.list_incidents(after, limit)})

    def _route_list_alerts(self, query) -> None:
        limit = _int_param(query, "limit", 200, 1, 1000)
        self._send_json(HTTPStatus.OK, {"alerts": self.backend.list_alerts(limit)})

    def _route_set_incident_status(self, query, public_id: str) -> None:
        data = self._read_json()
        status = data.get("status")
        if status not in {"NEW", "ACKNOWLEDGED", "RESOLVED", "CONFIRMED", "DISMISSED", "FALSE_ALARM"}:
            raise ApiError(HTTPStatus.BAD_REQUEST, "'status' must be NEW, ACKNOWLEDGED, RESOLVED, CONFIRMED, DISMISSED or FALSE_ALARM.")
        self.backend.set_incident_status(public_id, status)
        self._send_json(HTTPStatus.OK, {"public_id": public_id, "status": status})

    def _route_clip(self, query, public_id: str) -> None:
        path: Path | None = self.backend.footage_path(public_id)
        if path is None or not path.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "No saved footage for this incident.")
        size = path.stat().st_size
        start, end = 0, size - 1
        status = HTTPStatus.OK
        range_header = self.headers.get("Range", "")
        match = re.match(r"^bytes=(\d*)-(\d*)$", range_header.strip())
        if match and (match.group(1) or match.group(2)):
            if match.group(1):
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else size - 1
            else:  # suffix range: last N bytes
                start = max(0, size - int(match.group(2)))
            end = min(end, size - 1)
            if start > end or start >= size:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = HTTPStatus.PARTIAL_CONTENT
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as source:
            source.seek(start)
            remaining = length
            while remaining > 0:
                chunk = source.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


class _SnapshotRateLimiter:
    """Limit each client to one snapshot request per camera every half-second."""
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: dict[tuple[str, str], float] = {}

    def allow(self, address: str, camera_id: str) -> bool:
        now = time.monotonic()
        key = (address, camera_id)
        with self._lock:
            previous = self._last.get(key)
            if previous is not None and now - previous < SNAPSHOT_MIN_INTERVAL_SECONDS:
                return False
            self._last[key] = now
            if len(self._last) > 4096:
                cutoff = now - 60.0
                self._last = {item: stamp for item, stamp in self._last.items() if stamp >= cutoff}
            return True


class _StreamLimiter:
    """Bound concurrent live streams per desktop to protect server capacity."""
    MAX_PER_ADDRESS = 4
    MAX_GLOBAL = 24

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: dict[str, int] = {}

    def acquire(self, address: str) -> bool:
        with self._lock:
            active = self._active.get(address, 0)
            total = sum(self._active.values())
            if active >= self.MAX_PER_ADDRESS or total >= self.MAX_GLOBAL:
                return False
            self._active[address] = active + 1
            return True

    def release(self, address: str) -> None:
        with self._lock:
            active = self._active.get(address, 0)
            if active <= 1:
                self._active.pop(address, None)
            else:
                self._active[address] = active - 1


class ApiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, host: str, port: int, token: str, backend, log=lambda message: None,
                 tls_cert_file: str = "", tls_key_file: str = "") -> None:
        if len(token) < 16:
            raise ValueError("The API token must be at least 16 characters.")
        super().__init__((host, port), _Handler)
        self.token = token
        self.backend = backend
        self.log = log
        self.limiter = _AuthLimiter()
        self.snapshot_limiter = _SnapshotRateLimiter()
        self.stream_limiter = _StreamLimiter()
        self._thread: threading.Thread | None = None
        if tls_cert_file and tls_key_file:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(tls_cert_file, tls_key_file)
            self.socket = context.wrap_socket(self.socket, server_side=True)

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    def start(self) -> None:
        self._thread = threading.Thread(target=self.serve_forever, name="campusguard-api", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self.shutdown()
            self._thread.join(timeout=5)
            self._thread = None
        self.server_close()
