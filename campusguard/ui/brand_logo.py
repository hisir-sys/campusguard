"""CampusGuard logo: a lime shield with a check mark, drawn in code so it is sharp at any size.

LogoMark   - the static logo.
LogoReveal - the launch animation: a glass tile of liquid colour dissolves while the
             shield and check draw themselves in, then the logo settles with a soft glow.
Colours follow the active theme (dark / light).
"""
from __future__ import annotations

import math
import sqlite3
import json
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from campusguard.ui.theme import get_palette

LOGO_LIME_DARK = "#C8FF52"
LOGO_LIME_LIGHT = "#6FA60F"          # darker lime so the mark stays readable on near-white


def logo_color() -> QColor:
    return QColor(LOGO_LIME_LIGHT if get_palette().name == "light" else LOGO_LIME_DARK)


def saved_theme() -> str:
    """The theme saved in the app database ("dark" when unknown). Read-only and cheap,
    so the launch screen can match the user's theme before the app is fully loaded."""
    try:
        from campusguard.storage import application_data_dir

        path = Path(application_data_dir()) / "campusguard.db"
        if not path.exists():
            return "dark"
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=1)
        try:
            row = connection.execute("SELECT value FROM settings WHERE key = 'theme'").fetchone()
        finally:
            connection.close()
        value = json.loads(row[0]) if row else "dark"
        return value if value in {"dark", "light"} else "dark"
    except Exception:
        return "dark"


def _alpha(color: QColor, alpha: float) -> QColor:
    result = QColor(color)
    result.setAlphaF(max(0.0, min(1.0, alpha)))
    return result


def _smooth(edge0: float, edge1: float, x: float) -> float:
    if edge1 <= edge0:
        return 1.0 if x >= edge1 else 0.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3 - 2 * t)


def shield_path(box: QRectF) -> QPainterPath:
    """Shield outline in a 100x100 design space scaled into ``box``."""
    w, h = box.width() / 100.0, box.height() / 100.0

    def pt(x: float, y: float) -> QPointF:
        return QPointF(box.x() + x * w, box.y() + y * h)

    path = QPainterPath(pt(50, 9))
    path.lineTo(pt(83, 21))
    path.cubicTo(pt(85.5, 22), pt(86, 23), pt(86, 26))
    path.lineTo(pt(86, 50))
    path.cubicTo(pt(86, 71), pt(70, 86), pt(50, 94))
    path.cubicTo(pt(30, 86), pt(14, 71), pt(14, 50))
    path.lineTo(pt(14, 26))
    path.cubicTo(pt(14, 23), pt(14.5, 22), pt(17, 21))
    path.closeSubpath()
    return path


def check_path(box: QRectF) -> QPainterPath:
    w, h = box.width() / 100.0, box.height() / 100.0
    path = QPainterPath(QPointF(box.x() + 33 * w, box.y() + 51 * h))
    path.lineTo(QPointF(box.x() + 45.5 * w, box.y() + 63 * h))
    path.lineTo(QPointF(box.x() + 68 * w, box.y() + 38 * h))
    return path


def _draw_progress(painter: QPainter, path: QPainterPath, progress: float, color: QColor, width: float, glow: float) -> None:
    """Stroke ``path`` from its start to ``progress`` (0..1), with a soft glow underneath."""
    if progress <= 0.001:
        return
    length = max(1.0, path.length())
    for extra, alpha in ((width * 3.2, 0.10 * glow), (width * 2.0, 0.18 * glow)):
        if alpha > 0.005:
            pen = QPen(_alpha(color, alpha), extra, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            _stroke_partial(painter, path, pen, length, progress, extra)
    pen = QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    _stroke_partial(painter, path, pen, length, progress, width)


def _stroke_partial(painter: QPainter, path: QPainterPath, pen: QPen, length: float, progress: float, width: float) -> None:
    if progress >= 0.999:
        painter.setPen(pen)
        painter.drawPath(path)
        return
    visible = length * progress
    pen.setDashPattern([visible / width, (length * 2) / width])
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawPath(path)


class LogoMark(QWidget):
    """The static logo (shield + check)."""

    def __init__(self, parent: QWidget | None = None, size: int = 64) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def retint(self) -> None:
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        box = QRectF(0, 0, self.width(), self.height())
        width = self.width() * 0.07
        _draw_progress(painter, shield_path(box), 1.0, logo_color(), width, 0.6)
        _draw_progress(painter, check_path(box), 1.0, logo_color(), width, 0.6)
        painter.end()


class LogoReveal(QWidget):
    """Launch animation. ``finished_reveal`` is reached after DURATION seconds, then the logo
    stays on screen with a gentle breathing glow."""

    DURATION = 2.6

    def __init__(self, parent: QWidget | None = None, size: int = 210) -> None:
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

    def seconds(self) -> float:
        return self._clock.elapsed() / 1000.0

    def progress(self) -> float:
        return min(1.0, self.seconds() / self.DURATION)

    def is_done(self) -> bool:
        return self.progress() >= 1.0

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def retint(self) -> None:
        self.update()

    # -- drawing -----------------------------------------------------------
    def _paint_tile(self, painter: QPainter, centre: QPointF, side: float, strength: float, t: float) -> None:
        """Glass tile with drifting liquid colour, clipped to a rounded square."""
        if strength <= 0.003:
            return
        palette = get_palette()
        light = palette.name == "light"
        scale = 0.86 + 0.14 * _smooth(0.0, 0.25, self.progress()) - 0.10 * (1.0 - strength)
        half = side * scale / 2.0
        rect = QRectF(centre.x() - half, centre.y() - half, half * 2, half * 2)
        radius = half * 0.52
        clip = QPainterPath()
        clip.addRoundedRect(rect, radius, radius)

        painter.save()
        painter.setOpacity(strength)
        base = QLinearGradient(rect.topLeft(), rect.bottomRight())
        base.setColorAt(0.0, QColor(255, 255, 255, 235 if light else 38))
        base.setColorAt(1.0, QColor(235, 240, 228, 225) if light else QColor(10, 14, 11, 235))
        painter.fillPath(clip, QBrush(base))

        painter.setClipPath(clip)
        blobs = (
            (QColor(LOGO_LIME_DARK), 0.0, 0.34, 1.00),
            (QColor("#FF8A3D"), 2.1, 0.30, 0.80),
            (QColor("#35D6FF"), 4.0, 0.28, 0.85),
            (QColor("#A6FF8F"), 5.4, 0.26, 0.90),
        )
        for index, (color, phase, reach, speed) in enumerate(blobs):
            angle = t * speed * 1.6 + phase
            bx = centre.x() + math.cos(angle) * half * reach * 1.7
            by = centre.y() + math.sin(angle * 0.9 + index) * half * reach * 1.7
            blob_radius = half * (0.95 + 0.12 * math.sin(t * 2 + index))
            gradient = QRadialGradient(QPointF(bx, by), blob_radius)
            gradient.setColorAt(0.0, _alpha(color, 0.78 if not light else 0.62))
            gradient.setColorAt(0.55, _alpha(color, 0.22))
            gradient.setColorAt(1.0, _alpha(color, 0.0))
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver if light else QPainter.CompositionMode.CompositionMode_Plus
            )
            painter.fillRect(rect, QBrush(gradient))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # Glass sheen: bright top edge fading down.
        sheen = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + half * 1.1))
        sheen.setColorAt(0.0, QColor(255, 255, 255, 120 if not light else 170))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), half * 1.1), QBrush(sheen))
        painter.setClipping(False)

        rim = QLinearGradient(rect.topLeft(), rect.bottomRight())
        rim.setColorAt(0.0, QColor(255, 255, 255, 210 if not light else 255))
        rim.setColorAt(0.5, QColor(255, 255, 255, 40))
        rim.setColorAt(1.0, QColor(255, 255, 255, 120 if not light else 160))
        painter.setPen(QPen(QBrush(rim), max(1.0, side * 0.012)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)
        painter.restore()

    def paintEvent(self, event) -> None:
        del event
        t = self.seconds()
        p = self.progress()
        size = float(min(self.width(), self.height()))
        centre = QPointF(self.width() / 2.0, self.height() / 2.0)

        tile_strength = _smooth(0.0, 0.18, p) * (1.0 - _smooth(0.58, 0.86, p))
        shield_progress = _smooth(0.30, 0.78, p)
        check_progress = _smooth(0.66, 0.92, p)
        settle = _smooth(0.80, 1.0, p)
        breathe = 0.5 + 0.5 * math.sin(t * 2.2)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        color = logo_color()
        # Ambient glow behind the mark that grows as the logo forms.
        glow_strength = (0.10 + 0.10 * breathe) * (0.3 + 0.7 * settle) * (0.4 + 0.6 * shield_progress)
        glow = QRadialGradient(centre, size * 0.5)
        glow.setColorAt(0.0, _alpha(color, glow_strength * (1.0 if get_palette().name == "dark" else 0.8)))
        glow.setColorAt(1.0, _alpha(color, 0.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(centre, size * 0.5, size * 0.5)

        self._paint_tile(painter, centre, size * 0.74, tile_strength, t)

        box = QRectF(centre.x() - size * 0.36, centre.y() - size * 0.36, size * 0.72, size * 0.72)
        width = size * 0.052
        glow_level = 0.5 + 0.5 * settle * (0.6 + 0.4 * breathe)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        _draw_progress(painter, shield_path(box), shield_progress, color, width, glow_level)
        _draw_progress(painter, check_path(box), check_progress, color, width, glow_level)
        painter.end()
