from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from campusguard.settings import CameraConfig, CameraStats
from campusguard.storage import Repository
from campusguard.ui.common import CameraPreview, make_card, set_tone
from campusguard.ui.icons import IconLabel

# Color of the little dot next to each notification, by notification "kind".
# "" means a neutral grey dot.
NOTIFICATION_TONES = {
    "camera_connected": "good",
    "camera_added": "good",
    "camera_disconnected": "",
    "camera_removed": "",
    "incident_detected": "bad",
    "alert_generated": "bad",
}


class DashboardPage(QWidget):
    camera_selected = Signal(str)
    view_alerts_requested = Signal()  # the "View Alerts" link in Notifications

    def __init__(self, repository: Repository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self._cameras: dict[str, CameraConfig] = {}
        self._stats: dict[str, CameraStats] = {}
        self._ai_states: dict[str, tuple[str, float | None]] = {}
        self._model_statuses: dict[str, dict[str, str]] = {}
        self._tiles: dict[str, CameraPreview] = {}
        self._empty_label: QLabel | None = None
        self._camera_grid: QGridLayout | None = None

        # What the camera workers told us about each model (True = loaded).
        self._runtime_loaded: dict[str, bool] = {}
        self._runtime_messages: dict[str, str] = {}
        self._device_text: str | None = None
        self._settings = None
        self._notification_key: tuple = ()

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # Row 1: three equal cards side by side.
        overview = QHBoxLayout()
        overview.setSpacing(16)
        overview.addWidget(self._build_engine_card(), 1)
        overview.addWidget(self._build_stats_card(), 1)
        overview.addWidget(self._build_notifications_card(), 1)
        root.addLayout(overview)

        # Row 2: the live camera grid takes all the remaining height.
        root.addWidget(self._build_network_card(), 1)

    # ------------------------------------------------------------------
    # Building the cards
    # ------------------------------------------------------------------
    def _build_engine_card(self) -> QFrame:
        frame, layout = make_card("AI Engine", icon="cpu")
        self.engine_values: dict[str, QLabel] = {}
        rows = (
            ("detector", "Person detector"),
            ("pose", "Pose model"),
            ("fight", "Fight classifier"),
            ("status", "Status"),
            ("device", "Compute device"),
            ("threshold", "Confidence threshold"),
            ("detection", "Detection"),
        )
        for key, text in rows:
            row = QHBoxLayout()
            name = QLabel(text)
            name.setProperty("kvlabel", True)
            value = QLabel("—")
            value.setProperty("kvvalue", True)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(name)
            row.addStretch(1)
            row.addWidget(value)
            layout.addLayout(row)
            self.engine_values[key] = value
        layout.addStretch(1)
        return frame

    def _build_stats_card(self) -> QFrame:
        frame, layout = make_card("System Stats", icon="server")
        grid = QGridLayout()
        grid.setSpacing(12)
        online_tile, self.online_value = self._stat_tile("video", "good", "Cameras Online")
        offline_tile, self.offline_value = self._stat_tile("video-off", "muted", "Cameras Offline")
        incident_tile, self.incident_value = self._stat_tile("file-warning", "warn", "Total Incidents")
        alert_tile, self.alert_value = self._stat_tile("shield-alert", "bad", "Active Alerts")
        grid.addWidget(online_tile, 0, 0)
        grid.addWidget(offline_tile, 0, 1)
        grid.addWidget(incident_tile, 1, 0)
        grid.addWidget(alert_tile, 1, 1)
        layout.addLayout(grid, 1)
        return frame

    @staticmethod
    def _stat_tile(icon: str, tone: str, caption: str) -> tuple[QFrame, QLabel]:
        tile = QFrame()
        tile.setProperty("tile", True)
        box = QVBoxLayout(tile)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(4)
        box.addWidget(IconLabel(icon, 20, tone), 0, Qt.AlignmentFlag.AlignLeft)
        value = QLabel("0")
        value.setStyleSheet("font-size: 24pt; font-weight: 700;")
        label = QLabel(caption)
        label.setProperty("muted", True)
        box.addWidget(value)
        box.addWidget(label)
        return tile, value

    def _build_notifications_card(self) -> QFrame:
        frame, layout = make_card("Notifications", icon="bell")
        view_alerts = QPushButton("View Alerts")
        view_alerts.setProperty("link", True)
        view_alerts.setCursor(Qt.CursorShape.PointingHandCursor)
        view_alerts.clicked.connect(lambda _checked=False: self.view_alerts_requested.emit())
        frame.header_layout.addWidget(view_alerts)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumHeight(170)
        scroll.viewport().setAutoFillBackground(False)  # let the card color show through
        content = QWidget()
        self._notification_layout = QVBoxLayout(content)
        self._notification_layout.setContentsMargins(0, 0, 4, 0)
        self._notification_layout.setSpacing(12)
        self._notification_layout.addStretch(1)  # keeps rows packed at the top
        scroll.setWidget(content)
        content.setAutoFillBackground(False)  # setWidget() turns the fill on; undo it
        layout.addWidget(scroll, 1)
        return frame

    def _build_network_card(self) -> QFrame:
        frame, layout = make_card("Live Network", icon="activity")
        self.camera_count_pill = QLabel("0 cameras")
        self.camera_count_pill.setProperty("pill", True)
        # Insert before the header's trailing stretch so it sits next to the title.
        frame.header_layout.insertWidget(frame.header_layout.count() - 1, self.camera_count_pill)

        self.feed_scroll = QScrollArea()
        self.feed_scroll.setWidgetResizable(True)
        self.feed_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.feed_scroll.viewport().setAutoFillBackground(False)
        self.feed_content = QWidget()
        self._camera_grid = QGridLayout(self.feed_content)
        self._camera_grid.setContentsMargins(0, 0, 0, 0)
        self._camera_grid.setSpacing(12)
        self.feed_scroll.setWidget(self.feed_content)
        self.feed_content.setAutoFillBackground(False)
        layout.addWidget(self.feed_scroll, 1)
        return frame

    # ------------------------------------------------------------------
    # Camera grid
    # ------------------------------------------------------------------
    def sync_cameras(self, cameras: list[CameraConfig]) -> None:
        new_ids = {camera.camera_id for camera in cameras}
        for camera_id in set(self._tiles) - new_ids:
            tile = self._tiles.pop(camera_id)
            self._camera_grid.removeWidget(tile)
            tile.deleteLater()
            self._stats.pop(camera_id, None)
            self._ai_states.pop(camera_id, None)
            self._model_statuses.pop(camera_id, None)
        self._cameras = {camera.camera_id: camera for camera in cameras}

        for camera in cameras:
            tile = self._tiles.get(camera.camera_id)
            if tile is None:
                tile = CameraPreview(camera)
                tile.selected.connect(self.camera_selected.emit)
                self._tiles[camera.camera_id] = tile
            else:
                tile.set_camera(camera)
            self._update_tile(camera.camera_id)

        while self._camera_grid.count():
            item = self._camera_grid.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is self._empty_label:
                widget.deleteLater()
                self._empty_label = None
        for index, camera in enumerate(cameras):
            self._camera_grid.addWidget(self._tiles[camera.camera_id], index // 2, index % 2)

        count = len(cameras)
        self.camera_count_pill.setText(f"{count} camera{'' if count == 1 else 's'}")

        if not cameras:
            self._empty_label = QLabel(
                "No cameras configured. Add an external USB, RTSP, HTTP/MJPEG, or IP camera "
                "from the Cameras page."
            )
            self._empty_label.setWordWrap(True)
            self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._empty_label.setProperty("muted", True)
            self._camera_grid.addWidget(self._empty_label, 0, 0)

    def update_camera_stats(self, camera_id: str, stats: CameraStats) -> None:
        self._stats[camera_id] = stats
        self._update_tile(camera_id)

    def update_frame(
        self,
        camera_id: str,
        image,
        state: str,
        confidence: float | None,
    ) -> None:
        if camera_id not in self._tiles:
            return
        self._ai_states[camera_id] = (state, confidence)
        self._tiles[camera_id].set_frame(QPixmap.fromImage(image))

    # ------------------------------------------------------------------
    # AI Engine card
    # ------------------------------------------------------------------
    def update_model_status(self, camera_id: str, component: str, message: str) -> None:
        """Called whenever a camera worker reports on a model or the device."""
        self._model_statuses.setdefault(camera_id, {})[component] = message
        if component in {"detector", "pose", "fight"}:
            self._runtime_loaded[component] = message.upper().startswith("READY")
            self._runtime_messages[component] = message
        elif component == "device":
            self._device_text = message
        self._refresh_engine()

    def update_settings(self, confidence_threshold: float, detection_enabled: bool) -> None:
        self._set_value("threshold", f"{confidence_threshold:.0%}")
        self._set_value("detection", "Enabled" if detection_enabled else "Disabled")

    def update_model_configuration(self, settings) -> None:
        self._settings = settings
        self.update_settings(settings.confidence_threshold, settings.detection_enabled)
        self._refresh_engine()

    def _refresh_engine(self) -> None:
        """Recompute the model rows, the Status row and the device row."""
        settings = self._settings
        if settings is None:
            return

        paths = {
            "detector": settings.detector_model_path,
            "pose": settings.pose_model_path,
            "fight": settings.fight_model_path,
        }
        loaded = 0   # models a camera worker confirmed as loaded
        present = 0  # model files that exist on disk and have not failed
        for key, configured in paths.items():
            path = Path(configured).expanduser() if configured.strip() else None
            exists = bool(path and path.is_file())
            runtime = self._runtime_loaded.get(key)  # True / False / None (unknown yet)
            name = path.name if path else ""
            tooltip = self._runtime_messages.get(key, "")
            if runtime is True:
                loaded += 1
                present += 1
                self._set_value(key, name or "Loaded", "good", tooltip)
            elif runtime is False or not exists:
                self._set_value(key, "Not loaded", "warn", tooltip or f"File not found: {configured}")
            else:
                present += 1
                self._set_value(key, name, "", "Found on disk; loads when a camera starts")

        if loaded == 3:
            status = ("ACTIVE", "good")
        elif loaded > 0:
            status = ("PARTIAL", "warn")
        elif self._runtime_loaded:
            status = ("NOT LOADED", "bad")
        elif present == 3:
            status = ("READY", "")
        elif present > 0:
            status = ("PARTIAL", "warn")
        else:
            status = ("NO MODELS", "warn")
        self._set_value("status", *status)

        self._set_value("device", self._device_text or settings.device.upper())

    def _set_value(self, key: str, text: str, tone: str = "", tooltip: str = "") -> None:
        label = self.engine_values[key]
        label.setText(text)
        label.setToolTip(tooltip)
        set_tone(label, tone)

    # ------------------------------------------------------------------
    # Stats + notifications (refreshed by a timer in MainWindow)
    # ------------------------------------------------------------------
    def refresh_summary(self) -> None:
        online = sum(
            self._stats.get(camera_id, CameraStats()).status == "LIVE"
            for camera_id in self._cameras
        )
        offline = max(0, len(self._cameras) - online)
        self.online_value.setText(str(online))
        self.offline_value.setText(str(offline))
        self.incident_value.setText(str(self.repository.incident_count()))
        self.alert_value.setText(str(self.repository.active_alert_count()))
        self._show_notifications(self.repository.list_notifications(8))

    def _show_notifications(self, rows: list[dict]) -> None:
        # This runs every 1.5 s. Only rebuild when something actually changed,
        # otherwise the list would flicker and lose its scroll position.
        key = tuple((row["created_at"], row["message"]) for row in rows)
        if key == self._notification_key:
            return
        self._notification_key = key

        layout = self._notification_layout
        while layout.count() > 1:  # keep the trailing stretch
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

        if not rows:
            empty = QLabel("No notifications yet.")
            empty.setProperty("muted", True)
            layout.insertWidget(0, empty)
            return

        for index, row in enumerate(rows):
            layout.insertWidget(index, self._notification_row(row))

    @staticmethod
    def _notification_row(row: dict) -> QWidget:
        widget = QWidget()
        outer = QHBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        dot = QLabel("●")
        tone = NOTIFICATION_TONES.get(row.get("kind", ""), "")
        if tone:
            set_tone(dot, tone)
        else:
            dot.setProperty("muted", True)
        outer.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(2)
        message = QLabel(row["message"])
        message.setWordWrap(True)
        stamp = QLabel(row["created_at"][11:19])  # HH:MM:SS part of the ISO timestamp
        stamp.setProperty("muted", True)
        stamp.setStyleSheet("font-size: 8pt;")
        text.addWidget(message)
        text.addWidget(stamp)
        outer.addLayout(text, 1)
        return widget

    def _update_tile(self, camera_id: str) -> None:
        camera = self._cameras.get(camera_id)
        tile = self._tiles.get(camera_id)
        if not camera or not tile:
            return
        stats = self._stats.get(camera_id, CameraStats())
        tile.set_status(stats, camera.ai_enabled)
