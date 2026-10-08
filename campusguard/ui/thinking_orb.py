from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget


class ThinkingOrb(QWidget):
    """Qt rendering inspired by the MIT-licensed thinking-orbs project.

    CampusGuard uses an original painter implementation of the repository's
    dotted-globe/searching visual so the desktop app stays dependency-light.
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
        self._phase = (self._phase + 0.038) % math.tau
        self.update()

    def paintEvent(self, event) -> None:
        del event

        width = float(self.width())
        height = float(self.height())
        cx = width * 0.5
        cy = height * 0.5
        radius = min(width, height) * 0.34

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        # Monochrome dotted globe: latitude rings + a rotating longitude scan.
        # This follows the visual language of the "searching" orb in
        # Jakub Antalik's thinking-orbs project without embedding its web code.
        ink = QColor("#E3E9F2")
        soft = QColor("#AEB8C7")

        latitudes = (-0.82, -0.52, -0.22, 0.10, 0.40, 0.68)
        columns = 30

        for row, latitude in enumerate(latitudes):
            y = cy + latitude * radius * 0.86
            ring_scale = math.sqrt(max(0.05, 1.0 - latitude * latitude))
            row_phase = self._phase * (0.20 + row * 0.018)

            for index in range(columns):
                angle = math.tau * index / columns + row_phase
                x = cx + math.sin(angle) * radius * ring_scale
                z = math.cos(angle) * ring_scale
                depth = (z + 1.0) * 0.5
                dot = 0.75 + depth * 0.95
                alpha = int(48 + depth * 150)

                color = QColor(ink if row % 2 else soft)
                color.setAlpha(alpha)
                painter.setBrush(color)
                painter.drawEllipse(QPointF(x, y), dot, dot)

        # A brighter dotted meridian sweeps around the sphere.
        scan = self._phase * 1.35
        for index in range(34):
            t = index / 33.0
            latitude = -0.95 + t * 1.9
            y = cy + latitude * radius * 0.86
            ring_scale = math.sqrt(max(0.04, 1.0 - min(1.0, latitude * latitude)))
            angle = scan + latitude * 0.9
            x = cx + math.sin(angle) * radius * ring_scale
            depth = (math.cos(angle) + 1.0) * 0.5

            color = QColor("#F2F5FA")
            color.setAlpha(int(90 + depth * 150))
            dot = 0.9 + depth * 1.15
            painter.setBrush(color)
            painter.drawEllipse(QPointF(x, y), dot, dot)

        center = QColor("#F5F7FB")
        center.setAlpha(205)
        painter.setBrush(center)
        painter.drawEllipse(QPointF(cx, cy), 1.8, 1.8)
        painter.end()

    def stop(self) -> None:
        self._timer.stop()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
