"""Phase 6: alert-only synchronisation between the servers of one school.

Every server keeps detecting, recording and storing footage on its own. Servers
only exchange small alert records (no video, no streams, no model files):

* ``SyncFacade``  - answers the ``/sync/*`` API calls from this server's own data.
* ``PeerSync``    - background thread that *pulls* new/changed alerts from every
                    configured peer, with a per-peer cursor, so a reconnect simply
                    continues from where it stopped.

Alerts are keyed by (source server id, source incident id), so the same event can
arrive any number of times and is still counted once. A sync failure never touches
detection: the thread catches everything and only updates peer status.
"""
from __future__ import annotations

import hashlib
import json
import logging
import ssl
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

from campusguard.server.client import RemoteServerClient, ServerConnectionError

log = logging.getLogger("campusguard.server.sync")

PAGE_SIZE = 200
POLL_SECONDS = 5.0
MAX_BACKOFF_SECONDS = 60.0
PEER_TIMEOUT_SECONDS = 4.0

STATE_ONLINE = "online"
STATE_CATCHING_UP = "catching_up"
STATE_DISCONNECTED = "disconnected"
STATE_UNAUTHORIZED = "unauthorized"
STATE_WRONG_SCHOOL = "wrong_school"
STATE_CONNECTING = "connecting"


def school_id_from_email(email: str) -> str:
    """Stable school identifier derived from the website account when none is configured."""
    return "school-" + hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:16]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _by_severity(counts: dict[str, int]) -> dict[str, int]:
    return {str(key): int(value) for key, value in counts.items()}


class SyncFacade:
    """Read-only sync view of this server, used by the HTTP API."""

    def __init__(self, repository, server_id: str, server_name: str, school_id: str, version: str,
                 peers: Callable[[], list[dict]]) -> None:
        self.repository = repository
        self.server_id = server_id
        self.server_name = server_name
        self.school_id = school_id
        self.version = version
        self._peers = peers

    def identity(self) -> dict:
        return {"server_id": self.server_id, "server_name": self.server_name,
                "school_id": self.school_id, "version": self.version}

    def events(self, since: int, limit: int) -> dict:
        events, latest = self.repository.list_sync_events(since, limit)
        return {**self.identity(), "events": events, "latest_seq": latest}

    def _peer_rows(self) -> list[dict]:
        configured = {p["address"].rstrip("/").lower(): p for p in self._peers()}
        rows = []
        known: set[str] = set()
        for state in self.repository.list_peer_states():
            key = state["address"].rstrip("/").lower()
            if key not in configured:
                continue
            known.add(key)
            rows.append({"server_id": state["server_id"], "name": state["name"], "address": state["address"],
                         "state": state["state"], "last_seen": state["last_seen"], "last_error": state["last_error"]})
        for key, peer in configured.items():      # configured but never reached yet
            if key not in known:
                rows.append({"server_id": "", "name": peer["name"], "address": peer["address"],
                             "state": STATE_CONNECTING, "last_seen": None, "last_error": ""})
        return rows

    def overview(self) -> dict:
        counts = self.repository.alert_counts()
        local_total = sum(counts["local"].values())
        school_by: dict[str, int] = dict(counts["local"])
        servers = []
        for peer in self._peer_rows():
            by = counts["remote"].get(peer["server_id"], {})
            total = sum(by.values())
            for severity, number in by.items():
                school_by[severity] = school_by.get(severity, 0) + number
            servers.append({**peer, "total": total, "by_severity": _by_severity(by)})
        school_total = local_total + sum(item["total"] for item in servers)
        return {
            **self.identity(),
            "local": {"total": local_total, "by_severity": _by_severity(counts["local"])},
            "peers": servers,
            "school_wide": {"total": school_total, "by_severity": _by_severity(school_by)},
        }

    def remote_alerts(self, limit: int) -> list[dict]:
        addresses = {s["server_id"]: s["address"] for s in self._peer_rows()}
        result = []
        for row in self.repository.list_remote_alerts(limit):
            result.append({
                "source_server_id": row["source_server_id"], "source_name": row["source_name"],
                "source_address": addresses.get(row["source_server_id"], ""),
                "incident_id": row["source_incident_id"], "camera_id": row["camera_id"],
                "camera_name": row["camera_name"], "happened_at": row["happened_at"], "event": row["event"],
                "confidence": row["confidence"], "severity": row["severity"], "status": row["status"],
                "has_footage": bool(row["has_footage"]), "footage_location": "source_server",
            })
        return result


class PeerSync:
    """Pulls alerts from every configured peer. Isolated from detection by design."""

    def __init__(self, repository, facade: SyncFacade, peers: Callable[[], list[dict]],
                 token_for: Callable[[str], str], on_new_alert: Callable[[dict, dict], None] | None = None,
                 poll_seconds: float = POLL_SECONDS, client_factory=None) -> None:
        self.repository = repository
        self.facade = facade
        self._peers = peers
        self._token_for = token_for
        self._on_new_alert = on_new_alert
        self.poll_seconds = poll_seconds
        self._client_factory = client_factory or self._default_client
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._failures: dict[str, int] = {}
        self._next_try: dict[str, float] = {}

    # -- lifecycle --------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="peer-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.sync_once()
            except Exception as error:         # never let sync take anything else down
                log.error("peer sync cycle failed: %r", error)
            self._stop.wait(self.poll_seconds)

    # -- one pass over all peers -------------------------------------------
    @staticmethod
    def _default_client(address: str, token: str, ca_file: str) -> "_PeerClient":
        return _PeerClient(address, token, ca_file)

    def sync_once(self) -> None:
        peers = self._peers()
        self.repository.prune_peer_states({p["address"].rstrip("/").lower() for p in peers})
        for peer in peers:
            if self._stop.is_set():
                return
            key = peer["address"].rstrip("/").lower()
            if time.monotonic() < self._next_try.get(key, 0.0):
                continue
            try:
                self._sync_peer(peer)
                self._failures[key] = 0
                self._next_try.pop(key, None)
            except Exception as error:         # one bad peer must not block the others
                failures = self._failures.get(key, 0) + 1
                self._failures[key] = failures
                self._next_try[key] = time.monotonic() + min(MAX_BACKOFF_SECONDS, self.poll_seconds * (2 ** min(failures, 4)))
                self._record_failure(peer, error)

    def _record_failure(self, peer: dict, error: Exception) -> None:
        message = str(error) or type(error).__name__
        state = STATE_DISCONNECTED
        if isinstance(error, _PeerRejected):
            state = error.state
        existing = None
        for row in self.repository.list_peer_states():
            if row["address"].rstrip("/").lower() == peer["address"].rstrip("/").lower():
                existing = row
                break
        if existing is None:
            # Never reached: keep a placeholder keyed by address so the UI can still show the reason.
            placeholder = "pending-" + hashlib.sha256(peer["address"].lower().encode()).hexdigest()[:12]
            self.repository.save_peer_state(placeholder, peer["name"], peer["address"], 0, state, None, message)
        else:
            self.repository.save_peer_state(existing["server_id"], existing["name"], existing["address"],
                                            existing["last_seq"], state, None, message)

    def _sync_peer(self, peer: dict) -> None:
        token = self._token_for(peer["address"])
        if not token:
            raise _PeerRejected(STATE_UNAUTHORIZED, "No access token is stored for this server.")
        client = self._client_factory(peer["address"], token, peer.get("ca_file", ""))
        identity = client.sync_identity()
        peer_id = str(identity.get("server_id", ""))
        if not peer_id:
            raise _PeerRejected(STATE_DISCONNECTED, "The server did not identify itself.")
        if peer_id == self.facade.server_id:
            raise _PeerRejected(STATE_DISCONNECTED, "This address points back to this server.")
        if identity.get("school_id") != self.facade.school_id:
            raise _PeerRejected(STATE_WRONG_SCHOOL, "That server belongs to a different CampusGuard school ID.")
        name = str(identity.get("server_name") or peer["name"])
        # Drop any placeholder row created while the peer was unreachable.
        for row in self.repository.list_peer_states():
            if row["server_id"].startswith("pending-") and row["address"].rstrip("/").lower() == peer["address"].rstrip("/").lower():
                self.repository.delete_peer_state(row["server_id"])
        state_row = self.repository.get_peer_state(peer_id)
        cursor = int(state_row["last_seq"]) if state_row else 0
        while not self._stop.is_set():
            batch = client.sync_events(cursor, PAGE_SIZE)
            latest = int(batch.get("latest_seq", 0))
            if latest < cursor:
                # The other server's database was reset: start over; duplicates are harmless.
                cursor = 0
                continue
            events = batch.get("events", [])
            for event in events:
                result = self.repository.upsert_remote_alert(peer_id, name, event)
                cursor = max(cursor, int(event["seq"]))
                if result == "new" and self._on_new_alert is not None:
                    try:
                        self._on_new_alert({"server_id": peer_id, "name": name, "address": peer["address"]}, event)
                    except Exception as error:
                        log.error("alert callback failed: %r", error)
            self.repository.save_peer_state(peer_id, name, peer["address"], cursor,
                                            STATE_CATCHING_UP if len(events) >= PAGE_SIZE else STATE_ONLINE,
                                            _now(), "")
            if len(events) < PAGE_SIZE:
                break
        self.repository.save_peer_state(peer_id, name, peer["address"], cursor, STATE_ONLINE, _now(), "")


class _PeerRejected(Exception):
    def __init__(self, state: str, message: str) -> None:
        super().__init__(message)
        self.state = state


class _PeerClient:
    """Minimal timeout-bounded client for the /sync endpoints of another server."""

    def __init__(self, address: str, token: str, ca_file: str = "") -> None:
        self._client = RemoteServerClient(address, token, timeout=PEER_TIMEOUT_SECONDS, retries=0)
        self._context = None
        if ca_file and self._client.base_url.startswith("https://"):
            self._context = ssl.create_default_context(cafile=ca_file)

    def _get(self, path: str) -> dict:
        try:
            if self._context is None:
                return self._client._json(self._client._request(path)[1])
            request = urllib.request.Request(
                self._client.base_url + path, headers={"Authorization": f"Bearer {self._client.token}"}
            )
            with urllib.request.urlopen(request, timeout=PEER_TIMEOUT_SECONDS, context=self._context) as response:
                return json.loads(response.read(8 * 1024 * 1024).decode("utf-8"))
        except ServerConnectionError as error:
            if "token is wrong" in str(error) or "denied" in str(error).lower():
                raise _PeerRejected(STATE_UNAUTHORIZED, str(error)) from None
            raise
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise _PeerRejected(STATE_UNAUTHORIZED, "The other server rejected the access token.") from None
            raise

    def sync_identity(self) -> dict:
        return self._get("/api/v1/sync/identity")

    def sync_events(self, since: int, limit: int) -> dict:
        return self._get(f"/api/v1/sync/events?since={int(since)}&limit={int(limit)}")
