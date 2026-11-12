"""The v3 "Fight detected" modal: a scrim, a glass card that pops in, and two actions."""
from __future__ import annotations

import time

from PySide6.QtCore import QEasingCurve, QTimer, QVariantAnimation, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QVBoxLayout, QWidget

from campusguard import alarm_sound
from campusguard.ui.theme import get_palette, rgba
from campusguard.ui.v3widgets import GhostButton, GlassCard, make_pill, mono


class FightAlert(QWidget):
    """Covers the window with a soft scrim and centres the alert card. Critical alerts stay
    (and keep sounding) until someone acts; lower levels close themselves after a while."""

    view_requested = Signal(str)

    # title text is shared with the severity labels used on the Incidents and Alerts pages
    _LEVELS = {
        "medium": {"title": "ALERT", "auto_ms": 12000},
        "high": {"title": "CRITICAL ALERT", "auto_ms": 20000},
        "critical": {"title": "DANGER", "auto_ms": 0},
    }
    CARD_WIDTH = 420

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("fightAlert")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._incident_id = ""
        self._level = "medium"
        self._open = 0.0

        self._card = GlassCard(self, radius=24, lift=False)
        self._card.setObjectName("fightAlertCard")
        self._card.setFixedWidth(self.CARD_WIDTH)
        self.restyle()
        self._pill = make_pill("Alert", "new")
        self._pill.setMinimumWidth(56)
        self._headline = QLabel("Fight detected")
        self._headline.setObjectName("fightAlertTitle")
        self._meta = QLabel()
        self._meta.setFont(mono(9))
        self._meta.setProperty("muted", True)
        self._meta.setWordWrap(True)
        self._review = GhostButton("Review clip", primary=True)
        self._review.clicked.connect(self._view_incident)
        self._dismiss = GhostButton("Dismiss")
        self._dismiss.clicked.connect(self.dismiss)

        actions = QVBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self._review)
        actions.addWidget(self._dismiss)
        body = QVBoxLayout(self._card)
        body.setContentsMargins(28, 28, 28, 24)
        body.setSpacing(12)
        body.addWidget(self._pill, 0, Qt.AlignmentFlag.AlignLeft)
        body.addWidget(self._headline)
        body.addWidget(self._meta)
        body.addSpacing(4)
        body.addLayout(actions)

        self._effect = QGraphicsOpacityEffect(self._card)
        self._card.setGraphicsEffect(self._effect)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(500)
        self._anim.valueChanged.connect(self._on_anim)
        self._anim.finished.connect(self._anim_done)
        self._closing = False
        self._auto = QTimer(self)
        self._auto.setSingleShot(True)
        self._auto.timeout.connect(self.dismiss)
        self.hide()
        QTimer.singleShot(2500, alarm_sound.prewarm)   # build sounds off the UI thread

    def restyle(self) -> None:
        p = get_palette()
        self._card.setStyleSheet(
            f"""
            QFrame#fightAlertCard {{ background: {rgba(p.glass, 252)}; border: none; border-radius: 24px; }}
            QLabel#fightAlertTitle {{ color: {p.text}; font-family: Outfit, Inter, sans-serif;
                font-size: 22px; font-weight: 600; background: transparent; }}
            """
        )

    # ----- animation ------------------------------------------------------

    def _run(self, start: float, end: float, curve: QEasingCurve.Type, ms: int) -> None:
        self._anim.stop()
        self._anim.setEasingCurve(curve)
        self._anim.setDuration(ms)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.start()

    def _on_anim(self, value) -> None:
        self._open = float(value)
        self._effect.setOpacity(max(0.0, min(1.0, self._open * 1.5)))
        self._place_card()
        self.update()

    def _anim_done(self) -> None:
        if self._closing:
            self._closing = False
            self.hide()

    def _place_card(self) -> None:
        self._card.adjustSize()
        size = self._card.sizeHint()
        x = (self.width() - self.CARD_WIDTH) // 2
        rise = int((1.0 - min(1.0, self._open)) * 18)
        y = (self.height() - size.height()) // 2 + rise
        self._card.setGeometry(x, max(12, y), self.CARD_WIDTH, size.height())

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, int(max(0.0, min(1.0, self._open)) * 150)))
        painter.end()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_card()

    def mousePressEvent(self, event) -> None:
        if not self._card.geometry().contains(event.position().toPoint()):
            self.dismiss()
        event.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss()
            return
        super().keyPressEvent(event)

    # ----- public API -----------------------------------------------------

    def _present(self, incident_id: str, camera_name: str, score: float, replay: bool) -> None:
        self.restyle()
        self._level = "medium" if score < 85 else "high" if score < 95 else "critical"
        config = self._LEVELS[self._level]
        self._incident_id = incident_id
        self._pill.setText(config["title"].capitalize())
        self._meta.setText(f"{incident_id} · {camera_name} · {score:.0f}% · {time.strftime('%d %b %H:%M')}")
        if config["auto_ms"]:
            self._auto.start(config["auto_ms"])
        else:
            self._auto.stop()
        self.setGeometry(self.parentWidget().rect())
        already = self.isVisible() and not self._closing
        self._closing = False
        self.show()
        self.raise_()
        if already or not replay:
            self._anim.stop()
            self._open = 1.0
            self._effect.setOpacity(1.0)
            self._place_card()
            self.update()
        else:
            self._open = 0.0
            self._effect.setOpacity(0.0)
            self._run(0.0, 1.0, QEasingCurve.Type.OutBack, 500)
        self._review.setFocus()

    def show_alert(self, incident_id: str, event: str, camera_name: str, confidence: float) -> None:
        del event
        score = confidence * 100.0 if confidence <= 1.0 else confidence
        if score < 70:
            return
        self._present(incident_id, camera_name, score, replay=True)
        alarm_sound.play(self._level)

    def update_alert(self, incident_id: str, event: str, camera_name: str, confidence: float) -> None:
        """Refresh the same incident's peak confidence without replaying its alarm."""
        del event
        score = confidence * 100.0 if confidence <= 1.0 else confidence
        if score < 70:
            return
        self._present(incident_id, camera_name, score, replay=False)

    def _view_incident(self) -> None:
        incident_id = self._incident_id
        self.dismiss()
        if incident_id:
            self.view_requested.emit(incident_id)

    def dismiss(self) -> None:
        self._auto.stop()
        alarm_sound.stop()
        if not self.isVisible() or self._closing:
            return
        self._closing = True
        self._run(self._open, 0.0, QEasingCurve.Type.InCubic, 220)
