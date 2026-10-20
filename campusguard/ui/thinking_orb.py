from __future__ import annotations

import math

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QSizePolicy, QWidget

LIME = QColor("#C8FF52")
LIME_SOFT = QColor("#D8FF83")
LIME_CORE = QColor("#F4FFD0")


def _with_alpha(color: QColor, alpha: float) -> QColor:
    result = QColor(color)
    result.setAlpha(max(0, min(255, int(alpha))))
    return result


class ThinkingOrb(QWidget):
    """CampusGuard's start-up orb: a breathing lime core with three tilted
    orbit rings, travelling signal dots and a sweeping scan arc.

    It is drawn entirely with QPainter on the CampusGuard website palette
    (lime on near-black). Motion is driven by elapsed wall-clock time, so the
    speed stays constant even if a frame is delayed by other start-up work.
    """

    _RINGS = (
        # (tilt degrees, radius factor, flatness, speed, phase)
        (-24.0, 0.44, 0.34, 1.00, 0.0),
        (38.0, 0.40, 0.30, -1.35, 2.1),
        (96.0, 0.46, 0.38, 0.78, 4.2),
    )

    def __init__(self, parent: QWidget | None = None, size: int = 56) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self.update)
        self._timer.start()

    def _seconds(self) -> float:
        return self._clock.elapsed() / 1000.0

    def paintEvent(self, event) -> None:
        del event
        t = self._seconds()
        size = float(min(self.width(), self.height()))
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        breathe = 0.5 + 0.5 * math.sin(t * 2.3)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        # Soft halo that breathes with the core.
        halo_radius = size * (0.50 + 0.03 * breathe)
        halo = QRadialGradient(center, halo_radius)
        halo.setColorAt(0.0, _with_alpha(LIME, 70 + 40 * breathe))
        halo.setColorAt(0.45, _with_alpha(LIME, 22 + 10 * breathe))
        halo.setColorAt(1.0, _with_alpha(LIME, 0))
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(center, halo_radius, halo_radius)

        # Sweeping scan arc: a fading comet tail on the outer circle.
        sweep_radius = size * 0.47
        sweep_rect = QRectF(
            center.x() - sweep_radius, center.y() - sweep_radius, sweep_radius * 2, sweep_radius * 2
        )
        head = (t * 140.0) % 360.0
        steps = 28
        for step in range(steps):
            fade = 1.0 - step / steps
            pen = QPen(_with_alpha(LIME, 190 * fade * fade), max(1.2, size * 0.012), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            start_angle = (head - step * 3.2) % 360.0
            painter.drawArc(sweep_rect, int(-start_angle * 16), int(-3.4 * 16))
        painter.setPen(Qt.PenStyle.NoPen)

        # Tilted orbit rings with travelling signal dots.
        dots: list[tuple[float, QPointF, float]] = []
        for tilt, radius_factor, flatness, speed, phase in self._RINGS:
            radius = size * radius_factor
            ry = radius * flatness
            painter.save()
            painter.translate(center)
            painter.rotate(tilt)
            painter.setPen(QPen(_with_alpha(LIME, 46), max(1.0, size * 0.008)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(0, 0), radius, ry)
            painter.setPen(Qt.PenStyle.NoPen)
            for trail in range(7):
                angle = t * speed * 1.6 + phase - trail * 0.16 * (1 if speed > 0 else -1)
                x, y = radius * math.cos(angle), ry * math.sin(angle)
                depth = 0.5 + 0.5 * math.sin(angle)  # 1 = in front of the core
                fade = 1.0 - trail / 7.0
                dot = size * (0.011 + 0.014 * depth) * (0.55 + 0.45 * fade)
                painter.setBrush(_with_alpha(LIME_SOFT if trail == 0 else LIME, (70 + 185 * depth) * fade))
                painter.drawEllipse(QPointF(x, y), dot, dot)
            painter.restore()

        # Core: bright centre fading into lime.
        core_radius = size * (0.135 + 0.014 * breathe)
        core = QRadialGradient(QPointF(center.x() - core_radius * 0.25, center.y() - core_radius * 0.3), core_radius * 1.3)
        core.setColorAt(0.0, LIME_CORE)
        core.setColorAt(0.55, LIME)
        core.setColorAt(1.0, _with_alpha(LIME, 70))
        painter.setBrush(QBrush(core))
        painter.drawEllipse(center, core_radius, core_radius)
        painter.end()

    def stop(self) -> None:
        self._timer.stop()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
