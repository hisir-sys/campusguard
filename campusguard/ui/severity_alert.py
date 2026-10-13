from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt, Signal
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
        # Start immediately; subsequent ticks make the sound pattern audible without
        # blocking the UI thread. QApplication.beep uses the system's configured alert sound.
        self._play_beep()
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
        self._play_beep()
        self._sound_beats = 1
        self._sound_timer.start()

    def _position(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.move(max(18, parent.width() - self.width() - 24), 22)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position()

    @staticmethod
    def _play_beep() -> None:
        """Play a short audible Windows tone, falling back to Qt on other systems."""
        if winsound is not None:
            try:
                # A generated tone does not depend on the Windows system-sound setting.
                winsound.Beep(1000, 140)
                return
            except (RuntimeError, OSError):
                pass
        QApplication.beep()

    def _sound_tick(self) -> None:
        config = self._LEVELS[self._level]
        self._sound_elapsed += config["interval_ms"]
        if self._sound_elapsed >= config["sound_ms"]:
            self._sound_timer.stop()
            return
        if self._level == "medium" and self._sound_beats >= config["beats"]:
            self._sound_timer.stop()
            return
        self._play_beep()
        self._sound_beats += 1

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
