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

    def __init__(self, database_path: Path | None = None) -> None:
        self.data_dir = application_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = database_path or self.data_dir / "campusguard.db"
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
            status TEXT NOT NULL DEFAULT 'NEW'
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
        """
        with self._lock, self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(schema)

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
                "SELECT happened_at FROM incidents WHERE camera_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (camera.camera_id,),
            ).fetchone()
            if latest:
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
                "UPDATE incidents SET public_id = ? WHERE id = ?",
                (public_id, row_id),
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

    def update_incident_status(self, public_id: str, status: str) -> None:
        if status not in {"NEW", "ACKNOWLEDGED", "RESOLVED"}:
            raise ValueError(f"Unsupported incident status: {status}")
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE incidents SET status = ? WHERE public_id = ?",
                (status, public_id),
            )

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

    def incident_count(self) -> int:
        with self._lock, self._connection() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM incidents").fetchone()[0])

    def active_alert_count(self) -> int:
        with self._lock, self._connection() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM alerts WHERE acknowledged = 0"
                ).fetchone()[0]
            )