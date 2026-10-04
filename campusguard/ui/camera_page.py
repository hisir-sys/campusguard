from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from campusguard.settings import CameraConfig, CameraStats
from campusguard.ui.common import CameraFormDialog, make_page_title, set_status_label


class CameraRow(QFrame):
    remove_requested = Signal(str)
    reconnect_requested = Signal(str)
    ai_changed = Signal(str, bool)

    def __init__(self, camera: CameraConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.camera = camera
        self.setProperty("card", True)
        self.setObjectName("cameraRow")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.setSpacing(16)

        # Camera identity
        identity = QVBoxLayout()
        identity.setSpacing(5)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        name = QLabel(camera.name)
        name.setStyleSheet("font-size: 15px; font-weight: 700;")
        title_row.addWidget(name)

        self.source_badge = QLabel(camera.source_type.upper())
        self.source_badge.setStyleSheet(
            "font-size: 10px; font-weight: 700; padding: 3px 7px; "
            "border-radius: 5px; background: rgba(255,255,255,0.08);"
        )
        title_row.addWidget(self.source_badge)
        title_row.addStretch(1)
        identity.addLayout(title_row)

        address = QLabel(
            f"{camera.camera_id}  ·  {camera.source_address}"
        )
        address.setProperty("muted", True)
        address.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        address.setWordWrap(False)
        identity.addWidget(address)

        layout.addLayout(identity, 1)

        # Status
        status_box = QVBoxLayout()
        status_box.setSpacing(4)

        self.status_label = QLabel()
        set_status_label(self.status_label, "CONNECTING")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_box.addWidget(self.status_label)

        self.metrics = QLabel("FPS: N/A  ·  Resolution: N/A")
        self.metrics.setProperty("muted", True)
        self.metrics.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_box.addWidget(self.metrics)

        layout.addLayout(status_box)

        # AI toggle
        ai_box = QVBoxLayout()
        ai_box.setSpacing(3)
        ai_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.ai_checkbox = QCheckBox("AI monitoring")
        self.ai_checkbox.setChecked(camera.ai_enabled)
        self.ai_checkbox.toggled.connect(
            lambda checked: self.ai_changed.emit(camera.camera_id, checked)
        )
        ai_box.addWidget(self.ai_checkbox)

        self.ai_hint = QLabel("Enabled" if camera.ai_enabled else "Disabled")
        self.ai_hint.setProperty("muted", True)
        self.ai_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ai_box.addWidget(self.ai_hint)

        layout.addLayout(ai_box)

        # Actions
        actions = QHBoxLayout()
        actions.setSpacing(7)

        reconnect = QPushButton("Reconnect")
        reconnect.clicked.connect(
            lambda: self.reconnect_requested.emit(camera.camera_id)
        )
        actions.addWidget(reconnect)

        remove = QPushButton("Remove")
        remove.setProperty("danger", True)
        remove.clicked.connect(self._confirm_remove)
        actions.addWidget(remove)

        layout.addLayout(actions)

    def update_camera(self, camera: CameraConfig) -> None:
        self.camera = camera

        self.ai_checkbox.blockSignals(True)
        self.ai_checkbox.setChecked(camera.ai_enabled)
        self.ai_checkbox.blockSignals(False)

        self.ai_hint.setText("Enabled" if camera.ai_enabled else "Disabled")
        self.source_badge.setText(camera.source_type.upper())

    def update_stats(self, stats: CameraStats) -> None:
        status = stats.status or "CONNECTING"
        set_status_label(self.status_label, status)

        fps = f"{stats.fps:.1f}" if stats.fps is not None else "N/A"
        resolution = stats.resolution or "N/A"
        self.metrics.setText(f"FPS: {fps}  ·  Resolution: {resolution}")
        self.status_label.setToolTip(stats.message or "")

    def _confirm_remove(self) -> None:
        answer = QMessageBox.question(
            self,
            "Remove camera",
            (
                f"Remove {self.camera.name} ({self.camera.camera_id}) "
                "and its saved connection credentials?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )

        if answer == QMessageBox.StandardButton.Yes:
            self.remove_requested.emit(self.camera.camera_id)


class CamerasPage(QWidget):
    add_requested = Signal(dict)
    remove_requested = Signal(str)
    reconnect_requested = Signal(str)
    ai_changed = Signal(str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._rows: dict[str, CameraRow] = {}
        self._stats: dict[str, CameraStats] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(14)

        # Header
        header = QHBoxLayout()
        header.setSpacing(16)

        title = make_page_title(
            "Camera network",
            "Manage external USB, RTSP, HTTP/MJPEG and IP camera sources.",
        )
        header.addWidget(title, 1)

        add_button = QPushButton("＋  Add camera")
        add_button.setProperty("primary", True)
        add_button.setMinimumHeight(38)
        add_button.clicked.connect(self._add_camera)
        header.addWidget(add_button, 0, Qt.AlignmentFlag.AlignBottom)

        root.addLayout(header)

        # Network overview
        self.overview = QFrame()
        self.overview.setProperty("card", True)
        overview_layout = QHBoxLayout(self.overview)
        overview_layout.setContentsMargins(16, 13, 16, 13)
        overview_layout.setSpacing(0)

        self.total_value = self._metric_value("0")
        self.online_value = self._metric_value("0")
        self.offline_value = self._metric_value("0")
        self.ai_value = self._metric_value("0")

        self._add_metric(overview_layout, "Configured", self.total_value)
        self._add_metric(overview_layout, "Online", self.online_value)
        self._add_metric(overview_layout, "Offline", self.offline_value)
        self._add_metric(overview_layout, "AI enabled", self.ai_value)

        root.addWidget(self.overview)

        # Section header
        list_header = QHBoxLayout()
        list_title = QLabel("Connected sources")
        list_title.setStyleSheet("font-size: 14px; font-weight: 700;")
        list_header.addWidget(list_title)

        self.summary_label = QLabel("No cameras configured.")
        self.summary_label.setProperty("muted", True)
        list_header.addWidget(self.summary_label, 1)

        root.addLayout(list_header)

        # Scrollable camera list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.content = QWidget()
        self.rows_layout = QVBoxLayout(self.content)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(9)

        self.empty_state = self._create_empty_state()
        self.rows_layout.addWidget(self.empty_state)

        self.rows_layout.addStretch(1)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)

    @staticmethod
    def _metric_value(value: str) -> QLabel:
        label = QLabel(value)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 18px; font-weight: 750;")
        return label

    @staticmethod
    def _add_metric(layout: QHBoxLayout, title: str, value: QLabel) -> None:
        box = QVBoxLayout()
        box.setSpacing(2)

        caption = QLabel(title.upper())
        caption.setProperty("muted", True)
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)

        box.addWidget(value)
        box.addWidget(caption)

        wrapper = QWidget()
        wrapper.setLayout(box)
        layout.addWidget(wrapper, 1)

    def _create_empty_state(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        card.setMinimumHeight(190)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(9)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("◎")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 32px; font-weight: 300;")
        layout.addWidget(icon)

        title = QLabel("No camera sources configured")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        layout.addWidget(title)

        description = QLabel(
            "Add an external USB device, RTSP stream, HTTP/MJPEG stream, "
            "or IP camera to begin monitoring."
        )
        description.setProperty("muted", True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        description.setMaximumWidth(620)
        layout.addWidget(description)

        add_button = QPushButton("Add your first camera")
        add_button.clicked.connect(self._add_camera)
        layout.addWidget(add_button, 0, Qt.AlignmentFlag.AlignCenter)

        return card

    def sync_cameras(
        self,
        cameras: list[CameraConfig],
        stats: dict[str, CameraStats],
    ) -> None:
        self._stats = dict(stats)
        new_ids = {camera.camera_id for camera in cameras}

        for camera_id in set(self._rows) - new_ids:
            row = self._rows.pop(camera_id)
            self.rows_layout.removeWidget(row)
            row.deleteLater()

        # Hide empty state once a camera exists.
        self.empty_state.setVisible(not cameras)

        for camera in cameras:
            row = self._rows.get(camera.camera_id)

            if row is None:
                row = CameraRow(camera)
                row.remove_requested.connect(self.remove_requested.emit)
                row.reconnect_requested.connect(self.reconnect_requested.emit)
                row.ai_changed.connect(self.ai_changed.emit)

                self._rows[camera.camera_id] = row
                self.rows_layout.insertWidget(
                    self.rows_layout.count() - 1,
                    row,
                )
            else:
                row.update_camera(camera)

            row.update_stats(stats.get(camera.camera_id, CameraStats()))

        self._update_summary(cameras, stats)

    def _update_summary(
        self,
        cameras: list[CameraConfig],
        stats: dict[str, CameraStats],
    ) -> None:
        total = len(cameras)

        online_states = {"LIVE", "ONLINE", "CONNECTED"}
        offline_states = {"OFFLINE", "ERROR", "DISCONNECTED"}

        online = 0
        offline = 0

        for camera in cameras:
            status = (stats.get(camera.camera_id, CameraStats()).status or "").upper()
            if status in online_states:
                online += 1
            elif status in offline_states:
                offline += 1

        ai_enabled = sum(1 for camera in cameras if camera.ai_enabled)

        self.total_value.setText(str(total))
        self.online_value.setText(str(online))
        self.offline_value.setText(str(offline))
        self.ai_value.setText(str(ai_enabled))

        if cameras:
            self.summary_label.setText(
                f"{total} configured camera source"
                f"{'s' if total != 1 else ''}  ·  "
                f"{online} online  ·  {offline} offline"
            )
        else:
            self.summary_label.setText(
                "No camera sources yet. Add a real external camera source."
            )

    def update_camera_stats(self, camera_id: str, stats: CameraStats) -> None:
        self._stats[camera_id] = stats

        row = self._rows.get(camera_id)
        if row:
            row.update_stats(stats)

        self._refresh_counts()

    def _refresh_counts(self) -> None:
        cameras = [row.camera for row in self._rows.values()]
        self._update_summary(cameras, self._stats)

    def _add_camera(self) -> None:
        dialog = CameraFormDialog(self)

        if (
            dialog.exec() == CameraFormDialog.DialogCode.Accepted
            and dialog.form_data
        ):
            self.add_requested.emit(dialog.form_data)
