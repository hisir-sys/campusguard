"""Remote school-server viewer. Network operations always run in QThread workers."""
from __future__ import annotations

import tempfile
import threading
import uuid
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QImage, QPixmap
try:  # Multimedia can be missing or fail to load; never let that stop the app starting.
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    MULTIMEDIA_AVAILABLE = True
except Exception:  # pragma: no cover - depends on the Qt install
    QAudioOutput = QMediaPlayer = QVideoWidget = None  # type: ignore[assignment,misc]
    MULTIMEDIA_AVAILABLE = False
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QInputDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QFrame,
)

from campusguard.server.client import RemoteServerClient
from campusguard.ui.theme import get_palette, rgba
from campusguard.ui.common import make_page_title


class _LiveStreamWorker(QThread):
    frame_ready = Signal(bytes)
    status_changed = Signal(str)

    def __init__(self, client_provider: Callable[[], RemoteServerClient], camera_id: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._client_provider = client_provider
        self._camera_id = camera_id

    def run(self) -> None:
        while not self.isInterruptionRequested():
            try:
                self.status_changed.emit("Connecting to live camera…")
                client = self._client_provider()
                client.stream_frames(
                    self._camera_id, self.frame_ready.emit,
                    self.isInterruptionRequested,
                )
            except Exception as error:
                if self.isInterruptionRequested():
                    break
                self.status_changed.emit(f"Reconnecting: {error}")
                self.msleep(800)


class _LiveFeedDialog(QDialog):
    def __init__(self, client_provider: Callable[[], RemoteServerClient],
                 camera: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.camera = camera
        self._last_image: QImage | None = None
        self.setWindowTitle(f"CampusGuard Live · {camera.get('name', camera.get('camera_id', 'Camera'))}")
        self.resize(1200, 760)
        self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel(f"{camera.get('name', 'Camera')}  ·  {camera.get('camera_id', '')}")
        title.setStyleSheet("font-size: 16px; font-weight: 750;")
        self.status = QLabel("Starting live feed…")
        self.status.setProperty("muted", True)
        header.addWidget(title, 1)
        header.addWidget(self.status)
        layout.addLayout(header)
        self.frame = QLabel("Connecting to camera…")
        self.frame.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.frame.setMinimumSize(640, 360)
        self.frame.setStyleSheet("background: #05070b; border-radius: 10px;")
        layout.addWidget(self.frame, 1)
        footer = QHBoxLayout()
        footer.addStretch(1)
        close_button = QPushButton("Close live view")
        close_button.clicked.connect(self.close)
        footer.addWidget(close_button)
        layout.addLayout(footer)
        self._worker = _LiveStreamWorker(client_provider, str(camera.get("camera_id", "")), self)
        self._worker.frame_ready.connect(self._show_frame)
        self._worker.status_changed.connect(self.status.setText)
        self._worker.start()

    def _show_frame(self, jpeg: bytes) -> None:
        image = QImage.fromData(jpeg, "JPEG")
        if image.isNull():
            self.status.setText("Received an invalid video frame.")
            return
        self._last_image = image
        self.frame.setPixmap(QPixmap.fromImage(image).scaled(
            self.frame.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))
        self.status.setText("LIVE · selected camera")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._last_image is not None:
            self.frame.setPixmap(QPixmap.fromImage(self._last_image).scaled(
                self.frame.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))

    def closeEvent(self, event) -> None:
        self._worker.requestInterruption()
        self._worker.wait(12000)
        super().closeEvent(event)


class _ClickablePreview(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _ServerTask(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, operation: Callable[[], object], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._operation = operation

    def run(self) -> None:
        try:
            self.succeeded.emit(self._operation())
        except Exception as error:
            self.failed.emit(str(error))


class _CameraCard(QFrame):
    remove_requested = Signal(str)
    reconnect_requested = Signal(str)
    live_requested = Signal(str)

    def __init__(self, camera: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.camera = camera
        self.setProperty("card", True)
        self.setMinimumHeight(132)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(14)
        self.preview = _ClickablePreview("Preview paused")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedSize(200, 112)
        self.preview.setProperty("muted", True)
        self.preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview.setToolTip("Click to open the selected camera's live view")
        self.preview.clicked.connect(lambda: self.live_requested.emit(self.camera_id))
        self.preview.setStyleSheet("border: 1px solid rgba(255,255,255,0.12); border-radius: 8px;")
        row.addWidget(self.preview)
        details = QVBoxLayout()
        details.setSpacing(5)
        self.name = QLabel()
        self.name.setStyleSheet("font-size: 14px; font-weight: 700;")
        self.health = QLabel("CONNECTING")
        self.health.setProperty("muted", True)
        self.metrics = QLabel("")
        self.metrics.setProperty("muted", True)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setProperty("muted", True)
        details.addWidget(self.name)
        details.addWidget(self.health)
        details.addWidget(self.metrics)
        details.addWidget(self.message, 1)
        row.addLayout(details, 1)
        actions = QVBoxLayout()
        self.reconnect_button = QPushButton("Reconnect")
        self.remove_button = QPushButton("Remove")
        self.reconnect_button.clicked.connect(lambda: self.reconnect_requested.emit(self.camera_id))
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self.camera_id))
        actions.addWidget(self.reconnect_button)
        actions.addWidget(self.remove_button)
        actions.addStretch(1)
        row.addLayout(actions)
        self.set_camera(camera)

    @property
    def camera_id(self) -> str:
        return str(self.camera.get("camera_id", ""))

    def set_camera(self, camera: dict) -> None:
        self.camera = camera
        self.name.setText(f"{camera.get('name', 'Camera')}  ·  {self.camera_id}")
        self.health.setText(str(camera.get("health") or camera.get("status") or "connecting").upper())
        fps = camera.get("fps")
        resolution = camera.get("resolution") or "N/A"
        self.metrics.setText(f"FPS: {fps if fps is not None else 'N/A'}   ·   Resolution: {resolution}")
        self.message.setText(str(camera.get("message") or ""))

    def set_snapshot(self, jpeg: bytes | None) -> None:
        if not jpeg:
            if self.preview.pixmap() is None:
                self.preview.setText("Waiting for preview…")
            return
        image = QImage.fromData(jpeg, "JPEG")
        if image.isNull():
            self.preview.setText("Invalid camera snapshot")
            return
        self.preview.setPixmap(QPixmap.fromImage(image).scaled(
            self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))


class ServerViewerPage(QWidget):
    """Remote camera, incident and alert views. All network work stays off the UI thread."""

    def __init__(self, client_provider: Callable[[], RemoteServerClient], parent: QWidget | None = None,
                 peer_tokens=None) -> None:
        super().__init__(parent)
        self._base_client_provider = client_provider
        self._client_provider = self._active_client
        # Optional object with load_peer_token(address)/save_peer_token(address, token) (Credential Manager).
        self._peer_tokens = peer_tokens
        self._override: dict | None = None          # {"name", "address", "token", "save"} while viewing another server
        self._focus_incident: str | None = None
        self._overview: dict | None = None
        self._worker: _ServerTask | None = None
        self._pending_success: Callable[[object], None] | None = None
        self._closing = False
        self._stop_after_worker = False
        self._watched: set[str] = set()
        self._cards: dict[str, _CameraCard] = {}
        self._clip_paths: set[Path] = set()
        self._clip_cancel = threading.Event()
        self._live_dialog: _LiveFeedDialog | None = None
        self._known_incident_ids: set[str] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 112)
        root.setSpacing(16)
        root.addWidget(make_page_title(
            "School server",
            "All school cameras, clickable live views, incidents and saved clips. Local camera mode remains separate.",
        ))
        self.viewing_banner = QFrame()
        self.viewing_banner.setProperty("card", True)
        banner_row = QHBoxLayout(self.viewing_banner)
        banner_row.setContentsMargins(12, 8, 12, 8)
        self.viewing_label = QLabel("")
        self.viewing_label.setWordWrap(True)
        self.back_button = QPushButton("Back to my server")
        self.back_button.clicked.connect(self.leave_other_server)
        banner_row.addWidget(self.viewing_label, 1)
        banner_row.addWidget(self.back_button)
        self.viewing_banner.hide()
        root.addWidget(self.viewing_banner)
        status_row = QHBoxLayout()
        self.connection_status = QLabel("Not connected. Check the server address and token in Settings.")
        self.connection_status.setWordWrap(True)
        self.connection_status.setProperty("muted", True)
        status_row.addWidget(self.connection_status, 1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        status_row.addWidget(self.refresh_button)
        root.addLayout(status_row)
        self.remote_alert_banner = QLabel("")
        self.remote_alert_banner.setWordWrap(True)
        self.remote_alert_banner.setVisible(False)
        self.remote_alert_banner.setStyleSheet("padding: 10px 14px; border: 1px solid #F07838; border-radius: 10px; font-weight: 700;")
        root.addWidget(self.remote_alert_banner)
        self._remote_alert_timer = QTimer(self)
        self._remote_alert_timer.setSingleShot(True)
        self._remote_alert_timer.timeout.connect(self.remote_alert_banner.hide)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.cameras_tab = QWidget()
        camera_root = QVBoxLayout(self.cameras_tab)
        camera_root.setContentsMargins(4, 8, 4, 4)
        toolbar = QHBoxLayout()
        self.add_button = QPushButton("Add camera")
        self.import_button = QPushButton("Import CSV")
        self.add_button.clicked.connect(self._add_camera_dialog)
        self.import_button.clicked.connect(self._import_csv)
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.import_button)
        toolbar.addStretch(1)
        camera_root.addLayout(toolbar)
        self.camera_scroll = QScrollArea()
        self.camera_scroll.setWidgetResizable(True)
        self.camera_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.camera_content = QWidget()
        self.camera_layout = QVBoxLayout(self.camera_content)
        self.camera_layout.setContentsMargins(2, 2, 8, 8)
        self.camera_layout.setSpacing(8)
        self.empty_cameras_label = QLabel("No server cameras configured. Add a camera or import a CSV file.")
        self.empty_cameras_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_cameras_label.setWordWrap(True)
        self.empty_cameras_label.setProperty("muted", True)
        self.camera_layout.addWidget(self.empty_cameras_label)
        self.camera_layout.addStretch(1)
        self.camera_scroll.setWidget(self.camera_content)
        camera_root.addWidget(self.camera_scroll, 1)
        self.tabs.addTab(self.cameras_tab, "Cameras")
        self.incidents_table = self._make_table()
        self.tabs.addTab(self.incidents_table, "Incidents")
        self.alerts_table = self._make_table()
        self.tabs.addTab(self.alerts_table, "Alerts")

        # School-wide alert overview shared by the school's servers (alerts only, never video).
        self.school_tab = QWidget()
        school_root = QVBoxLayout(self.school_tab)
        school_root.setContentsMargins(4, 8, 4, 4)
        school_root.setSpacing(8)
        self.school_summary = QLabel("School-wide totals appear here once this server is connected.")
        self.school_summary.setWordWrap(True)
        self.school_summary.setStyleSheet("font-size: 14px; font-weight: 700;")
        self.school_detail = QLabel("")
        self.school_detail.setWordWrap(True)
        self.school_detail.setProperty("muted", True)
        school_root.addWidget(self.school_summary)
        school_root.addWidget(self.school_detail)
        self.servers_table = QTableWidget(0, 4)
        self.servers_table.setHorizontalHeaderLabels(["Server", "Address", "Status", "Alerts"])
        self.servers_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.servers_table.verticalHeader().setVisible(False)
        self.servers_table.horizontalHeader().setStretchLastSection(True)
        self.servers_table.setMaximumHeight(170)
        school_root.addWidget(self.servers_table)
        self.remote_table = QTableWidget(0, 7)
        self.remote_table.setHorizontalHeaderLabels(
            ["ID", "Source server · camera", "Event", "Confidence", "Severity", "Status", "Actions"])
        self.remote_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.remote_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.remote_table.setAlternatingRowColors(True)
        self.remote_table.verticalHeader().setVisible(False)
        self.remote_table.horizontalHeader().setSectionResizeMode(1, self.remote_table.horizontalHeader().ResizeMode.Stretch)
        school_root.addWidget(self.remote_table, 1)
        self.tabs.addTab(self.school_tab, "School")

        # Multimedia backends can be unavailable on headless PCs and CI.
        # Create the player only when a user actually opens a saved clip.
        self._root_layout = root
        self.video_widget: QVideoWidget | None = None
        self._audio: QAudioOutput | None = None
        self._player: QMediaPlayer | None = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(2500)
        self._poll_timer.timeout.connect(self.refresh)

    @staticmethod
    def _make_table() -> QTableWidget:
        table = QTableWidget(0, 7)
        table.setHorizontalHeaderLabels(["ID", "Camera", "Event", "Confidence", "Severity", "Status", "Actions"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, table.horizontalHeader().ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, table.horizontalHeader().ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, table.horizontalHeader().ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(6, table.horizontalHeader().ResizeMode.ResizeToContents)
        return table

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._closing:
            self._poll_timer.start()
            QTimer.singleShot(0, self.refresh)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._poll_timer.stop()
        if self._worker is not None and self._worker.isRunning():
            self._stop_after_worker = True
        elif self._watched:
            self._stop_snapshots()

    def refresh(self) -> None:
        if self._closing or (self._worker is not None and self._worker.isRunning()):
            return
        visible = {
            camera_id for camera_id, card in self._cards.items()
            if card.isVisible() and not card.visibleRegion().isEmpty()
        }
        previously_watched = set(self._watched)
        self._watched.update(visible)  # track attempts too, so a hide/failure can stop them

        def operation():
            client = self._client_provider()
            status = client.test_connection()
            cameras = client.list_cameras()
            incidents = client.list_incidents()
            alerts = client.list_alerts()
            try:        # older servers have no sync endpoints; the School tab simply stays empty
                overview, remote_alerts = client.sync_overview(), client.sync_alerts(200)
            except Exception:
                overview, remote_alerts = None, []
            for camera_id in previously_watched - visible:
                try:
                    client.stop_snapshot(camera_id)
                except Exception:
                    pass
            snapshots = {}
            for camera_id in sorted(visible):
                try:
                    snapshots[camera_id] = client.snapshot(camera_id)
                except Exception as error:
                    if "not ready yet" not in str(error).lower():
                        snapshots[camera_id] = None
            return {"status": status, "cameras": cameras, "incidents": incidents,
                    "alerts": alerts, "snapshots": snapshots, "watched": visible,
                    "overview": overview, "remote_alerts": remote_alerts}

        self._run(operation, self._apply_refresh)

    def _run(self, operation: Callable[[], object], success: Callable[[object], None]) -> None:
        if self._closing or (self._worker is not None and self._worker.isRunning()):
            return
        worker = _ServerTask(operation, self)
        self._worker = worker
        self._pending_success = success
        worker.succeeded.connect(self._worker_succeeded)
        worker.failed.connect(self._worker_failed)
        worker.finished.connect(self._worker_finished)
        self.refresh_button.setEnabled(False)
        worker.start()

    def _worker_succeeded(self, value: object) -> None:
        callback, self._pending_success = self._pending_success, None
        if callback is not None and not self._closing:
            callback(value)

    def _worker_failed(self, message: str) -> None:
        self.connection_status.setText(f"Server unreachable or access unavailable. Retrying automatically. {message}")
        self.connection_status.setProperty("muted", False)
        warn = get_palette().warn
        self.connection_status.setStyleSheet(
            f"color: {get_palette().text}; background: {rgba(warn, 30)}; "
            f"border: 1px solid {rgba(warn, 110)}; border-radius: 10px; padding: 9px 12px;"
        )
        self.connection_status.style().unpolish(self.connection_status)
        self.connection_status.style().polish(self.connection_status)

    def _worker_finished(self) -> None:
        worker, self._worker = self._worker, None
        self.refresh_button.setEnabled(True)
        if worker is not None:
            worker.deleteLater()
        if self._stop_after_worker and not self._closing:
            self._stop_after_worker = False
            self._stop_snapshots()

    def _apply_refresh(self, result: object) -> None:
        data = result
        counts = data["status"].get("cameras", {})
        self.connection_status.setText(
            f"Connected · {len(data['cameras'])} cameras · {counts.get('ok', 0)} ok · "
            f"{counts.get('stalled', 0)} stalled · {counts.get('offline', 0)} offline · "
            f"{counts.get('connecting', 0)} connecting"
        )
        self.connection_status.setProperty("muted", True)
        self.connection_status.setStyleSheet("")
        self.connection_status.style().unpolish(self.connection_status)
        self.connection_status.style().polish(self.connection_status)
        self._last_cameras = list(data["cameras"])
        incoming_ids = {str(row.get("public_id", "")) for row in data["incidents"] if row.get("public_id")}
        if self._known_incident_ids is None:
            # Seed from the first successful poll so opening the viewer does not
            # replay alarms for historical incidents.
            self._known_incident_ids = incoming_ids
        else:
            new_rows = [row for row in data["incidents"]
                        if row.get("public_id") and str(row.get("public_id")) not in self._known_incident_ids]
            self._known_incident_ids.update(incoming_ids)
            actionable = []
            for row in new_rows:
                try:
                    score = float(row.get("confidence", 0) or 0)
                    score = score * 100.0 if score <= 1.0 else score
                except (TypeError, ValueError):
                    score = 0.0
                if score >= 70.0:
                    actionable.append((score, row))
            if actionable:
                score, latest = max(actionable, key=lambda item: item[0])
                severity = str(latest.get("severity", "ALERT")).upper()
                camera_name = str(latest.get("camera_name", "Camera"))
                event = str(latest.get("event", "Fight detected"))
                public_id = str(latest.get("public_id", ""))
                self.remote_alert_banner.setText(
                    f"{severity} · {event} · {camera_name} · {score:.1f}% confidence · {public_id}"
                )
                accent = "#FF343F" if score >= 95 else "#F07838" if score >= 85 else "#D9A441"
                self.remote_alert_banner.setStyleSheet(
                    f"padding: 10px 14px; border: 1px solid {accent}; border-left: 4px solid {accent}; "
                    "border-radius: 10px; font-weight: 700;"
                )
                self.remote_alert_banner.show()
                self._remote_alert_timer.start(15000 if score >= 95 else 7000 if score >= 85 else 5000)
                QApplication.beep()
        self._sync_camera_cards(data["cameras"])
        for camera_id, jpeg in data["snapshots"].items():
            card = self._cards.get(camera_id)
            if card is not None:
                card.set_snapshot(jpeg)
        self._watched = set(data["watched"])
        self._populate_table(self.incidents_table, data["incidents"], allow_status_actions=True)
        self._populate_table(self.alerts_table, data["alerts"], allow_status_actions=True)
        self._populate_school(data.get("overview"), data.get("remote_alerts", []))
        if self._override and self._override.get("save") and self._peer_tokens is not None:
            try:        # the token worked: remember it for next time
                self._peer_tokens.save_peer_token(self._override["address"], self._override["token"])
            except Exception:
                pass
            self._override["save"] = False
        self._apply_focus()

    # -- Phase 6: school-wide alerts and the remote-footage experience -----------------
    def _active_client(self) -> RemoteServerClient:
        if self._override is not None:
            return RemoteServerClient(self._override["address"], self._override["token"], timeout=1.0, retries=0)
        return self._base_client_provider()

    def _populate_school(self, overview: dict | None, remote_alerts: list[dict]) -> None:
        self._overview = overview
        if not overview:
            self.school_summary.setText("School-wide alerts are not available from this server.")
            self.school_detail.setText("")
            self.servers_table.setRowCount(0)
            self.remote_table.setRowCount(0)
            return
        school, local = overview.get("school_wide", {}), overview.get("local", {})
        peers = overview.get("peers", [])
        name = overview.get("server_name") or "This server"
        remote_total = sum(int(p.get("total", 0)) for p in peers)
        self.school_summary.setText(f"School-wide fight alerts: {school.get('total', 0)}")
        severities = ", ".join(f"{key}: {value}" for key, value in sorted(school.get("by_severity", {}).items())) or "none"
        self.school_detail.setText(
            f"{local.get('total', 0)} detected by {name} (this server) · {remote_total} reported by other servers · "
            f"by severity: {severities}"
        )
        self.servers_table.setRowCount(len(peers))
        for row, peer in enumerate(peers):
            state = str(peer.get("state", "")).replace("_", " ")
            if peer.get("last_error") and peer.get("state") != "online":
                state += f" · {peer['last_error']}"
            for col, value in enumerate((peer.get("name", ""), peer.get("address", ""), state, str(peer.get("total", 0)))):
                self.servers_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.remote_table.setUpdatesEnabled(False)
        self.remote_table.setRowCount(len(remote_alerts))
        for row, alert in enumerate(remote_alerts):
            try:
                confidence = f"{float(alert.get('confidence', 0) or 0):.0%}"
            except (TypeError, ValueError):
                confidence = ""
            values = [str(alert.get("incident_id", "")),
                      f"{alert.get('source_name', '?')} · {alert.get('camera_name', '')}",
                      str(alert.get("event", "")), confidence, str(alert.get("severity", "")),
                      str(alert.get("status", ""))]
            for col, value in enumerate(values):
                self.remote_table.setItem(row, col, QTableWidgetItem(value))
            if alert.get("has_footage"):
                button = QPushButton("View footage", self.remote_table)
                button.clicked.connect(lambda _checked=False, item=dict(alert): self.show_remote_footage_notice(item))
                self.remote_table.setCellWidget(row, 6, button)
            else:
                self.remote_table.setItem(row, 6, QTableWidgetItem("No footage"))
                self.remote_table.removeCellWidget(row, 6)
        self.remote_table.setUpdatesEnabled(True)

    def show_remote_footage_notice(self, alert: dict) -> None:
        """Footage of a remote alert lives on its source server: never pretend a local copy exists."""
        source = str(alert.get("source_name") or "the source server")
        address = str(alert.get("source_address") or "")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Footage is stored on another server")
        if address:
            box.setText(
                f"This incident's footage is not stored on the current machine.\n\n"
                f"Open {source} to review the incident and its recording."
            )
            box.setInformativeText(f"Source: {source} · {alert.get('camera_name', '')}\nAddress: {address}")
            go = box.addButton(f"Go to {source}", QMessageBox.ButtonRole.AcceptRole)
        else:
            box.setText(
                f"This incident's footage is not stored on the current machine.\n\n"
                f"It is stored on {source}. Open that server's CampusGuard to review the recording."
            )
            box.setInformativeText("This server does not know the other server's network address. Check the peer settings.")
            go = None
        box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        self._remote_footage_box = box
        box.exec()
        if go is not None and box.clickedButton() is go:
            self.go_to_server(source, address, str(alert.get("incident_id", "")))

    def go_to_server(self, name: str, address: str, incident_id: str = "") -> bool:
        token = ""
        if self._peer_tokens is not None:
            try:
                token = self._peer_tokens.load_peer_token(address)
            except Exception:
                token = ""
        save = False
        if not token:
            token, accepted = QInputDialog.getText(
                self, f"Connect to {name}", f"Access token for {name} ({address}):", QLineEdit.EchoMode.Password)
            if not accepted or not token.strip():
                return False
            token, save = token.strip(), True
        try:
            RemoteServerClient(address, token)      # validates the address/token shape before switching
        except Exception as error:
            QMessageBox.warning(self, "Cannot open server", str(error))
            return False
        self._override = {"name": name, "address": address, "token": token, "save": save}
        self._focus_incident = incident_id or None
        self._watched.clear()
        self.viewing_label.setText(f"Viewing {name} ({address}). Cameras, incidents and clips below come from that server.")
        self.viewing_banner.show()
        self.refresh()
        return True

    def leave_other_server(self) -> None:
        self._override = None
        self._focus_incident = None
        self._watched.clear()
        self.viewing_banner.hide()
        self.tabs.setCurrentWidget(self.school_tab)
        self.refresh()

    def _apply_focus(self) -> None:
        if not self._focus_incident:
            return
        for row in range(self.incidents_table.rowCount()):
            item = self.incidents_table.item(row, 0)
            if item is not None and item.text() == self._focus_incident:
                self.tabs.setCurrentWidget(self.incidents_table)
                self.incidents_table.selectRow(row)
                self._focus_incident = None
                return

    def _sync_camera_cards(self, cameras: list[dict]) -> None:
        present = {str(camera.get("camera_id", "")) for camera in cameras}
        self.empty_cameras_label.setVisible(not present)
        for camera_id in list(self._cards):
            if camera_id not in present:
                card = self._cards.pop(camera_id)
                self.camera_layout.removeWidget(card)
                card.deleteLater()
        for camera in cameras:
            camera_id = str(camera.get("camera_id", ""))
            card = self._cards.get(camera_id)
            if card is None:
                card = _CameraCard(camera, self.camera_content)
                card.remove_requested.connect(self._remove_camera)
                card.reconnect_requested.connect(self._reconnect_camera)
                card.live_requested.connect(self._open_live_feed)
                self._cards[camera_id] = card
                self.camera_layout.insertWidget(max(0, self.camera_layout.count() - 1), card)
            else:
                card.set_camera(camera)

    def _populate_table(
        self, table: QTableWidget, rows: list[dict], *, allow_status_actions: bool = False
    ) -> None:
        table.setUpdatesEnabled(False)
        table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            public_id = str(row.get("public_id", ""))
            try:
                confidence = float(row.get("confidence", 0) or 0)
            except (TypeError, ValueError):
                confidence = 0.0
            values = [public_id, str(row.get("camera_name", "")), str(row.get("event", "")),
                      f"{confidence:.0%}", str(row.get("severity", "")), str(row.get("status", ""))]
            for col, value in enumerate(values):
                table.setItem(index, col, QTableWidgetItem(value))
            actions = QWidget(table)
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(3, 2, 3, 2)
            if allow_status_actions:
                status_select = QComboBox(actions)
                for label, status in (("Confirm", "CONFIRMED"), ("Dismiss", "DISMISSED"),
                                      ("False alarm", "FALSE_ALARM"), ("Resolve", "RESOLVED")):
                    status_select.addItem(label, status)
                update_button = QPushButton("Update", actions)
                update_button.clicked.connect(
                    lambda _checked=False, pid=public_id, combo=status_select:
                    self._update_incident_status(pid, str(combo.currentData()))
                )
                action_layout.addWidget(status_select)
                action_layout.addWidget(update_button)
            if row.get("has_footage") and public_id:
                play = QPushButton("Play clip", actions)
                play.clicked.connect(lambda _checked=False, pid=public_id: self._play_clip(pid))
                action_layout.addWidget(play)
            if action_layout.count():
                table.setCellWidget(index, 6, actions)
            else:
                table.removeCellWidget(index, 6)
        table.setUpdatesEnabled(True)

    def _update_incident_status(self, public_id: str, status: str) -> None:
        self._run(lambda: self._client_provider().set_incident_status(public_id, status), lambda _result: self.refresh())

    def _ensure_media_player(self) -> bool:
        if self._player is not None:
            return True
        if not MULTIMEDIA_AVAILABLE:
            return False
        try:
            video_widget = QVideoWidget(self)
            video_widget.setMinimumHeight(180)
            video_widget.setMaximumHeight(300)
            audio = QAudioOutput(self)
            player = QMediaPlayer(self)
            player.setAudioOutput(audio)
            player.setVideoOutput(video_widget)
        except Exception:
            return False
        self._root_layout.addWidget(video_widget)
        self.video_widget, self._audio, self._player = video_widget, audio, player
        return True

    def _play_clip(self, public_id: str) -> None:
        destination = Path(tempfile.gettempdir()) / f"campusguard-{uuid.uuid4().hex}.mp4"
        self._clip_cancel.clear()
        def success(path: object) -> None:
            clip_path = Path(path)
            self._clip_paths.add(clip_path)
            if not self._ensure_media_player():
                self.connection_status.setText("Video playback is unavailable on this PC. The clip was downloaded to: " + str(clip_path))
                return
            assert self.video_widget is not None and self._player is not None
            self.video_widget.show()
            self._player.setSource(QUrl.fromLocalFile(str(clip_path)))
            self._player.play()
        self.connection_status.setText(f"Downloading incident {public_id} in chunks for playback…")
        self._run(lambda: self._client_provider().stream_clip_to_file(
            public_id, destination, cancelled=self._clip_cancel.is_set
        ), success)

    def _add_camera_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Add server camera")
        form = QFormLayout(dialog)
        name = QLineEdit()
        source_type = QComboBox()
        for value in ("RTSP", "HTTP", "MJPEG", "IP", "USB"):
            source_type.addItem(value, value)
        address = QLineEdit()
        address.setPlaceholderText("rtsp://camera-address/substream")
        username = QLineEdit()
        password = QLineEdit()
        password.setEchoMode(QLineEdit.EchoMode.Password)
        ai_enabled = QCheckBox("Enable AI analysis")
        ai_enabled.setChecked(True)
        form.addRow("Camera name", name)
        form.addRow("Source type", source_type)
        form.addRow("Stream address", address)
        form.addRow("Username", username)
        form.addRow("Password", password)
        form.addRow("", ai_enabled)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not name.text().strip() or not address.text().strip():
            QMessageBox.warning(self, "Camera details missing", "Enter both a camera name and stream address.")
            return
        spec = (name.text().strip(), str(source_type.currentData()), address.text().strip(),
                username.text(), password.text(), ai_enabled.isChecked())
        self._run(lambda: self._client_provider().add_camera(*spec), lambda _result: self.refresh())

    def _open_live_feed(self, camera_id: str) -> None:
        camera = next(
            (item for item in getattr(self, "_last_cameras", [])
             if str(item.get("camera_id", "")) == camera_id),
            None,
        )
        if camera is None:
            card = self._cards.get(camera_id)
            camera = card.camera if card is not None else {"camera_id": camera_id, "name": camera_id}
        if self._live_dialog is not None:
            return
        # Pause list polling while the dedicated stream worker owns this camera.
        self._poll_timer.stop()
        self._watched.clear()
        dialog = _LiveFeedDialog(self._client_provider, camera, self)
        self._live_dialog = dialog
        try:
            dialog.exec()
        finally:
            self._live_dialog = None
            if not self._closing:
                self._poll_timer.start()
                QTimer.singleShot(0, self.refresh)

    def _remove_camera(self, camera_id: str) -> None:
        answer = QMessageBox.question(self, "Remove camera", f"Remove camera {camera_id} from the school server?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run(lambda: self._client_provider().remove_camera(camera_id), lambda _result: self.refresh())

    def _reconnect_camera(self, camera_id: str) -> None:
        self._run(lambda: self._client_provider().reconnect_camera(camera_id), lambda _result: self.refresh())

    def _import_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import server cameras", "", "CSV files (*.csv);;All files (*.*)")
        if not path:
            return
        try:
            raw = Path(path).read_bytes()
        except OSError as error:
            QMessageBox.warning(self, "CSV import failed", str(error))
            return
        if not raw or len(raw) > 2 * 1024 * 1024:
            QMessageBox.warning(self, "CSV import failed", "Choose a non-empty CSV file no larger than 2 MB.")
            return
        self._run(lambda: self._client_provider().import_cameras(raw), self._show_import_result)

    def _show_import_result(self, result: object) -> None:
        errors = result.get("errors", [])
        summary = f"Added {result.get('added', 0)} cameras."
        if errors:
            summary += "\n\nRejected rows:\n" + "\n".join(
                f"Row {item.get('row') or '?'}: {item.get('error', 'Invalid row')}" for item in errors[:20]
            )
        QMessageBox.information(self, "CSV import result", summary)
        self.refresh()

    def _stop_snapshots(self) -> None:
        cameras = set(self._watched)
        self._watched.clear()
        if not cameras or self._closing:
            return
        def operation():
            client = self._client_provider()
            for camera_id in cameras:
                try:
                    client.stop_snapshot(camera_id)
                except Exception:
                    pass
        self._run(operation, lambda _result: None)

    def shutdown(self) -> None:
        self._closing = True
        self._clip_cancel.set()
        self._poll_timer.stop()
        if self._player is not None:
            self._player.stop()
            self._player.setSource(QUrl())
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait(9000)
        self._worker = None
        for path in list(self._clip_paths):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        self._clip_paths.clear()
