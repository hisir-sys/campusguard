from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from PySide6.QtCore import QStandardPaths

from campusguard.settings import AppSettings, CameraConfig


def application_data_dir() -> Path:
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if location:
        return Path(location)
    return Path.home() / "AppData" / "Roaming" / "CampusGuard"


class Repository:
    """SQLite-backed storage for cameras, incidents, alerts, notifications, and settings."""

    def __init__(self, database_path: Path | None = None, footage_dir: Path | None = None) -> None:
        self.data_dir = application_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = database_path or self.data_dir / "campusguard.db"
        self._footage_dir = Path(footage_dir).expanduser() if footage_dir is not None else None
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @property
    def footage_dir(self) -> Path:
        directory = self._footage_dir or (self.data_dir / "footage")
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS cameras (
            camera_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_address TEXT NOT NULL,
            ai_enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_id TEXT UNIQUE NOT NULL,
            camera_id TEXT NOT NULL,
            camera_name TEXT NOT NULL,
            happened_at TEXT NOT NULL,
            event TEXT NOT NULL,
            confidence REAL NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'NEW',
            footage_path TEXT
        );
        CREATE INDEX IF NOT EXISTS incidents_camera_time
            ON incidents(camera_id, happened_at DESC);
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER UNIQUE NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
            acknowledged INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sequences (
            name TEXT PRIMARY KEY,
            value INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS remote_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_server_id TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_incident_id TEXT NOT NULL,
            camera_id TEXT NOT NULL,
            camera_name TEXT NOT NULL,
            happened_at TEXT NOT NULL,
            event TEXT NOT NULL,
            confidence REAL NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            has_footage INTEGER NOT NULL DEFAULT 0,
            source_seq INTEGER NOT NULL DEFAULT 0,
            received_at TEXT NOT NULL,
            UNIQUE(source_server_id, source_incident_id)
        );
        CREATE INDEX IF NOT EXISTS remote_alerts_time ON remote_alerts(happened_at DESC);
        CREATE TABLE IF NOT EXISTS peer_state (
            server_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            last_seq INTEGER NOT NULL DEFAULT 0,
            state TEXT NOT NULL DEFAULT 'disconnected',
            last_seen TEXT,
            last_error TEXT NOT NULL DEFAULT ''
        );
        """
        with self._lock, self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(schema)
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(incidents)"
                ).fetchall()
            }
            if "footage_path" not in columns:
                connection.execute(
                    "ALTER TABLE incidents ADD COLUMN footage_path TEXT"
                )
            if "sync_seq" not in columns:
                # Phase 6: every create/status/footage change gets a new sequence number so
                # other servers can ask "what changed since N?" after a reconnect.
                connection.execute(
                    "ALTER TABLE incidents ADD COLUMN sync_seq INTEGER NOT NULL DEFAULT 0"
                )
                connection.execute("UPDATE incidents SET sync_seq = id WHERE sync_seq = 0")
                top = connection.execute("SELECT COALESCE(MAX(sync_seq), 0) AS top FROM incidents").fetchone()["top"]
                connection.execute(
                    "INSERT INTO sequences(name, value) VALUES ('sync', ?) "
                    "ON CONFLICT(name) DO UPDATE SET value = MAX(value, excluded.value)",
                    (int(top),),
                )

    def list_cameras(self) -> list[CameraConfig]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM cameras ORDER BY created_at, camera_id"
            ).fetchall()
        return [
            CameraConfig(
                camera_id=row["camera_id"],
                name=row["name"],
                source_type=row["source_type"],
                source_address=row["source_address"],
                ai_enabled=bool(row["ai_enabled"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def add_camera(
        self,
        name: str,
        source_type: str,
        source_address: str,
        ai_enabled: bool = True,
    ) -> CameraConfig:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock, self._connection() as connection:
            latest_camera = int(
                connection.execute(
                    "SELECT COALESCE(MAX(CAST(SUBSTR(camera_id, 5) AS INTEGER)), 0) "
                    "FROM cameras"
                ).fetchone()[0]
            )
            sequence_row = connection.execute(
                "SELECT value FROM sequences WHERE name = 'camera_id'"
            ).fetchone()
            previous_sequence = int(sequence_row["value"]) if sequence_row else 0
            next_sequence = max(latest_camera, previous_sequence) + 1
            camera_id = f"CAM-{next_sequence:03d}"
            connection.execute(
                "INSERT INTO sequences(name, value) VALUES ('camera_id', ?) "
                "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
                (next_sequence,),
            )
            connection.execute(
                """INSERT INTO cameras
                   (camera_id, name, source_type, source_address, ai_enabled, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (camera_id, name, source_type, source_address, int(ai_enabled), created_at),
            )
        return CameraConfig(
            camera_id=camera_id,
            name=name,
            source_type=source_type,
            source_address=source_address,
            ai_enabled=ai_enabled,
            created_at=created_at,
        )

    def remove_camera(self, camera_id: str) -> None:
        with self._lock, self._connection() as connection:
            connection.execute("DELETE FROM cameras WHERE camera_id = ?", (camera_id,))

    def set_camera_ai(self, camera_id: str, enabled: bool) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE cameras SET ai_enabled = ? WHERE camera_id = ?",
                (int(enabled), camera_id),
            )

    def get_settings(self) -> AppSettings:
        with self._lock, self._connection() as connection:
            rows = connection.execute("SELECT key, value FROM settings").fetchall()
        values: dict[str, Any] = {}
        for row in rows:
            try:
                values[row["key"]] = json.loads(row["value"])
            except (TypeError, json.JSONDecodeError):
                continue
        return AppSettings.from_dict(values)

    def save_settings(self, settings: AppSettings) -> None:
        with self._lock, self._connection() as connection:
            connection.executemany(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                [(key, json.dumps(value)) for key, value in settings.to_dict().items()],
            )

    @staticmethod
    def _next_sync_seq(connection: sqlite3.Connection) -> int:
        row = connection.execute("SELECT value FROM sequences WHERE name = 'sync'").fetchone()
        value = (int(row["value"]) if row else 0) + 1
        connection.execute(
            "INSERT INTO sequences(name, value) VALUES ('sync', ?) "
            "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
            (value,),
        )
        return value

    def create_incident(
        self,
        camera: CameraConfig,
        event: str,
        confidence: float,
        severity: str,
        cooldown_seconds: int,
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        happened_at = now.isoformat(timespec="seconds")
        with self._lock, self._connection() as connection:
            latest = connection.execute(
                "SELECT happened_at, status FROM incidents WHERE camera_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (camera.camera_id,),
            ).fetchone()
            if latest and latest["status"] != "RESOLVED":
                last_time = datetime.fromisoformat(latest["happened_at"])
                if now - last_time < timedelta(seconds=max(0, cooldown_seconds)):
                    return None

            cursor = connection.execute(
                """INSERT INTO incidents
                   (public_id, camera_id, camera_name, happened_at, event, confidence, severity)
                   VALUES ('PENDING', ?, ?, ?, ?, ?, ?)""",
                (
                    camera.camera_id,
                    camera.name,
                    happened_at,
                    event,
                    float(confidence),
                    severity,
                ),
            )
            row_id = int(cursor.lastrowid)
            public_id = f"INC-{row_id:05d}"
            connection.execute(
                "UPDATE incidents SET public_id = ?, sync_seq = ? WHERE id = ?",
                (public_id, self._next_sync_seq(connection), row_id),
            )
            connection.execute(
                "INSERT INTO alerts(incident_id, acknowledged) VALUES (?, 0)",
                (row_id,),
            )
            connection.execute(
                "INSERT INTO notifications(kind, message, created_at) VALUES (?, ?, ?)",
                ("incident_detected", f"{event} — {camera.name} ({confidence:.1%})", happened_at),
            )
            connection.execute(
                "INSERT INTO notifications(kind, message, created_at) VALUES (?, ?, ?)",
                ("alert_generated", f"{severity} alert raised for {camera.name}", happened_at),
            )
            row = connection.execute(
                "SELECT * FROM incidents WHERE id = ?", (row_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_incidents(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM incidents ORDER BY id DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_incident(self, public_id: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM incidents WHERE public_id = ?", (public_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_incidents_after(self, after_id: int, limit: int = 200) -> list[dict[str, Any]]:
        """Incidents newer than a row id, oldest first (for clients that poll)."""
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM incidents WHERE id > ? ORDER BY id ASC LIMIT ?",
                (int(after_id), max(1, limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def purge_incidents_older_than(self, days: float) -> int:
        """Delete incidents (and their alerts) older than `days`; returns how many."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        with self._lock, self._connection() as connection:
            removed = connection.execute(
                "DELETE FROM incidents WHERE happened_at < ?", (cutoff,)
            ).rowcount
            connection.execute("DELETE FROM notifications WHERE created_at < ?", (cutoff,))
            connection.execute("DELETE FROM remote_alerts WHERE happened_at < ?", (cutoff,))
        return int(removed)

    def forget_footage_paths(self, paths: list[str]) -> None:
        """Clear the footage link of incidents whose clip file was deleted."""
        if not paths:
            return
        with self._lock, self._connection() as connection:
            for path in paths:
                connection.execute(
                    "UPDATE incidents SET footage_path = NULL, sync_seq = ? WHERE footage_path = ?",
                    (self._next_sync_seq(connection), str(path)),
                )

    def attach_incident_footage(self, public_id: str, footage_path: str) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE incidents SET footage_path = ?, sync_seq = ? WHERE public_id = ?",
                (str(footage_path), self._next_sync_seq(connection), public_id),
            )

    def update_incident_assessment(
        self, public_id: str, confidence: float, severity: str
    ) -> None:
        """Update an existing incident as the same detection's peak confidence rises."""
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE incidents SET confidence = ?, severity = ? WHERE public_id = ?",
                (float(confidence), severity, public_id),
            )

    def update_incident_status(self, public_id: str, status: str) -> None:
        allowed = {"NEW", "ACKNOWLEDGED", "RESOLVED", "CONFIRMED", "DISMISSED", "FALSE_ALARM"}
        if status not in allowed:
            raise ValueError(f"Unsupported incident status: {status}")
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT id FROM incidents WHERE public_id = ?", (public_id,)
            ).fetchone()
            if row is None:
                return
            connection.execute(
                "UPDATE incidents SET status = ?, sync_seq = ? WHERE public_id = ?",
                (status, self._next_sync_seq(connection), public_id),
            )
            # Any explicit operator decision acknowledges the associated alert.
            if status != "NEW":
                connection.execute(
                    "UPDATE alerts SET acknowledged = 1 WHERE incident_id = ?", (row["id"],)
                )

    # ------------------------------------------------------------------
    # Phase 6: alert synchronisation between servers of one school
    # ------------------------------------------------------------------
    def list_sync_events(self, since_seq: int, limit: int = 200) -> tuple[list[dict[str, Any]], int]:
        """Locally detected incidents changed after ``since_seq`` (oldest change first)."""
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT public_id, camera_id, camera_name, happened_at, event, confidence, severity, "
                "status, footage_path, sync_seq FROM incidents WHERE sync_seq > ? ORDER BY sync_seq ASC LIMIT ?",
                (max(0, int(since_seq)), max(1, int(limit))),
            ).fetchall()
            latest = connection.execute("SELECT value FROM sequences WHERE name = 'sync'").fetchone()
        events = [
            {
                "incident_id": row["public_id"], "camera_id": row["camera_id"], "camera_name": row["camera_name"],
                "happened_at": row["happened_at"], "event": row["event"], "confidence": row["confidence"],
                "severity": row["severity"], "status": row["status"],
                "has_footage": bool(row["footage_path"]), "seq": int(row["sync_seq"]),
            }
            for row in rows
        ]
        return events, int(latest["value"]) if latest else 0

    def upsert_remote_alert(self, source_server_id: str, source_name: str, event: dict[str, Any]) -> str:
        """Store/refresh one alert received from another server. Returns new|updated|same."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        incident_id = str(event["incident_id"])
        seq = int(event["seq"])
        values = (
            str(event["camera_id"]), str(event["camera_name"]), str(event["happened_at"]), str(event["event"]),
            float(event["confidence"]), str(event["severity"]), str(event["status"]),
            1 if event.get("has_footage") else 0,
        )
        with self._lock, self._connection() as connection:
            existing = connection.execute(
                "SELECT id, source_seq FROM remote_alerts WHERE source_server_id = ? AND source_incident_id = ?",
                (source_server_id, incident_id),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """INSERT INTO remote_alerts(source_server_id, source_name, source_incident_id, camera_id,
                       camera_name, happened_at, event, confidence, severity, status, has_footage,
                       source_seq, received_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (source_server_id, source_name, incident_id, *values, seq, now),
                )
                return "new"
            if seq <= int(existing["source_seq"]):
                return "same"        # duplicate or out-of-order delivery: never counted twice
            connection.execute(
                """UPDATE remote_alerts SET source_name = ?, camera_id = ?, camera_name = ?, happened_at = ?,
                   event = ?, confidence = ?, severity = ?, status = ?, has_footage = ?, source_seq = ?
                   WHERE id = ?""",
                (source_name, *values, seq, existing["id"]),
            )
            return "updated"

    def list_remote_alerts(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM remote_alerts ORDER BY happened_at DESC, id DESC LIMIT ?", (max(1, int(limit)),)
            ).fetchall()
        return [dict(row) for row in rows]

    def alert_counts(self) -> dict[str, Any]:
        """Local and remote totals, split by severity (used for the school-wide overview)."""
        with self._lock, self._connection() as connection:
            local = connection.execute("SELECT severity, COUNT(*) AS n FROM incidents GROUP BY severity").fetchall()
            remote = connection.execute(
                "SELECT source_server_id, severity, COUNT(*) AS n FROM remote_alerts "
                "GROUP BY source_server_id, severity"
            ).fetchall()
        local_by = {row["severity"]: int(row["n"]) for row in local}
        remote_by: dict[str, dict[str, int]] = {}
        for row in remote:
            remote_by.setdefault(row["source_server_id"], {})[row["severity"]] = int(row["n"])
        return {"local": local_by, "remote": remote_by}

    def get_peer_state(self, server_id: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute("SELECT * FROM peer_state WHERE server_id = ?", (server_id,)).fetchone()
        return dict(row) if row else None

    def list_peer_states(self) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            rows = connection.execute("SELECT * FROM peer_state ORDER BY name").fetchall()
        return [dict(row) for row in rows]

    def save_peer_state(self, server_id: str, name: str, address: str, last_seq: int, state: str,
                        last_seen: str | None, last_error: str = "") -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT INTO peer_state(server_id, name, address, last_seq, state, last_seen, last_error)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(server_id) DO UPDATE SET name = excluded.name, address = excluded.address,
                   last_seq = excluded.last_seq, state = excluded.state,
                   last_seen = COALESCE(excluded.last_seen, peer_state.last_seen), last_error = excluded.last_error""",
                (server_id, name, address, int(last_seq), state, last_seen, last_error[:300]),
            )

    def delete_peer_state(self, server_id: str) -> None:
        with self._lock, self._connection() as connection:
            connection.execute("DELETE FROM peer_state WHERE server_id = ?", (server_id,))

    def prune_peer_states(self, keep_addresses: set[str]) -> None:
        """Forget peers that were removed from the configuration (and their alerts)."""
        with self._lock, self._connection() as connection:
            rows = connection.execute("SELECT server_id, address FROM peer_state").fetchall()
            for row in rows:
                if row["address"].rstrip("/").lower() not in keep_addresses:
                    connection.execute("DELETE FROM peer_state WHERE server_id = ?", (row["server_id"],))
                    connection.execute("DELETE FROM remote_alerts WHERE source_server_id = ?", (row["server_id"],))

    def list_alerts(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                """SELECT a.id AS alert_id, a.acknowledged, i.*
                   FROM alerts AS a
                   JOIN incidents AS i ON i.id = a.incident_id
                   ORDER BY i.id DESC LIMIT ?""",
                (max(1, limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def acknowledge_alert(self, alert_id: int) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,)
            )

    def add_notification(self, kind: str, message: str) -> None:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO notifications(kind, message, created_at) VALUES (?, ?, ?)",
                (kind, message, created_at),
            )

    def list_notifications(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM notifications ORDER BY id DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_notifications(self) -> None:
        """Delete operator notifications without changing incidents or alerts."""
        with self._lock, self._connection() as connection:
            connection.execute("DELETE FROM notifications")

    def clear_incident_footage_paths(self) -> None:
        with self._lock, self._connection() as connection:
            connection.execute("UPDATE incidents SET footage_path = NULL")

    def incident_count(self) -> int:
        with self._lock, self._connection() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM incidents").fetchone()[0])

    def open_incident_count(self) -> int:
        """Count incidents that still need operator review or follow-up."""
        with self._lock, self._connection() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM incidents WHERE status NOT IN ('RESOLVED', 'DISMISSED', 'FALSE_ALARM')"
                ).fetchone()[0]
            )

    def clear_all_incidents_alerts_notifications(self) -> None:
        """Delete incident history, alerts, and operator notifications together."""
        with self._lock, self._connection() as connection:
            connection.execute("DELETE FROM alerts")
            connection.execute("DELETE FROM incidents")
            connection.execute("DELETE FROM notifications")
            connection.execute(
                "DELETE FROM sqlite_sequence WHERE name = 'incidents'"
            )

    def active_alert_count(self) -> int:
        with self._lock, self._connection() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM alerts WHERE acknowledged = 0"
                ).fetchone()[0]
            )