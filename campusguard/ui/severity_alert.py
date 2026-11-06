from __future__ import annotations

import math
import time

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from campusguard import alarm_sound
from campusguard.ui.theme import get_palette, rgba


class SeverityAlertToast(QFrame):
    """Compact, auto-dismissing glass alert that lives inside the app window."""

    view_requested = Signal(str)

    _LEVELS = {
        "medium": {"title": "ALERT", "accent": "#E0A93B", "popup_ms": 5000, "glyph": "!"},
        "high": {"title": "CRITICAL ALERT", "accent": "#F07838", "popup_ms": 7000, "glyph": "!!"},
        "critical": {"title": "DANGER", "accent": "#FF343F", "popup_ms": 15000, "glyph": "!!!"},
    }

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("severityAlertToast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedWidth(430)
        self._incident_id = ""
        self._level = "medium"
        self._pulse_started = 0.0

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(240)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._fade_out)
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(70)
        self._pulse_timer.timeout.connect(self._pulse)

        self._badge = QLabel("!")
        self._badge.setObjectName("severityAlertBadge")
        self._badge.setFixedSize(46, 46)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title = QLabel("ALERT")
        self._title.setObjectName("severityAlertTitle")
        self._headline = QLabel()
        self._headline.setObjectName("severityAlertMessage")
        self._headline.setWordWrap(True)
        self._detail = QLabel()
        self._detail.setObjectName("severityAlertDetail")
        self._close = QPushButton("\u2715")
        self._close.setObjectName("severityAlertClose")
        self._close.setFixedSize(26, 26)
        self._close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close.setToolTip("Dismiss")
        self._close.clicked.connect(self.dismiss)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        text.addWidget(self._title)
        text.addWidget(self._headline)
        text.addWidget(self._detail)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(14)
        head.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignTop)
        head.addLayout(text, 1)
        head.addWidget(self._close, 0, Qt.AlignmentFlag.AlignTop)

        self._confidence_label = QLabel("Confidence")
        self._confidence_label.setObjectName("severityAlertDetail")
        self._confidence_value = QLabel()
        self._confidence_value.setObjectName("severityAlertValue")
        self._bar = QProgressBar()
        self._bar.setObjectName("severityAlertBar")
        self._bar.setRange(0, 1000)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(7)
        meter = QHBoxLayout()
        meter.setContentsMargins(0, 0, 0, 0)
        meter.addWidget(self._confidence_label)
        meter.addStretch(1)
        meter.addWidget(self._confidence_value)

        self._view = QPushButton("View incident")
        self._view.setObjectName("severityAlertView")
        self._view.setMinimumHeight(36)
        self._view.setCursor(Qt.CursorShape.PointingHandCursor)
        self._view.clicked.connect(self._view_incident)
        self._ok = QPushButton("Dismiss")
        self._ok.setObjectName("severityAlertDismiss")
        self._ok.setMinimumHeight(36)
        self._ok.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ok.clicked.connect(self.dismiss)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 4, 0, 0)
        actions.setSpacing(8)
        actions.addStretch(1)
        actions.addWidget(self._ok)
        actions.addWidget(self._view)

        self._countdown = QProgressBar()
        self._countdown.setObjectName("severityAlertCountdown")
        self._countdown.setRange(0, 1000)
        self._countdown.setValue(1000)
        self._countdown.setTextVisible(False)
        self._countdown.setFixedHeight(3)
        self._countdown_anim = QPropertyAnimation(self._countdown, b"value", self)
        self._countdown_anim.setEasingCurve(QEasingCurve.Type.Linear)

        body = QVBoxLayout()
        body.setContentsMargins(18, 16, 16, 12)
        body.setSpacing(10)
        body.addLayout(head)
        body.addLayout(meter)
        body.addWidget(self._bar)
        body.addLayout(actions)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(body)
        layout.addWidget(self._countdown)

        self._apply_theme()
        QTimer.singleShot(2500, alarm_sound.prewarm)   # build sounds off the UI thread

    def _apply_theme(self, border_alpha: int | None = None) -> None:
        palette = get_palette()
        accent = self._LEVELS[self._level]["accent"]
        is_critical = self._level == "critical"
        glass_alpha = 236 if palette.name == "dark" else 244
        if border_alpha is None:
            border_alpha = 190 if is_critical else 130
        self._badge.setText(self._LEVELS[self._level]["glyph"])
        self.setStyleSheet(
            f"""
            QFrame#severityAlertToast {{
                background: {rgba(palette.glass, glass_alpha)};
                color: {palette.text};
                border: 1px solid {rgba(accent, border_alpha)};
                border-left: 5px solid {accent};
                border-radius: 18px;
            }}
            QLabel {{ background: transparent; }}
            QLabel#severityAlertBadge {{
                background: {rgba(accent, 46)}; color: {accent};
                border: 1px solid {rgba(accent, 140)}; border-radius: 23px;
                font-size: 15pt; font-weight: 900;
            }}
            QLabel#severityAlertTitle {{ color: {accent}; font-size: 9pt; font-weight: 900; letter-spacing: 1.6px; }}
            QLabel#severityAlertMessage {{ color: {palette.text}; font-size: 13pt; font-weight: 800; }}
            QLabel#severityAlertDetail {{ color: {palette.muted}; font-size: 9pt; }}
            QLabel#severityAlertValue {{ color: {accent}; font-size: 11pt; font-weight: 900; }}
            QPushButton#severityAlertClose {{
                background: transparent; color: {palette.muted}; border: none; border-radius: 13px; font-size: 10pt;
            }}
            QPushButton#severityAlertClose:hover {{ background: {rgba(palette.text, 24)}; color: {palette.text}; }}
            QPushButton#severityAlertView {{
                background: {accent}; color: #130d06; border: none; border-radius: 10px;
                padding: 0 16px; font-weight: 800;
            }}
            QPushButton#severityAlertView:hover {{ background: {rgba(accent, 225)}; }}
            QPushButton#severityAlertDismiss {{
                background: {rgba(palette.text, 16)}; color: {palette.text}; border: 1px solid {rgba(palette.text, 40)};
                border-radius: 10px; padding: 0 16px; font-weight: 700;
            }}
            QPushButton#severityAlertDismiss:hover {{ background: {rgba(palette.text, 30)}; }}
            QProgressBar#severityAlertBar {{
                background: {rgba(palette.text, 22)}; border: none; border-radius: 3px;
            }}
            QProgressBar#severityAlertBar::chunk {{ background: {accent}; border-radius: 3px; }}
            QProgressBar#severityAlertCountdown {{ background: transparent; border: none; }}
            QProgressBar#severityAlertCountdown::chunk {{ background: {rgba(accent, 200)}; }}
            """
        )

    def _pulse(self) -> None:
        """Critical alerts breathe: the border glows in and out until dismissed."""
        phase = (time.monotonic() - self._pulse_started) * 5.0
        self._apply_theme(border_alpha=int(150 + 100 * (0.5 + 0.5 * math.sin(phase))))

    def _present(self, incident_id: str, event: str, camera_name: str, score: float, peak: bool) -> None:
        self._level = "medium" if score < 85 else "high" if score < 95 else "critical"
        config = self._LEVELS[self._level]
        self._incident_id = incident_id
        self._title.setText(config["title"])
        self._headline.setText(event)
        self._detail.setText(f"{camera_name}  \u00b7  {time.strftime('%H:%M:%S')}")
        self._confidence_label.setText("Peak confidence" if peak else "Confidence")
        self._confidence_value.setText(f"{score:.0f}%")
        self._bar.setValue(int(max(0.0, min(100.0, score)) * 10))
        self._apply_theme()
        if self._level == "critical":
            self._pulse_started = time.monotonic()
            self._pulse_timer.start()
        else:
            self._pulse_timer.stop()
        self._dismiss_timer.start(config["popup_ms"])
        self._countdown_anim.stop()
        self._countdown_anim.setDuration(config["popup_ms"])
        self._countdown_anim.setStartValue(1000)
        self._countdown_anim.setEndValue(0)
        self._countdown_anim.start()
        self.adjustSize()
        self.setFixedHeight(self.sizeHint().height())
        self._position()
        self.show()
        self.raise_()

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
        self._fade.stop()
        self._opacity.setOpacity(0.0)
        self._present(incident_id, event, camera_name, score, peak=False)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        alarm_sound.play(self._level)

    def update_alert(
        self,
        incident_id: str,
        event: str,
        camera_name: str,
        confidence: float,
    ) -> None:
        """Refresh the same incident's peak confidence without replaying its alarm."""
        score = confidence * 100.0 if confidence <= 1.0 else confidence
        if score < 70:
            return
        self._fade.stop()
        self._opacity.setOpacity(1.0)
        self._present(incident_id, event, camera_name, score, peak=True)

    def _position(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.move(max(18, parent.width() - self.width() - 24), 22)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position()

    def _view_incident(self) -> None:
        incident_id = self._incident_id
        self.dismiss()
        if incident_id:
            self.view_requested.emit(incident_id)

    def dismiss(self) -> None:
        self._dismiss_timer.stop()
        self._fade_out()

    def _fade_out(self) -> None:
        alarm_sound.stop()
        self._pulse_timer.stop()
        self._countdown_anim.stop()
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
