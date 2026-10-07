from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


class ThinkingOrb(QWidget):
    """Lightweight Qt port inspired by Jakub Antalik's thinking-orbs.

    CampusGuard uses its own Qt painter implementation rather than bringing a
    browser/React runtime into the desktop app. The source project is MIT
    licensed; this widget is an original Qt rendering adapted for CampusGuard.
    """

    def __init__(self, parent: QWidget | None = None, size: int = 56) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.055) % (math.tau)
        self.update()

    def paintEvent(self, event) -> None:
        del event
        size = min(self.width(), self.height())
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        radius = size * 0.30

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # A restrained monochrome orb that fits CampusGuard's indigo/slate UI.
        accent = QColor("#6F8CFF")
        soft = QColor("#AFC0FF")

        for ring, count in enumerate((18, 24, 30)):
            ring_phase = self._phase * (0.82 + ring * 0.12) + ring * 1.45
            ring_radius = radius * (0.55 + ring * 0.22)
            for index in range(count):
                angle = math.tau * index / count + ring_phase
                wobble = 1.0 + 0.10 * math.sin(self._phase * 1.7 + index * 0.55 + ring)
                x = cx + math.cos(angle) * ring_radius * wobble
                y = cy + math.sin(angle) * ring_radius * 0.62 * wobble

                depth = (math.sin(angle) + 1.0) * 0.5
                dot = 1.0 + depth * 1.15
                alpha = int(70 + depth * 145)
                color = QColor(accent if ring != 1 else soft)
                color.setAlpha(alpha)

                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(QPointF(x, y), dot, dot)

        painter.end()

    def stop(self) -> None:
        self._timer.stop()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
