"""Dialog that runs a local video file through the production AI pipeline."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (

    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from campusguard.settings import AppSettings
from campusguard.camera_runtime import LocalVideoTestThread
from campusguard.ui.theme import get_palette, rgba




class LocalVideoTestDialog(QFrame):
    """Theme-aware, in-app overlay for one-shot local video model testing."""

    event_detected = Signal(str, float, str)
    footage_saved = Signal(str)

    def __init__(self, video_path: str, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._video_path = video_path
        self._settings = settings
        self._thread: LocalVideoTestThread | None = None
        self._last_pixmap: QPixmap | None = None
        self.setObjectName("localVideoTestOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._panel = QFrame(self)
        self._panel.setObjectName("localVideoTestPanel")
        self._panel.setMinimumWidth(720)
        self._panel.setMaximumWidth(1280)
        self._panel.setMaximumHeight(900)

        root = QVBoxLayout(self._panel)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(14)
        header = QHBoxLayout()
        title = QLabel("Local File Test")
        title.setObjectName("localVideoTestTitle")
        title.setStyleSheet("font-size: 17px; font-weight: 600;")
        header.addWidget(title, 0)
        header.addStretch(1)
        self.close_button = QPushButton("×")
        self.close_button.setFixedSize(36, 36)
        self.close_button.setToolTip("Close local file testing")
        header.addWidget(self.close_button)
        root.addLayout(header)

        file_label = QLabel(video_path)
        file_label.setProperty("muted", True)
        file_label.setWordWrap(True)
        root.addWidget(file_label)

        self.video = QLabel("Ready to test")
        self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video.setMinimumHeight(360)
        self.video.setProperty("videoSurface", True)
        self.video.setStyleSheet("border-radius: 14px; font-size: 10pt;")
        root.addWidget(self.video, 1)

        self.status = QLabel("Test file loaded. Press Play once to run the production model.")
        self.status.setProperty("muted", True)
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.play_button = QPushButton("Play Once")
        self.play_button.setProperty("primary", True)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.choose_button = QPushButton("Choose File")
        controls.addWidget(self.play_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.choose_button)
        controls.addStretch(1)
        root.addLayout(controls)

        self.play_button.clicked.connect(self._play)
        self.stop_button.clicked.connect(self._stop)
        self.choose_button.clicked.connect(self._choose_file)
        self.close_button.clicked.connect(self.close)
        self.retint()

    def retint(self) -> None:
        palette = get_palette()
        overlay = rgba("#000000" if palette.name == "dark" else "#667085",
                       178 if palette.name == "dark" else 112)
        panel = rgba(palette.glass, min(242, max(208, palette.glass_alpha + 60)))
        line = rgba(palette.line, min(150, max(55, palette.line_alpha * 3)))
        self.setStyleSheet(
            f"QFrame#localVideoTestOverlay {{ background: {overlay}; border: none; }}"
            f"QFrame#localVideoTestPanel {{ background: {panel}; border: 1px solid {line}; "
            "border-radius: 26px; }"
            "QLabel#localVideoTestTitle { background: transparent; }"
        )
        self.update()

    def _center_panel(self) -> None:
        if not self.parentWidget():
            return
        available_width = max(640, self.width() - 56)
        available_height = max(480, self.height() - 48)
        self._panel.setMaximumWidth(min(1280, available_width))
        self._panel.setMaximumHeight(min(900, available_height))
        self._panel.adjustSize()
        width = min(max(720, self._panel.sizeHint().width()), available_width)
        height = min(max(560, self._panel.sizeHint().height()), available_height)
        self._panel.resize(width, height)
        self._panel.move(max(12, (self.width() - width) // 2),
                         max(12, (self.height() - height) // 2))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.parentWidget():
            self.setGeometry(self.parentWidget().rect())
        self.retint()
        self._center_panel()
        self.raise_()
        self.setFocus()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._center_panel()
        self._scale_frame()

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select test video", "",
            "Video files (*.mp4 *.avi *.mov *.mkv *.wmv *.m4v);;All files (*.*)",
        )
        if not path:
            return
        self._video_path = path
        self.video.clear()
        self.video.setText("Ready to test")
        self.status.setText("Test file loaded. Press Play once to run the production model.")

    def _play(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        self._last_pixmap = None
        self.video.clear()
        self.status.setText("Loading Spontim 1.0 and the production detection pipeline...")
        self.play_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.choose_button.setEnabled(False)
        from campusguard.camera_runtime import LocalVideoTestThread

        self._thread = LocalVideoTestThread(self._video_path, self._settings)
        self._thread.frame_ready.connect(self._on_frame)
        self._thread.status_changed.connect(self._on_status)
        self._thread.model_status.connect(self._on_model_status)
        self._thread.event_detected.connect(self.event_detected.emit)
        self._thread.footage_saved.connect(self.footage_saved.emit)
        self._thread.finished.connect(self._on_finished)
        self._thread.start()

    def _stop(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._thread.requestInterruption()
            self.status.setText("Stopping test...")

    def _on_frame(self, image, state: str, confidence) -> None:
        self._last_pixmap = QPixmap.fromImage(image)
        self._scale_frame()
        suffix = f"  ·  {confidence:.0%}" if confidence is not None else ""
        self.status.setText(f"{state}{suffix}")

    def _on_status(self, message: str) -> None:
        self.status.setText(message)

    def _on_model_status(self, component: str, message: str) -> None:
        if component == "fight":
            self.status.setText(message)

    def _on_finished(self) -> None:
        self.play_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.choose_button.setEnabled(True)

    def _scale_frame(self) -> None:
        if self._last_pixmap is None:
            return
        self.video.setPixmap(self._last_pixmap.scaled(
            self.video.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))

    def closeEvent(self, event) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._thread.requestInterruption()
            self._thread.wait(5000)
        event.accept()
