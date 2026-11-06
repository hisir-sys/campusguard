from __future__ import annotations

import math

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QConicalGradient, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QSizePolicy, QWidget

from campusguard.ui.theme import get_palette

LIME = QColor("#C8FF52")


def _alpha(color: QColor, alpha: float) -> QColor:
    result = QColor(color)
    result.setAlphaF(max(0.0, min(1.0, alpha)))
    return result


class ThinkingOrb(QWidget):
    """CampusGuard's "thinking" orb: a glass sphere with a slowly swirling aurora inside,
    a travelling rim light, glossy reflections, and a ring of dots whose brightness
    ripples around it (the dotted-sphere motif of the CampusGuard logo animation).

    Drawn entirely with QPainter on the active theme's palette (dark glass on near-black,
    frosted glass on near-white). Motion follows wall-clock time, so a delayed frame never
    changes the speed.
    """

    DOTS = 28

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

    def retint(self) -> None:
        self.update()

    def paintEvent(self, event) -> None:
        del event
        t = self._seconds()
        palette = get_palette()
        light = palette.name == "light"
        accent = QColor("#7DB313") if light else QColor(LIME)
        size = float(min(self.width(), self.height()))
        centre = QPointF(self.width() / 2.0, self.height() / 2.0)
        radius = size * 0.31
        breathe = 0.5 + 0.5 * math.sin(t * 2.0)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        # 1) Ambient glow (dark) or soft contact shadow (light).
        if light:
            shadow = QRadialGradient(QPointF(centre.x(), centre.y() + radius * 1.18), radius * 1.25)
            shadow.setColorAt(0.0, QColor(23, 27, 22, 52))
            shadow.setColorAt(1.0, QColor(23, 27, 22, 0))
            painter.setBrush(QBrush(shadow))
            painter.drawEllipse(QPointF(centre.x(), centre.y() + radius * 1.18), radius * 1.25, radius * 0.32)
        halo = QRadialGradient(centre, radius * 1.9)
        halo.setColorAt(0.0, _alpha(accent, (0.20 if not light else 0.16) + 0.08 * breathe))
        halo.setColorAt(0.6, _alpha(accent, 0.05))
        halo.setColorAt(1.0, _alpha(accent, 0.0))
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(centre, radius * 1.9, radius * 1.9)

        # 2) Ring of dots with a brightness ripple travelling around it.
        ring = size * 0.455
        for i in range(self.DOTS):
            angle = (i / self.DOTS) * math.tau
            wave = 0.5 + 0.5 * math.cos(angle - t * 1.7)
            wave = wave ** 3
            dot = size * (0.0065 + 0.0095 * wave)
            painter.setBrush(_alpha(accent if wave > 0.35 else QColor(palette.muted), 0.28 + 0.72 * wave))
            painter.drawEllipse(QPointF(centre.x() + ring * math.cos(angle), centre.y() + ring * math.sin(angle)), dot, dot)

        # 3) Glass body.
        body = QRadialGradient(QPointF(centre.x() - radius * 0.35, centre.y() - radius * 0.45), radius * 1.6)
        if light:
            body.setColorAt(0.0, QColor(255, 255, 255, 250))
            body.setColorAt(0.65, QColor(238, 243, 230, 235))
            body.setColorAt(1.0, QColor(214, 224, 200, 235))
        else:
            body.setColorAt(0.0, QColor(44, 54, 42, 245))
            body.setColorAt(0.6, QColor(18, 24, 18, 248))
            body.setColorAt(1.0, QColor(7, 10, 7, 252))
        painter.setBrush(QBrush(body))
        painter.drawEllipse(centre, radius, radius)

        # 4) Aurora swirling inside the glass.
        clip = QPainterPath()
        clip.addEllipse(centre, radius, radius)
        painter.save()
        painter.setClipPath(clip)
        blobs = (
            (accent, 0.0, 0.55, 0.9),
            (QColor("#5FF0C2") if not light else QColor("#3FCFA0"), 2.1, 0.50, -1.1),
            (QColor("#E7FF8A") if not light else QColor("#B6D94A"), 4.2, 0.45, 0.7),
        )
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceOver if light else QPainter.CompositionMode.CompositionMode_Plus
        )
        for color, phase, reach, speed in blobs:
            a = t * speed + phase
            pos = QPointF(centre.x() + math.cos(a) * radius * reach, centre.y() + math.sin(a * 1.3) * radius * reach)
            blob_radius = radius * (0.85 + 0.15 * math.sin(t * 1.6 + phase))
            gradient = QRadialGradient(pos, blob_radius)
            gradient.setColorAt(0.0, _alpha(color, 0.62 if not light else 0.55))
            gradient.setColorAt(0.5, _alpha(color, 0.18))
            gradient.setColorAt(1.0, _alpha(color, 0.0))
            painter.setBrush(QBrush(gradient))
            painter.drawEllipse(centre, radius, radius)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # Inner depth: darker/lighter toward the edge so it reads as a sphere.
        depth = QRadialGradient(centre, radius)
        depth.setColorAt(0.0, QColor(0, 0, 0, 0))
        depth.setColorAt(0.72, QColor(0, 0, 0, 0))
        depth.setColorAt(1.0, QColor(0, 0, 0, 90 if not light else 38))
        painter.setBrush(QBrush(depth))
        painter.drawEllipse(centre, radius, radius)
        painter.restore()

        # 5) Rim light that travels around the edge.
        rim = QConicalGradient(centre, -math.degrees(t * 1.2))
        bright = QColor(255, 255, 255, 235 if not light else 255)
        rim.setColorAt(0.00, bright)
        rim.setColorAt(0.16, _alpha(accent, 0.75))
        rim.setColorAt(0.40, QColor(255, 255, 255, 36 if not light else 120))
        rim.setColorAt(0.70, QColor(255, 255, 255, 18 if not light else 90))
        rim.setColorAt(1.00, bright)
        painter.setPen(QPen(QBrush(rim), max(1.2, size * 0.011)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(centre, radius, radius)
        painter.setPen(Qt.PenStyle.NoPen)

        # 6) Glossy reflections: large soft highlight top-left, small bright glint, faint bottom bounce.
        gloss = QLinearGradient(QPointF(centre.x(), centre.y() - radius), QPointF(centre.x(), centre.y() - radius * 0.1))
        gloss.setColorAt(0.0, QColor(255, 255, 255, 190 if not light else 235))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(gloss))
        painter.drawEllipse(QRectF(centre.x() - radius * 0.66, centre.y() - radius * 0.90, radius * 1.32, radius * 0.78))
        painter.setBrush(QColor(255, 255, 255, 235))
        glint = radius * 0.075
        painter.drawEllipse(QPointF(centre.x() - radius * 0.40, centre.y() - radius * 0.56), glint * 1.4, glint)
        bounce = QRadialGradient(QPointF(centre.x() + radius * 0.25, centre.y() + radius * 0.92), radius * 0.62)
        bounce.setColorAt(0.0, _alpha(accent, 0.34 if not light else 0.30))
        bounce.setColorAt(1.0, _alpha(accent, 0.0))
        painter.setBrush(QBrush(bounce))
        painter.setClipPath(clip)
        painter.drawEllipse(QPointF(centre.x() + radius * 0.25, centre.y() + radius * 0.92), radius * 0.62, radius * 0.34)
        painter.end()

    def stop(self) -> None:
        self._timer.stop()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
