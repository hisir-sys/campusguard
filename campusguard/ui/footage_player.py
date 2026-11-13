"""Incident footage players: the full-screen viewer and the inline player of the side panel."""
from __future__ import annotations

from pathlib import Path

import cv2

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsBlurEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)





class FootagePlayerDialog(QWidget):
    """Persistent in-app incident footage viewer using OpenCV decoding.

    OpenCV is also the writer used by FightFootageRecorder, so playback uses
    the same decoder path instead of depending on Windows/Qt codec availability.
    """

    def __init__(
        self,
        footage_path: str,
        title: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("footageViewerOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(
            """
            QWidget#footageViewerOverlay {
                background: rgba(0, 0, 0, 145);
            }
            QFrame#footageViewerCard {
                border-radius: 18px;
            }
            """
        )

        self.card = QFrame(self)
        self.card.setObjectName("footageViewerCard")
        self.card.setProperty("card", True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.card)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        heading = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(2)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 17px; font-weight: 850;")

        subtitle = QLabel("Saved incident footage")
        subtitle.setProperty("muted", True)

        title_block.addWidget(title_label)
        title_block.addWidget(subtitle)
        heading.addLayout(title_block, 1)

        close_button = QPushButton("Close")
        close_button.setProperty("secondaryButton", True)
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_button.setMinimumHeight(32)
        close_button.clicked.connect(self.close)
        heading.addWidget(close_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(heading)

        self.video = QLabel("Loading saved footage…")
        self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video.setMinimumSize(640, 360)
        self.video.setStyleSheet(
            "QLabel { background: #050505; border-radius: 12px; color: #AAB4C0; }"
        )
        self.video.installEventFilter(self)
        self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.video, 1)

        self.capture: cv2.VideoCapture | None = None
        self.source_fps = 30.0
        self.playback_rate = 1.0
        self.frame_count = 0
        self.zoom_factor = 1.0
        self._last_pixmap: QPixmap | None = None
        self._seeking = False

        # Timeline / seek bar.
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setObjectName("footageTimeline")
        self.timeline.setRange(0, 0)
        self.timeline.setSingleStep(1)
        self.timeline.sliderPressed.connect(self._begin_seek)
        self.timeline.sliderReleased.connect(self._finish_seek)
        self.timeline.valueChanged.connect(self._timeline_changed)
        layout.addWidget(self.timeline)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.play_button = QPushButton("▶ Play")
        self.play_button.setProperty("secondaryButton", True)
        self.play_button.clicked.connect(self._toggle_play)
        controls.addWidget(self.play_button)

        self.rewind_button = QPushButton("↶ 5s")
        self.rewind_button.setToolTip("Rewind five seconds")
        self.rewind_button.clicked.connect(lambda: self._skip_seconds(-5))
        controls.addWidget(self.rewind_button)

        self.forward_button = QPushButton("5s ↷")
        self.forward_button.setToolTip("Forward five seconds")
        self.forward_button.clicked.connect(lambda: self._skip_seconds(5))
        controls.addWidget(self.forward_button)

        speed_label = QLabel("Speed")
        speed_label.setProperty("muted", True)
        controls.addWidget(speed_label)
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5×", "0.75×", "1×", "1.25×", "1.5×", "2×"])
        self.speed_combo.setCurrentIndex(2)
        self.speed_combo.setMinimumWidth(76)
        self.speed_combo.currentIndexChanged.connect(self._set_playback_speed)
        controls.addWidget(self.speed_combo)

        controls.addWidget(QLabel("Zoom"))
        self.zoom_out_button = QPushButton("−")
        self.zoom_out_button.setToolTip("Zoom out")
        self.zoom_out_button.setFixedWidth(36)
        self.zoom_out_button.clicked.connect(lambda: self._change_zoom(-0.2))
        controls.addWidget(self.zoom_out_button)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(46)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        controls.addWidget(self.zoom_label)
        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setToolTip("Zoom in")
        self.zoom_in_button.setFixedWidth(36)
        self.zoom_in_button.clicked.connect(lambda: self._change_zoom(0.2))
        controls.addWidget(self.zoom_in_button)

        controls.addStretch(1)
        self.status_label = QLabel("Ready")
        self.status_label.setProperty("muted", True)
        controls.addWidget(self.status_label)
        layout.addLayout(controls)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._read_frame)
        self._background_blurs: list[tuple[QWidget, QGraphicsBlurEffect]] = []

        path = Path(footage_path)
        if not path.is_file():
            self.video.setText("The saved footage file is no longer available.")
            return

        capture = cv2.VideoCapture(str(path.resolve()))
        if capture is None or not capture.isOpened():
            if capture is not None:
                capture.release()
            self.video.setText("CampusGuard could not decode this saved footage.")
            return

        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        if not 8.0 <= fps <= 60.0:
            fps = 30.0
        self.source_fps = fps
        self.capture = capture
        self.frame_count = max(0, int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0))
        self.timeline.setRange(0, max(0, self.frame_count - 1))
        self.status_label.setText("00:00 / " + self._format_time(self._duration_seconds()))
        self._set_timer_interval()
        self._read_frame()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_background_blur()
        self.raise_()
        self.card.raise_()
        if self.capture is not None:
            self._set_timer_interval()
            self.timer.start()
            self.play_button.setText("Ⅱ Pause")

    def eventFilter(self, watched, event) -> bool:
        # Clicking the video surface must not close playback; users can interact
        # with the timeline and controls while reviewing saved footage.
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event) -> None:
        if not self.card.geometry().contains(event.position().toPoint()):
            self.close()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def _duration_seconds(self) -> float:
        return self.frame_count / self.source_fps if self.frame_count > 0 else 0.0

    @staticmethod
    def _format_time(seconds: float) -> str:
        total = max(0, int(seconds))
        return f"{total // 60:02d}:{total % 60:02d}"

    def _begin_seek(self) -> None:
        self._seeking = True
        self.timer.stop()

    def _finish_seek(self) -> None:
        if self.capture is not None:
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, self.timeline.value())
            self._seeking = False
            self._read_frame()
            self.timer.start()

    def _timeline_changed(self, frame_index: int) -> None:
        if self.frame_count > 0:
            current = frame_index / self.source_fps
            self.status_label.setText(
                f"{self._format_time(current)} / {self._format_time(self._duration_seconds())}"
            )
        if self._seeking and self.capture is not None:
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            self._read_frame()

    def _toggle_play(self) -> None:
        if self.capture is None:
            return
        if self.timer.isActive():
            self.timer.stop()
            self.play_button.setText("▶ Play")
        else:
            if self.frame_count and self.timeline.value() >= self.frame_count - 1:
                self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self.timeline.setValue(0)
            self._set_timer_interval()
            self.timer.start()
            self.play_button.setText("Ⅱ Pause")

    def _skip_seconds(self, seconds: float) -> None:
        if self.capture is None:
            return
        target = int(self.capture.get(cv2.CAP_PROP_POS_FRAMES) + seconds * self.source_fps)
        target = max(0, min(max(0, self.frame_count - 1), target))
        self.capture.set(cv2.CAP_PROP_POS_FRAMES, target)
        self.timeline.setValue(target)
        self._read_frame()

    def _change_zoom(self, delta: float) -> None:
        self.zoom_factor = max(0.6, min(2.5, round(self.zoom_factor + delta, 2)))
        self.zoom_label.setText(f"{int(self.zoom_factor * 100)}%")
        self._display_frame()

    def _set_playback_speed(self, index: int) -> None:
        rates = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
        if 0 <= index < len(rates):
            self.playback_rate = rates[index]
            self._set_timer_interval()

    def _set_timer_interval(self) -> None:
        interval = max(10, int(round(1000.0 / self.source_fps / self.playback_rate)))
        self.timer.setInterval(interval)

    def _display_frame(self) -> None:
        if self._last_pixmap is None:
            return
        target = self.video.size() * self.zoom_factor
        self.video.setPixmap(
            self._last_pixmap.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _read_frame(self) -> None:
        if self.capture is None:
            self.timer.stop()
            return
        ok, frame = self.capture.read()
        if not ok or frame is None or frame.size == 0:
            self.timer.stop()
            self.play_button.setText("▶ Replay")
            self.status_label.setText("End of footage")
            return

        frame_index = max(0, int(self.capture.get(cv2.CAP_PROP_POS_FRAMES)) - 1)
        if not self._seeking:
            self.timeline.blockSignals(True)
            self.timeline.setValue(frame_index)
            self.timeline.blockSignals(False)
        current = frame_index / self.source_fps
        self.status_label.setText(
            f"{self._format_time(current)} / {self._format_time(self._duration_seconds())}"
        )
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = QImage(
            rgb.data,
            rgb.shape[1],
            rgb.shape[0],
            int(rgb.strides[0]),
            QImage.Format.Format_RGB888,
        ).copy()
        self._last_pixmap = QPixmap.fromImage(image)
        self._display_frame()

    def _apply_background_blur(self) -> None:
        self._clear_background_blur()
        window = self.window()
        for name in ("stack", "top_bar", "bottom_bar"):
            widget = getattr(window, name, None)
            if isinstance(widget, QWidget):
                effect = QGraphicsBlurEffect(widget)
                effect.setBlurRadius(16)
                widget.setGraphicsEffect(effect)
                self._background_blurs.append((widget, effect))

    def _clear_background_blur(self) -> None:
        for widget, effect in self._background_blurs:
            if widget.graphicsEffect() is effect:
                widget.setGraphicsEffect(None)
            # setGraphicsEffect(None) can destroy the effect immediately;
            # never delete the wrapper a second time.
        self._background_blurs.clear()

    def closeEvent(self, event) -> None:
        self._clear_background_blur()
        self.timer.stop()
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        super().closeEvent(event)


class InlineClipPlayer(QWidget):
    """A small player for the incident side panel: video, play / pause, seek bar and a
    full-screen button that hands the clip to FootagePlayerDialog."""

    fullscreen_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.capture = None
        self.path = ""
        self.fps = 25.0
        self.frames = 0
        self._seeking = False
        self._pixmap: QPixmap | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.video = QLabel("Select an incident to review its clip")
        self.video.setProperty("videoSurface", True)
        self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video.setMinimumHeight(220)
        self.video.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.video, 1)
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, 0)
        self.timeline.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.timeline.sliderReleased.connect(self._release_seek)
        self.timeline.sliderMoved.connect(self._seek)
        layout.addWidget(self.timeline)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.play_button = QPushButton("Play")
        self.play_button.setProperty("primary", True)
        self.play_button.setMinimumHeight(34)
        self.play_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_button.clicked.connect(self.toggle)
        self.time_label = QLabel("")
        self.time_label.setProperty("muted", True)
        self.fullscreen_button = QPushButton("Full screen")
        self.fullscreen_button.setMinimumHeight(34)
        self.fullscreen_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fullscreen_button.clicked.connect(self.fullscreen_requested.emit)
        controls.addWidget(self.play_button)
        controls.addWidget(self.time_label, 1)
        controls.addWidget(self.fullscreen_button)
        layout.addLayout(controls)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._next)
        self._set_enabled(False)

    def _set_enabled(self, enabled: bool) -> None:
        for widget in (self.play_button, self.timeline, self.fullscreen_button):
            widget.setEnabled(enabled)

    def clear(self, message: str) -> None:
        self.timer.stop()
        self._release()
        self.path = ""
        self._pixmap = None
        self.video.setPixmap(QPixmap())
        self.video.setText(message)
        self.time_label.setText("")
        self.timeline.setRange(0, 0)
        self.play_button.setText("Play")
        self._set_enabled(False)

    def _release(self) -> None:
        if self.capture is not None:
            self.capture.release()
            self.capture = None

    def load(self, path: str) -> bool:
        """Open a clip and show its first frame. Returns False when it cannot be decoded."""
        if path == self.path and self.capture is not None:
            return True
        self.timer.stop()
        self._release()
        try:
            capture = cv2.VideoCapture(path)
        except Exception:
            capture = None
        if capture is None or not capture.isOpened():
            self.clear("Clip saved, but it cannot be played here")
            return False
        self.capture = capture
        self.path = path
        self.fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        if self.fps < 1 or self.fps > 120:
            self.fps = 25.0
        self.frames = max(0, int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0))
        self.timeline.setRange(0, max(0, self.frames - 1))
        self.timeline.setValue(0)
        self.play_button.setText("Play")
        self._set_enabled(True)
        self._show_next()
        return True

    def toggle(self) -> None:
        if self.capture is None:
            return
        if self.timer.isActive():
            self.timer.stop()
            self.play_button.setText("Play")
            return
        if self.frames and self.timeline.value() >= self.frames - 1:
            self._seek(0)
        self.timer.start(int(1000 / self.fps))
        self.play_button.setText("Pause")

    def pause(self) -> None:
        self.timer.stop()
        self.play_button.setText("Play")

    def _next(self) -> None:
        if not self._show_next():
            self.timer.stop()
            self.play_button.setText("Play")

    def _show_next(self) -> bool:
        if self.capture is None:
            return False
        ok, frame = self.capture.read()
        if not ok:
            return False
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb.shape
        self._pixmap = QPixmap.fromImage(QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy())
        self._paint_frame()
        position = int(self.capture.get(cv2.CAP_PROP_POS_FRAMES) or 0)
        if not self._seeking:
            self.timeline.blockSignals(True)
            self.timeline.setValue(max(0, position - 1))
            self.timeline.blockSignals(False)
        self.time_label.setText(f"{(position / self.fps):.1f} s / {(self.frames / self.fps):.1f} s")
        return True

    def _paint_frame(self) -> None:
        if self._pixmap is not None:
            self.video.setPixmap(self._pixmap.scaled(
                max(1, self.video.width()), max(1, self.video.height()),
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            ))

    def _seek(self, frame: int) -> None:
        if self.capture is not None:
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame))
            self._show_next()

    def _release_seek(self) -> None:
        self._seeking = False
        self._seek(self.timeline.value())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._paint_frame()

    def hideEvent(self, event) -> None:
        self.pause()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self.timer.stop()
        self._release()
        super().closeEvent(event)
