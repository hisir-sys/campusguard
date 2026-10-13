from __future__ import annotations

import math
import struct
import tempfile
import threading
import wave
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from campusguard.ui.theme import get_palette, rgba

try:
    import winsound
except ImportError:  # Non-Windows development/test environments.
    winsound = None


class SeverityAlertToast(QFrame):
    """Compact, auto-dismissing glass alert that lives inside the app window."""

    view_requested = Signal(str)

    _LEVELS = {
        "medium": {
            "title": "ALERT",
            "accent": "#D9A441",
            "sound_ms": 2000,
            "popup_ms": 5000,
            "interval_ms": 1000,
            "beats": 2,
        },
        "high": {
            "title": "CRITICAL ALERT",
            "accent": "#F07838",
            "sound_ms": 5000,
            "popup_ms": 7000,
            "interval_ms": 500,
            "beats": 0,
        },
        "critical": {
            "title": "DANGER",
            "accent": "#FF343F",
            "sound_ms": 10000,
            "popup_ms": 15000,
            "interval_ms": 500,
            "beats": 0,
        },
    }

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("severityAlertToast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedWidth(410)
        self.setMinimumHeight(166)
        self._incident_id = ""
        self._level = "medium"
        self._sound_elapsed = 0
        self._sound_beats = 0
        self._audio_output = QAudioOutput(self)
        self._audio_player = QMediaPlayer(self)
        self._audio_player.setAudioOutput(self._audio_output)
        self._audio_output.setVolume(1.0)
        self._user_alarm_path = (
            Path(__file__).resolve().parents[2] / "assets" / "campusguard_alert.mp3"
        )

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(240)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._fade_out)
        self._sound_timer = QTimer(self)
        self._sound_timer.timeout.connect(self._sound_tick)
        self._sound_timer.setInterval(500)

        self._title = QLabel("SECURITY ALERT")
        self._title.setObjectName("severityAlertTitle")
        self._title.setStyleSheet("font-size: 10pt; font-weight: 850; letter-spacing: 1px; background: transparent;")
        self._message = QLabel()
        self._message.setObjectName("severityAlertMessage")
        self._message.setWordWrap(True)
        self._message.setStyleSheet("font-size: 10pt; background: transparent;")
        self._confidence = QLabel()
        self._confidence.setStyleSheet("font-size: 9pt; font-weight: 750; background: transparent;")

        self._view = QPushButton("View")
        self._view.setProperty("primary", True)
        self._view.setMinimumHeight(34)
        self._view.setCursor(Qt.CursorShape.PointingHandCursor)
        self._view.clicked.connect(self._view_incident)
        self._ok = QPushButton("OK")
        self._ok.setProperty("secondaryButton", True)
        self._ok.setMinimumHeight(34)
        self._ok.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ok.clicked.connect(self.dismiss)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 4, 0, 0)
        actions.setSpacing(8)
        actions.addStretch(1)
        actions.addWidget(self._view)
        actions.addWidget(self._ok)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 15, 18, 14)
        layout.setSpacing(7)
        layout.addWidget(self._title)
        layout.addWidget(self._message)
        layout.addWidget(self._confidence)
        layout.addLayout(actions)

        # Opacity is animated directly so the glass toast fades smoothly in and out.
        self._apply_theme()

    def _apply_theme(self) -> None:
        palette = get_palette()
        accent = self._LEVELS[self._level]["accent"]
        is_critical = self._level == "critical"
        glass_alpha = 220 if palette.name == "dark" else 232
        border_alpha = 170 if is_critical else 112
        self.setStyleSheet(
            f"""
            QFrame#severityAlertToast {{
                background: {rgba(palette.glass, glass_alpha)};
                color: {palette.text};
                border: 1px solid {rgba(accent, border_alpha)};
                border-left: 4px solid {accent};
                border-radius: 19px;
            }}
            QLabel#severityAlertTitle {{ color: {accent}; }}
            QLabel#severityAlertMessage {{ color: {palette.text}; }}
            """
        )

    def show_alert(
        self,
        incident_id: str,
        event: str,
        camera_name: str,
        confidence: float,
    ) -> None:
        score = confidence * 100.0 if confidence <= 1.0 else confidence
        if score < 70:
            return
        self._level = "medium" if score < 85 else "high" if score < 95 else "critical"
        config = self._LEVELS[self._level]
        self._incident_id = incident_id
        self._sound_elapsed = 0
        self._sound_beats = 0
        self._title.setText(config["title"])
        self._message.setText(f"{event} · {camera_name}")
        self._confidence.setText(f"Peak model confidence  {score:.1f}%")
        self._apply_theme()

        self._dismiss_timer.stop()
        self._sound_timer.stop()
        self._fade.stop()
        self._opacity.setOpacity(0.0)
        self.adjustSize()
        self.setFixedHeight(max(166, self.sizeHint().height()))
        self._position()
        self.show()
        self.raise_()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

        self._dismiss_timer.start(config["popup_ms"])
        self._sound_timer.setInterval(config["interval_ms"])
        # Start a dedicated repeating two-tone alarm immediately. The sound is
        # synthesized locally (no bundled copyrighted siren recording or network file).
        self._play_alarm()
        self._sound_elapsed = 0
        self._sound_beats = 1
        self._sound_timer.start()

    def update_assessment(
        self, incident_id: str, confidence: float
    ) -> None:
        """Refresh the visible peak and escalate an existing toast without duplicating it."""
        if incident_id != self._incident_id or not self.isVisible():
            return
        score = confidence * 100.0 if confidence <= 1.0 else confidence
        if score < 70:
            return
        new_level = "medium" if score < 85 else "high" if score < 95 else "critical"
        old_level = self._level
        self._confidence.setText(f"Peak model confidence  {score:.1f}%")
        if new_level == old_level:
            return

        self._level = new_level
        config = self._LEVELS[new_level]
        self._title.setText(config["title"])
        self._apply_theme()
        self._dismiss_timer.start(config["popup_ms"])
        self._sound_timer.stop()
        self._sound_elapsed = 0
        self._sound_beats = 0
        self._sound_timer.setInterval(config["interval_ms"])
        self._play_alarm()
        self._sound_beats = 1
        self._sound_timer.start()

    def _position(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        # Center the alert over the app canvas so it reads as a deliberate
        # glass incident dialog, not a small notification competing with cards.
        x = max(18, (parent.width() - self.width()) // 2)
        y = max(18, (parent.height() - self.height()) // 2)
        self.move(x, y)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position()

    @staticmethod
    def _alarm_wave_path() -> Path:
        """Create a short, repeating two-tone emergency-style alert locally."""
        tone_path = Path(tempfile.gettempdir()) / "campusguard_severity_alarm.wav"
        if tone_path.is_file() and tone_path.stat().st_size > 1000:
            return tone_path

        sample_rate = 22050
        duration = 1.0
        amplitude = 15000
        frames = bytearray()
        for i in range(int(sample_rate * duration)):
            t = i / sample_rate
            # Alternating rising/falling tones, with short gaps for a clear alert pulse.
            phase = t % 0.5
            if phase >= 0.42:
                sample = 0
            else:
                frequency = 880.0 if phase < 0.21 else 660.0
                envelope = min(1.0, phase / 0.012, (0.42 - phase) / 0.012)
                sample = int(amplitude * max(0.0, envelope) * math.sin(2.0 * math.pi * frequency * t))
            frames.extend(struct.pack("<h", sample))

        with wave.open(str(tone_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(bytes(frames))
        return tone_path

    def _play_alarm(self) -> None:
        """Play the user's supplied alarm clip; fall back to a Windows siren pattern."""
        if self._user_alarm_path.is_file():
            try:
                self._stop_alarm()
                self._audio_player.setSource(QUrl.fromLocalFile(str(self._user_alarm_path)))
                self._audio_player.setLoops(QMediaPlayer.Loops.Infinite)
                self._audio_player.play()
                return
            except (RuntimeError, OSError):
                pass

        self._stop_alarm()
        if winsound is None:
            QApplication.beep()
            return

        stop_event = threading.Event()
        self._alarm_stop_event = stop_event

        def play_pattern() -> None:
            # Severity controls pulse speed: slow and restrained at medium,
            # quicker at high, and rapid/urgent at critical.
            patterns = {
                "medium": ((950, 520), (720, 520)),
                "high": ((1250, 330), (900, 330)),
                "critical": ((1500, 170), (1050, 170), (1500, 170), (820, 170)),
            }
            pattern = patterns.get(self._level, patterns["medium"])
            while not stop_event.is_set():
                for frequency, duration in pattern:
                    if stop_event.is_set():
                        break
                    try:
                        winsound.Beep(frequency, duration)
                    except (RuntimeError, OSError):
                        return
                    if stop_event.wait(0.025):
                        break

        self._alarm_thread = threading.Thread(
            target=play_pattern, name="CampusGuardAlertSound", daemon=True
        )
        self._alarm_thread.start()

    def _stop_alarm(self) -> None:
        stop_event = getattr(self, "_alarm_stop_event", None)
        if stop_event is not None:
            stop_event.set()
        try:
            self._audio_player.stop()
        except (RuntimeError, AttributeError):
            pass
        if winsound is not None:
            try:
                winsound.PlaySound(None, 0)
            except (RuntimeError, OSError):
                pass

    def _sound_tick(self) -> None:
        config = self._LEVELS[self._level]
        self._sound_elapsed += config["interval_ms"]
        if self._sound_elapsed >= config["sound_ms"]:
            self._sound_timer.stop()
            self._stop_alarm()
            return

    def _view_incident(self) -> None:
        incident_id = self._incident_id
        self.dismiss()
        if incident_id:
            self.view_requested.emit(incident_id)

    def dismiss(self) -> None:
        self._dismiss_timer.stop()
        self._fade_out()

    def _fade_out(self) -> None:
        self._sound_timer.stop()
        self._stop_alarm()
        self._fade.stop()
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(0.0)
        try:
            self._fade.finished.disconnect(self._hide_after_fade)
        except (TypeError, RuntimeError):
            pass
        self._fade.finished.connect(self._hide_after_fade)
        self._fade.start()

    def _hide_after_fade(self) -> None:
        try:
            self._fade.finished.disconnect(self._hide_after_fade)
        except (TypeError, RuntimeError):
            pass
        self.hide()
