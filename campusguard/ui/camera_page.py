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
        layout = QHBoxLayout(self)
        layout.setContentsMargins(13, 11, 13, 11)
        layout.setSpacing(12)

        labels = QVBoxLayout()
        labels.setSpacing(3)
        name = QLabel(camera.name)
        name.setStyleSheet("font-weight: 700;")
        address = QLabel(f"{camera.camera_id}  ·  {camera.source_type}  ·  {camera.source_address}")
        address.setProperty("muted", True)
        address.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        labels.addWidget(name)
        labels.addWidget(address)
        layout.addLayout(labels, 1)

        self.status_label = QLabel()
        set_status_label(self.status_label, "CONNECTING")
        layout.addWidget(self.status_label)
        self.metrics = QLabel("FPS: N/A  ·  Resolution: N/A")
        self.metrics.setProperty("muted", True)
        layout.addWidget(self.metrics)

        self.ai_checkbox = QCheckBox("AI")
        self.ai_checkbox.setChecked(camera.ai_enabled)
        self.ai_checkbox.toggled.connect(
            lambda checked: self.ai_changed.emit(camera.camera_id, checked)
        )
        layout.addWidget(self.ai_checkbox)

        reconnect = QPushButton("Reconnect")
        reconnect.clicked.connect(lambda: self.reconnect_requested.emit(camera.camera_id))
        layout.addWidget(reconnect)
        remove = QPushButton("Remove")
        remove.setProperty("danger", True)
        remove.clicked.connect(lambda: self._confirm_remove())
        layout.addWidget(remove)

    def update_camera(self, camera: CameraConfig) -> None:
        self.camera = camera
        self.ai_checkbox.blockSignals(True)
        self.ai_checkbox.setChecked(camera.ai_enabled)
        self.ai_checkbox.blockSignals(False)

    def update_stats(self, stats: CameraStats) -> None:
        set_status_label(self.status_label, stats.status)
        fps = f"{stats.fps:.1f}" if stats.fps is not None else "N/A"
        self.metrics.setText(f"FPS: {fps}  ·  Resolution: {stats.resolution}")
        self.status_label.setToolTip(stats.message)

    def _confirm_remove(self) -> None:
        answer = QMessageBox.question(
            self,
            "Remove camera",
            f"Remove {self.camera.name} ({self.camera.camera_id}) and its saved connection credentials?",
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
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(13)

        header = QHBoxLayout()
        header.addWidget(make_page_title(
            "Camera network",
            "Manage external camera sources. Camera video and status come from real OpenCV reads.",
        ), 1)
        add_button = QPushButton("Add camera")
        add_button.setProperty("primary", True)
        add_button.clicked.connect(self._add_camera)
        header.addWidget(add_button, 0, Qt.AlignmentFlag.AlignBottom)
        root.addLayout(header)

        self.summary_label = QLabel("No cameras configured.")
        self.summary_label.setProperty("muted", True)
        root.addWidget(self.summary_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.rows_layout = QVBoxLayout(self.content)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(8)
        self.rows_layout.addStretch(1)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)

    def sync_cameras(self, cameras: list[CameraConfig], stats: dict[str, CameraStats]) -> None:
        new_ids = {camera.camera_id for camera in cameras}
        for camera_id in set(self._rows) - new_ids:
            row = self._rows.pop(camera_id)
            self.rows_layout.removeWidget(row)
            row.deleteLater()

        for camera in cameras:
            row = self._rows.get(camera.camera_id)
            if row is None:
                row = CameraRow(camera)
                row.remove_requested.connect(self.remove_requested.emit)
                row.reconnect_requested.connect(self.reconnect_requested.emit)
                row.ai_changed.connect(self.ai_changed.emit)
                self._rows[camera.camera_id] = row
                self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
            else:
                row.update_camera(camera)
            row.update_stats(stats.get(camera.camera_id, CameraStats()))

        if cameras:
            self.summary_label.setText(
                f"{len(cameras)} configured camera source{'s' if len(cameras) != 1 else ''}."
            )
        else:
            self.summary_label.setText(
                "No camera sources yet. Add a real USB device index, RTSP URL, HTTP/MJPEG URL, or IP camera."
            )

    def update_camera_stats(self, camera_id: str, stats: CameraStats) -> None:
        row = self._rows.get(camera_id)
        if row:
            row.update_stats(stats)

    def _add_camera(self) -> None:
        dialog = CameraFormDialog(self)
        if dialog.exec() == CameraFormDialog.DialogCode.Accepted and dialog.form_data:
            self.add_requested.emit(dialog.form_data)