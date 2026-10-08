from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGraphicsDropShadowEffect,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from campusguard.camera_runtime import (
    CameraTestThread,
    build_capture_source,
    enumerate_local_cameras,
)
from campusguard.settings import CameraConfig, CameraCredentials, CameraStats
from campusguard.ui.icons import IconLabel, set_icon_theme
from campusguard.ui.theme import build_qss, get_palette, set_current


def apply_theme(application, theme: str) -> None:
    """Apply the dark/light stylesheet and re-color every custom widget."""
    set_current(theme)
    set_icon_theme(theme)
    application.setStyleSheet(build_qss(theme))
    # QScrollArea paints its inner widget with Qt's default light color, which shows
    # up as white boxes in dark mode. Turn that fill off so the card color shows.
    for scroll in application.findChildren(QScrollArea):
        scroll.viewport().setAutoFillBackground(False)
        inner = scroll.widget()
        if inner is not None:
            inner.setAutoFillBackground(False)
    for widget in application.findChildren(QWidget):
        retint = getattr(widget, "retint", None)  # custom-painted widgets and glass popups
        if callable(retint):
            retint()


def set_tone(widget: QWidget, tone: str) -> None:
    """Set a label's color class: "good", "warn", "bad", or "" for the default.

    Qt only re-reads stylesheet rules when asked, hence unpolish/polish.
    """
    widget.setProperty("tone", tone)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class ClickableFrame(QFrame):
    """A QFrame that emits clicked() when pressed with the left mouse button."""

    clicked = Signal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def make_page_title(title: str, subtitle: str) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 8)
    layout.setSpacing(8)
    heading = QLabel(title)
    heading.setStyleSheet("font-size: 21pt; font-weight: 700; letter-spacing: -0.15px;")
    description = QLabel(subtitle)
    description.setProperty("muted", True)
    layout.addWidget(heading)
    layout.addWidget(description)
    return widget


def make_card(
    title: str,
    parent: QWidget | None = None,
    icon: str | None = None,
) -> tuple[QFrame, QVBoxLayout]:
    """A rounded card with a header row (optional icon + bold title).

    Returns (frame, layout). Add your content to `layout`. To put something on
    the right of the header (a link, a pill), use `frame.header_layout`.
    """
    frame = QFrame(parent)
    frame.setProperty("card", True)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    shadow = QGraphicsDropShadowEffect(frame)
    shadow.setBlurRadius(34)
    shadow.setOffset(0, 10)
    shadow.setColor(QColor(0, 0, 0, 88))
    frame.setGraphicsEffect(shadow)

    header = QHBoxLayout()
    header.setSpacing(10)
    if icon:
        header.addWidget(IconLabel(icon, 20, "text"))
    label = QLabel(title)
    label.setProperty("cardtitle", True)
    header.addWidget(label)
    header.addStretch(1)
    layout.addLayout(header)
    frame.header_layout = header  # lets callers add widgets on the right
    return frame, layout


def set_status_label(label: QLabel, status: str) -> None:
    status = status.upper()
    palette = get_palette()
    colors = {
        "LIVE": palette.good,
        "CONNECTING": palette.warn,
        "OFFLINE": palette.muted,
        "ERROR": palette.bad,
    }
    color = colors.get(status, palette.muted)
    label.setProperty("statusPill", True)
    label.setProperty("tone", status.lower())
    label.setText(f"●  {status}")
    label.setStyleSheet(
        f"color: {color}; "
        f"background: {color}18; "
        f"border: 1px solid {color}38; "
        "padding: 4px 9px; border-radius: 9px; "
        "font-size: 8pt; font-weight: 700; letter-spacing: 0.35px;"
    )


class CameraPreview(QFrame):
    selected = Signal(str)

    def __init__(self, camera: CameraConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.camera_id = camera.camera_id
        self._source_pixmap: QPixmap | None = None
        self.setProperty("card", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(238)
        self.setObjectName("cameraPreview")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)
        header = QHBoxLayout()
        labels = QVBoxLayout()
        labels.setSpacing(1)
        self.name_label = QLabel(camera.name)
        self.name_label.setStyleSheet("font-weight: 700;")
        self.id_label = QLabel(camera.camera_id)
        self.id_label.setProperty("muted", True)
        labels.addWidget(self.name_label)
        labels.addWidget(self.id_label)
        self.status_label = QLabel()
        set_status_label(self.status_label, "CONNECTING")
        header.addLayout(labels)
        header.addStretch(1)
        header.addWidget(self.status_label)
        outer.addLayout(header)

        self.video_label = QLabel("Waiting for camera frames")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setMinimumHeight(130)
        self.video_label.setProperty("videoSurface", True)
        self.video_label.setStyleSheet("border-radius: 12px; font-size: 9pt; padding: 1px;")
        self.video_label.setScaledContents(False)
        outer.addWidget(self.video_label, 1)

        self.meta_label = QLabel("FPS: N/A    Resolution: N/A    AI: starting")
        self.meta_label.setProperty("muted", True)
        self.meta_label.setStyleSheet("font-size: 8pt; letter-spacing: 0.15px;")
        outer.addWidget(self.meta_label)

        self.ai_state_label = QLabel("AI: starting")
        self.ai_state_label.setProperty("muted", True)
        self.ai_state_label.setStyleSheet("font-size: 8pt; font-weight: 650; letter-spacing: 0.15px;")
        outer.addWidget(self.ai_state_label)

    def set_camera(self, camera: CameraConfig) -> None:
        self.camera_id = camera.camera_id
        self.name_label.setText(camera.name)
        self.id_label.setText(camera.camera_id)

    def set_status(self, stats: CameraStats, ai_enabled: bool) -> None:
        set_status_label(self.status_label, stats.status)
        fps = f"{stats.fps:.1f}" if stats.fps is not None else "N/A"
        ai_text = "enabled" if ai_enabled else "off"
        self.meta_label.setText(
            f"FPS: {fps}    Resolution: {stats.resolution}    AI: {ai_text}"
        )
        if stats.status != "LIVE":
            self._source_pixmap = None
            self.video_label.setPixmap(QPixmap())
            self.video_label.setText(
                stats.message
                or ("Connecting to camera…" if stats.status == "CONNECTING" else "Waiting for camera frames")
            )
            self.ai_state_label.setText("AI: waiting for live frames")
        elif self._source_pixmap is None:
            self.video_label.setText("Waiting for camera frames")

    def set_model_status(self, message: str) -> None:
        if message:
            self.ai_state_label.setText(f"AI: {message}")

    def set_frame(
        self,
        pixmap: QPixmap,
        state: str = "NORMAL",
        confidence: float | None = None,
    ) -> None:
        self._source_pixmap = pixmap
        if confidence is None:
            self.ai_state_label.setText(f"AI: {state}")
        else:
            self.ai_state_label.setText(f"AI: {state}  ·  {confidence:.0%}")
        self._scale_pixmap()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._scale_pixmap()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.camera_id)
        super().mousePressEvent(event)

    def _scale_pixmap(self) -> None:
        if self._source_pixmap is None:
            return
        self.video_label.setText("")
        self.video_label.setPixmap(
            self._source_pixmap.scaled(
                self.video_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class CameraFormDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add external camera")
        self.setMinimumWidth(460)
        self._test_thread: CameraTestThread | None = None
        self._form_data: dict[str, str] | None = None

        root = QVBoxLayout(self)
        intro = QLabel(
            "Connect an external USB, RTSP, HTTP/MJPEG, or IP camera. "
            "No camera is selected automatically."
        )
        intro.setWordWrap(True)
        intro.setProperty("muted", True)
        root.addWidget(intro)

        form = QFormLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("North Gate")
        self.type_input = QComboBox()
        self.type_input.addItems(["RTSP", "HTTP", "MJPEG", "IP", "USB"])
        self.address_input = QLineEdit()
        self.address_input.setPlaceholderText("rtsp://camera-address/stream")
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Stored in the OS credential vault")
        form.addRow("Camera name", self.name_input)
        form.addRow("Source type", self.type_input)

        self.detected_widget = QWidget()
        detected_layout = QHBoxLayout(self.detected_widget)
        detected_layout.setContentsMargins(0, 0, 0, 0)
        detected_layout.setSpacing(8)

        self.detected_input = QComboBox()
        self.detected_input.setMinimumWidth(250)
        self.detected_input.addItem("Press Refresh Cameras to scan", None)

        self.refresh_cameras_button = QPushButton("Refresh Cameras")
        self.refresh_cameras_button.clicked.connect(self._refresh_local_cameras)

        detected_layout.addWidget(self.detected_input, 1)
        detected_layout.addWidget(self.refresh_cameras_button)
        form.addRow("Detected cameras", self.detected_widget)

        form.addRow("Source address", self.address_input)
        form.addRow("Username", self.username_input)
        form.addRow("Password", self.password_input)
        root.addLayout(form)

        self.detected_input.currentIndexChanged.connect(
            self._select_detected_camera
        )

        self.test_status = QLabel("Connection has not been tested.")
        self.test_status.setProperty("muted", True)
        root.addWidget(self.test_status)

        self.validation_status = QLabel()
        self.validation_status.setProperty("tone", "bad")
        self.validation_status.setWordWrap(True)
        self.validation_status.hide()
        root.addWidget(self.validation_status)
        buttons = QDialogButtonBox()
        self.test_button = buttons.addButton(
            "Test Connection", QDialogButtonBox.ButtonRole.ActionRole
        )
        self.save_button = buttons.addButton(
            "Save Camera", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.save_button.setProperty("primary", True)
        self.cancel_button = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        root.addWidget(buttons)

        self.test_button.clicked.connect(self._test_connection)
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.reject)
        self.type_input.currentTextChanged.connect(self._update_placeholder)
        self._update_placeholder(self.type_input.currentText())
        self._update_usb_controls(self.type_input.currentText())

    @property
    def form_data(self) -> dict[str, str] | None:
        return self._form_data

    def _update_placeholder(self, source_type: str) -> None:
        placeholders = {
            "USB": "Device index, for example 1",
            "RTSP": "rtsp://camera-address/stream",
            "HTTP": "http://camera-address/video",
            "MJPEG": "http://camera-address/mjpeg",
            "IP": "192.168.1.50:8080/video or a full URL",
        }
        self.address_input.setPlaceholderText(placeholders.get(source_type, ""))
        self._update_usb_controls(source_type)

    def _update_usb_controls(self, source_type: str) -> None:
        is_usb = source_type.upper() == "USB"
        self.detected_widget.setVisible(is_usb)
        if is_usb:
            self.username_input.clear()
            self.password_input.clear()
            self.username_input.setEnabled(False)
            self.password_input.setEnabled(False)
            self._refresh_local_cameras()
        else:
            self.username_input.setEnabled(True)
            self.password_input.setEnabled(True)

    def _refresh_local_cameras(self) -> None:
        if self.type_input.currentText().upper() != "USB":
            return

        self.detected_input.blockSignals(True)
        self.detected_input.clear()
        self.detected_input.addItem("Scanning local camera devices...", None)
        self.detected_input.blockSignals(False)
        self.refresh_cameras_button.setEnabled(False)

        cameras = enumerate_local_cameras(max_devices=8)

        self.detected_input.blockSignals(True)
        self.detected_input.clear()

        if cameras:
            for camera in cameras:
                self.detected_input.addItem(
                    str(camera["label"]),
                    int(camera["index"]),
                )
            self.detected_input.setCurrentIndex(0)
            self.address_input.setText(str(cameras[0]["index"]))
        else:
            self.detected_input.addItem(
                "No local camera found - check DroidCam/Windows first",
                None,
            )

        self.detected_input.blockSignals(False)
        self.refresh_cameras_button.setEnabled(True)

    def _select_detected_camera(self, index: int) -> None:
        device_index = self.detected_input.itemData(index)
        if device_index is not None:
            self.address_input.setText(str(int(device_index)))

    def _values(self) -> dict[str, str]:
        return {
            "name": self.name_input.text().strip(),
            "source_type": self.type_input.currentText(),
            "source_address": self.address_input.text().strip(),
            "username": self.username_input.text(),
            "password": self.password_input.text(),
        }

    def _test_connection(self) -> None:
        values = self._values()
        if not values["source_address"]:
            self.validation_status.setText(
                "Source address required — select a detected camera or enter its device index."
            )
            self.validation_status.show()
            return
        self.validation_status.hide()
        credentials = CameraCredentials(values["username"], values["password"])
        self._test_thread = CameraTestThread(
            values["source_type"],
            values["source_address"],
            credentials,
        )
        self._test_thread.result_ready.connect(self._show_test_result)
        self._test_thread.finished.connect(self._restore_buttons)
        self.test_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.test_status.setText("Testing the actual camera source…")
        self._test_thread.start()

    def _show_test_result(self, success: bool, message: str) -> None:
        self.test_status.setText(message)
        self.test_status.setStyleSheet(
            "color: #5cae80;" if success else "color: #dc766d;"
        )

    def _restore_buttons(self) -> None:
        self.test_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.cancel_button.setEnabled(True)

    def _save(self) -> None:
        values = self._values()
        if not values["name"]:
            self.validation_status.setText("Camera name required — enter a name before saving.")
            self.validation_status.show()
            return
        if not values["source_address"]:
            self.validation_status.setText("Source address required — enter a camera source address.")
            self.validation_status.show()
            return
        try:
            build_capture_source(
                values["source_type"],
                values["source_address"],
                CameraCredentials(values["username"], values["password"]),
            )
        except ValueError as error:
            self.validation_status.setText(str(error))
            self.validation_status.show()
            return
        self._form_data = values
        self.accept()

    def closeEvent(self, event) -> None:
        if self._test_thread is not None and self._test_thread.isRunning():
            self.test_status.setText("Wait for the camera connection test to finish before closing.")
            event.ignore()
            return
        event.accept()

    def reject(self) -> None:
        if self._test_thread is not None and self._test_thread.isRunning():
            self.test_status.setText("Wait for the camera connection test to finish before closing.")
            return
        super().reject()


class EnlargedCameraDialog(QDialog):
    def __init__(self, camera: CameraConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{camera.name} — {camera.camera_id}")
        self.resize(1100, 720)
        self._stats = CameraStats()
        self._state = "CONNECTING"
        self._confidence: float | None = None
        self.image_label = QLabel("Waiting for camera frames")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background: #080d11; color: #9ba5aa;")
        self.info_label = QLabel("FPS: N/A   Resolution: N/A")
        layout = QVBoxLayout(self)
        layout.addWidget(self.image_label, 1)
        layout.addWidget(self.info_label)

    def set_frame(self, image, state: str, confidence: float | None) -> None:
        self._state = state
        self._confidence = confidence
        pixmap = QPixmap.fromImage(image)
        self.image_label.setText("")
        self.image_label.setPixmap(
            pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self._render_info()

    def set_camera_stats(self, stats: CameraStats) -> None:
        self._stats = stats
        if stats.status != "LIVE":
            self._state = stats.status
            self._confidence = None
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText(
                stats.message
                or ("Connecting to camera…" if stats.status == "CONNECTING" else "Waiting for camera frames")
            )
        self._render_info()

    def _render_info(self) -> None:
        fps = f"{self._stats.fps:.1f}" if self._stats.fps is not None else "N/A"
        suffix = (
            f"   Confidence: {self._confidence:.0%}"
            if self._confidence is not None
            else ""
        )
        self.info_label.setText(
            f"{self._state}   FPS: {fps}   Resolution: {self._stats.resolution}{suffix}"
        )

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)