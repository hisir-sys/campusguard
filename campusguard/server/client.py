"""Small, timeout-bounded client for the CampusGuard server API.

All methods are synchronous by design; UI callers must run them in a worker thread.
"""
from __future__ import annotations

import json
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

MAX_JSON_RESPONSE_BYTES = 8 * 1024 * 1024
CLIP_CHUNK_BYTES = 256 * 1024


class ServerConnectionError(RuntimeError):
    """A safe, user-facing server connection failure."""


class RemoteServerClient:
    def __init__(self, address: str, token: str, timeout: float = 4.0, retries: int = 2) -> None:
        self.base_url = self._normalise_address(address)
        self.token = token.strip()
        self.timeout = max(0.5, min(float(timeout), 15.0))
        self.retries = max(0, min(int(retries), 4))
        if not self.token:
            raise ServerConnectionError("Enter the server access token.")

    @staticmethod
    def _normalise_address(address: str) -> str:
        value = address.strip().rstrip("/")
        try:
            parsed = urllib.parse.urlsplit(value)
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
                raise ValueError
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError
            if parsed.path not in {"", "/", "/api/v1"}:
                raise ValueError
            host = parsed.hostname
            port = f":{parsed.port}" if parsed.port is not None else ""
            netloc = f"[{host}]{port}" if ":" in host and not host.startswith("[") else f"{host}{port}"
        except (ValueError, TypeError):
            raise ServerConnectionError(
                "Enter a valid server address such as https://school-server:8765 (no username, password, or extra path)."
            ) from None
        return f"{parsed.scheme.lower()}://{netloc}"

    def _request(
        self,
        path: str,
        method: str = "GET",
        payload: Any = None,
        raw: bytes | None = None,
        content_type: str = "application/json",
        range_header: str | None = None,
    ) -> tuple[int, bytes, str]:
        url = self.base_url + path
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json, image/jpeg, video/mp4"}
        data = raw
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        if data is not None:
            headers["Content-Type"] = content_type
        if range_header:
            headers["Range"] = range_header
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        attempts = self.retries + 1 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    content_length = response.headers.get("Content-Length")
                    if content_length and path.endswith("/snapshot") and int(content_length) > 512 * 1024:
                        raise ServerConnectionError("The server returned an oversized camera snapshot.")
                    body = response.read(MAX_JSON_RESPONSE_BYTES + 1 if "clip" not in path else -1)
                    if "clip" not in path and len(body) > MAX_JSON_RESPONSE_BYTES:
                        raise ServerConnectionError("The server response is larger than the allowed limit.")
                    return response.status, body, response.headers.get("Content-Type", "")
            except urllib.error.HTTPError as error:
                try:
                    body = error.read(4096).decode("utf-8", errors="replace")
                    try:
                        message = json.loads(body).get("error", "")
                    except (ValueError, AttributeError):
                        message = ""
                finally:
                    error.close()
                if error.code == 401:
                    raise ServerConnectionError("Access denied: the token is wrong or server access has been lost.") from None
                if error.code == 403:
                    raise ServerConnectionError("The server denied access. Check the account approval and permissions.") from None
                if error.code == 429:
                    raise ServerConnectionError("The server is rate-limiting requests. Wait briefly and retry.") from None
                if error.code == 503:
                    if path.endswith("/snapshot"):
                        raise ServerConnectionError(message or "The server is online but this camera snapshot is not ready yet.") from None
                    raise ServerConnectionError(message or "The server is temporarily unavailable. Retrying automatically in the background.") from None
                if error.code == 404:
                    raise ServerConnectionError(message or "The requested camera or incident was not found.") from None
                if error.code >= 500:
                    raise ServerConnectionError("The server reported an internal error. Check the server log.") from None
                raise ServerConnectionError(message or f"The server rejected the request (HTTP {error.code}).") from None
            except (ssl.SSLCertVerificationError, ssl.CertificateError) as error:
                raise ServerConnectionError(f"HTTPS certificate verification failed: {error}") from None
            except urllib.error.URLError as error:
                reason = error.reason
                if isinstance(reason, (ssl.SSLCertVerificationError, ssl.CertificateError)):
                    raise ServerConnectionError(f"HTTPS certificate verification failed: {reason}") from None
                if isinstance(reason, (socket.timeout, TimeoutError)):
                    message = "The server connection timed out."
                else:
                    message = "The server is unreachable or is not accepting connections."
                if attempt + 1 >= attempts:
                    raise ServerConnectionError(f"{message} Retrying automatically in the background.") from None
            except (socket.timeout, TimeoutError):
                if attempt + 1 >= attempts:
                    raise ServerConnectionError("The server connection timed out. Retrying automatically in the background.") from None
            if attempt + 1 < attempts:
                time.sleep(0.25 * (2 ** attempt))
        raise ServerConnectionError("The server is unreachable.")

    @staticmethod
    def _json(body: bytes) -> Any:
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ServerConnectionError("The server returned invalid JSON.") from None

    def test_connection(self) -> dict:
        status, body, _ = self._request("/api/v1/status")
        if status != 200:
            raise ServerConnectionError("The server did not confirm a successful connection.")
        return self._json(body)

    def list_cameras(self) -> list[dict]:
        return self._json(self._request("/api/v1/cameras")[1]).get("cameras", [])

    def list_incidents(self) -> list[dict]:
        return self._json(self._request("/api/v1/incidents?limit=200")[1]).get("incidents", [])

    def list_alerts(self) -> list[dict]:
        return self._json(self._request("/api/v1/alerts?limit=200")[1]).get("alerts", [])

    def snapshot(self, camera_id: str) -> bytes:
        status, body, content_type = self._request(f"/api/v1/cameras/{camera_id}/snapshot")
        if status != 200 or content_type.split(";", 1)[0].lower() != "image/jpeg":
            raise ServerConnectionError("The server did not return a camera JPEG snapshot.")
        return body

    def stop_snapshot(self, camera_id: str) -> None:
        self._request(f"/api/v1/cameras/{camera_id}/snapshot?watch=0")

    def add_camera(self, name: str, source_type: str, address: str, username: str = "", password: str = "", ai_enabled: bool = True) -> dict:
        body = {"name": name, "type": source_type, "address": address, "username": username, "password": password, "ai_enabled": ai_enabled}
        return self._json(self._request("/api/v1/cameras", "POST", body)[1])

    def remove_camera(self, camera_id: str) -> None:
        self._request(f"/api/v1/cameras/{camera_id}", "DELETE")

    def reconnect_camera(self, camera_id: str) -> None:
        self._request(f"/api/v1/cameras/{camera_id}/reconnect", "POST", {})

    def import_cameras(self, csv_bytes: bytes) -> dict:
        return self._json(self._request("/api/v1/cameras/import", "POST", raw=csv_bytes, content_type="text/csv; charset=utf-8")[1])

    def set_incident_status(self, public_id: str, status: str) -> dict:
        return self._json(self._request(f"/api/v1/incidents/{public_id}/status", "POST", {"status": status})[1])

    def stream_clip_to_file(
        self, public_id: str, destination: str | Path, cancelled: Callable[[], bool] | None = None
    ) -> Path:
        """Copy the server's chunked MP4 response to a local temp file for Qt playback."""
        url = self.base_url + f"/api/v1/incidents/{public_id}/clip"
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}", "Accept": "video/mp4"})
        path = Path(destination)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response, path.open("wb") as output:
                if response.headers.get_content_type() != "video/mp4":
                    raise ServerConnectionError("The server did not return an MP4 clip.")
                while True:
                    if cancelled is not None and cancelled():
                        raise ServerConnectionError("Clip download cancelled.")
                    chunk = response.read(CLIP_CHUNK_BYTES)
                    if not chunk:
                        break
                    output.write(chunk)
        except urllib.error.HTTPError as error:
            path.unlink(missing_ok=True)
            if error.code == 401:
                raise ServerConnectionError("Access denied: the token is wrong or server access has been lost.") from None
            if error.code == 404:
                raise ServerConnectionError("No saved clip exists for this incident.") from None
            raise ServerConnectionError(f"The server rejected the clip request (HTTP {error.code}).") from None
        except ServerConnectionError:
            path.unlink(missing_ok=True)
            raise
        except (OSError, urllib.error.URLError, TimeoutError) as error:
            path.unlink(missing_ok=True)
            if isinstance(error, urllib.error.URLError) and isinstance(error.reason, (ssl.SSLCertVerificationError, ssl.CertificateError)):
                raise ServerConnectionError(f"HTTPS certificate verification failed: {error.reason}") from None
            raise ServerConnectionError("The incident clip could not be downloaded from the server.") from None
        return path
