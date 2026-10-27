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
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QFrame,
)

from campusguard.server.client import RemoteServerClient
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

    def __init__(self, client_provider: Callable[[], RemoteServerClient], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._client_provider = client_provider
        self._worker: _ServerTask | None = None
        self._pending_success: Callable[[object], None] | None = None
        self._closing = False
        self._stop_after_worker = False
        self._watched: set[str] = set()
        self._cards: dict[str, _CameraCard] = {}
        self._clip_paths: set[Path] = set()
        self._clip_cancel = threading.Event()
        self._live_dialog: _LiveFeedDialog | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 112)
        root.setSpacing(16)
        root.addWidget(make_page_title(
            "School server",
            "Remote camera health, live snapshots, incidents and saved clips. Local camera mode remains separate.",
        ))
        status_row = QHBoxLayout()
        self.connection_status = QLabel("Not connected. Check the server address and token in Settings.")
        self.connection_status.setWordWrap(True)
        self.connection_status.setProperty("muted", True)
        status_row.addWidget(self.connection_status, 1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        status_row.addWidget(self.refresh_button)
        root.addLayout(status_row)

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
                    "alerts": alerts, "snapshots": snapshots, "watched": visible}

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
        self.connection_status.style().unpolish(self.connection_status)
        self.connection_status.style().polish(self.connection_status)
        self._last_cameras = list(data["cameras"])
        self._sync_camera_cards(data["cameras"])
        for camera_id, jpeg in data["snapshots"].items():
            card = self._cards.get(camera_id)
            if card is not None:
                card.set_snapshot(jpeg)
        self._watched = set(data["watched"])
        self._populate_table(self.incidents_table, data["incidents"], allow_status_actions=True)
        self._populate_table(self.alerts_table, data["alerts"], allow_status_actions=True)

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
