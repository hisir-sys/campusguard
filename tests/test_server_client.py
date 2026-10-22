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

    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == "/api/v1/status" and self.headers.get("Authorization") != f"Bearer {self.token}":
            self.send_response(401)
            self.end_headers()
            return
        body = json.dumps({"version": "test", "cameras": {"total": 0}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def fake_server():
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
    client = RemoteServerClient("http://127.0.0.1:1", TOKEN, timeout=0.5, retries=0)
    with pytest.raises(ServerConnectionError, match="unreachable|timed out"):
        client.test_connection()
