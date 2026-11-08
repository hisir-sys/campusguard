"""CampusGuard's current shield-and-check mark, drawn sharply at any size.

LogoMark is the static neon-green brand mark. LogoReveal animates a restrained
frosted-glass disc and silver/lime edge before settling on that same mark.
"""
from __future__ import annotations

import math
import sqlite3
import json
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush, QColor, QConicalGradient, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from campusguard.ui.theme import get_palette

LOGO_LIME_DARK = "#C8FF52"
LOGO_LIME_LIGHT = "#6FA60F"          # darker lime so the mark stays readable on near-white


def logo_color() -> QColor:
    return QColor(LOGO_LIME_LIGHT if get_palette().name == "light" else LOGO_LIME_DARK)


def ui_logo_color() -> QColor:
    """Neutral (palette) colour for the logo inside the app chrome."""
    return QColor(get_palette().ink)


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

    def __init__(self, parent: QWidget | None = None, size: int = 64, tint: str | None = None) -> None:
        super().__init__(parent)
        self._tint = tint
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
        _draw_progress(painter, shield_path(box), 1.0, (QColor(self._tint) if self._tint else ui_logo_color()), width, 0.6)
        _draw_progress(painter, check_path(box), 1.0, (QColor(self._tint) if self._tint else ui_logo_color()), width, 0.6)
        painter.end()


class LogoReveal(QWidget):
    """Launch animation, following the brand film:

    1. a glass disc with a lime check mark,
    2. the disc melts into a rounded glass tile whose edge glows with liquid colour
       while the shield draws itself around the check,
    3. the colour drains away, the tile fades and the plain lime shield + check stays.

    After DURATION seconds the animation is finished and the logo is simply held
    (no glow, no breathing)."""

    DURATION = 3.2

    def __init__(self, parent: QWidget | None = None, size: int = 210) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        self.update()
        if self.is_done():
            self._timer.stop()  # the logo is held still: no need to keep repainting

    def seconds(self) -> float:
        return self._clock.elapsed() / 1000.0

    def progress(self) -> float:
        return min(1.0, self.seconds() / self.DURATION)

    def is_done(self) -> bool:
        return self.progress() >= 1.0

    def start(self) -> None:
        if not self._timer.isActive():
            self._clock.restart()  # the film starts when the window appears
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def retint(self) -> None:
        self.update()

    # -- drawing -----------------------------------------------------------
    @staticmethod
    def _tile_path(centre: QPointF, side: float, roundness: float) -> QPainterPath:
        """Rounded square that is a perfect circle at roundness 1 and a soft tile at 0."""
        radius = side / 2.0 * (0.52 + 0.48 * roundness)
        rect = QRectF(centre.x() - side / 2.0, centre.y() - side / 2.0, side, side)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path

    def _paint_glass(self, painter: QPainter, path: QPainterPath, rect: QRectF, strength: float) -> None:
        light = get_palette().name == "light"
        painter.save()
        painter.setOpacity(strength)
        body = QRadialGradient(QPointF(rect.center().x(), rect.top() + rect.height() * 0.22), rect.width() * 0.85)
        if light:
            body.setColorAt(0.0, QColor(255, 255, 255))
            body.setColorAt(1.0, QColor(226, 232, 220))
        else:
            body.setColorAt(0.0, QColor(66, 70, 76))
            body.setColorAt(1.0, QColor(9, 11, 12))
        painter.fillPath(path, QBrush(body))
        rim = QLinearGradient(rect.topLeft(), rect.bottomRight())
        rim.setColorAt(0.0, QColor(255, 255, 255, 235 if not light else 200))
        rim.setColorAt(0.5, QColor(190, 205, 230, 70))
        rim.setColorAt(1.0, QColor(200, 255, 82, 210 if not light else 150))
        painter.setPen(QPen(QBrush(rim), max(1.2, rect.width() * 0.016)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.restore()

    def _paint_liquid_edge(self, painter: QPainter, path: QPainterPath, centre: QPointF, rect: QRectF, strength: float, t: float) -> None:
        """A restrained silver-to-brand-lime highlight around the glass tile."""
        if strength <= 0.004:
            return
        light = get_palette().name == "light"
        painter.save()
        painter.setClipPath(path)
        stops = (
            (0.00, "#FFFFFF"), (0.18, "#D7DBDA"), (0.34, "#C8FF52"),
            (0.66, "#C8FF52"), (0.84, "#D7DBDA"), (0.98, "#FFFFFF"),
        )
        for width_factor, alpha in ((0.20, 0.10), (0.11, 0.24), (0.055, 0.48)):
            gradient = QConicalGradient(centre, -(t * 34.0) % 360.0)
            for position, hex_color in stops:
                gradient.setColorAt(position, _alpha(QColor(hex_color), alpha * strength * (0.72 if light else 1.0)))
            gradient.setColorAt(1.0, _alpha(QColor(stops[0][1]), alpha * strength * (0.72 if light else 1.0)))
            painter.setPen(QPen(QBrush(gradient), rect.width() * width_factor, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        painter.restore()

    def paintEvent(self, event) -> None:
        del event
        t = self.seconds()
        size = float(min(self.width(), self.height()))
        centre = QPointF(self.width() / 2.0, self.height() / 2.0)

        disc_in = _smooth(0.0, 0.40, t)
        morph = _smooth(0.65, 1.55, t)                       # disc -> rounded tile
        edge = _smooth(0.70, 1.15, t) * (1.0 - _smooth(1.85, 2.65, t))
        shield_p = _smooth(0.95, 1.85, t)
        tile_fade = 1.0 - _smooth(2.15, 2.85, t)
        shrink = _smooth(2.15, 2.85, t)                       # tile gone: shield settles smaller

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        color = logo_color()
        pop = 0.82 + 0.18 * disc_in
        side = size * (0.52 + 0.26 * morph) * pop
        path = self._tile_path(centre, side, 1.0 - morph)
        rect = QRectF(centre.x() - side / 2.0, centre.y() - side / 2.0, side, side)
        glass_strength = disc_in * tile_fade
        if glass_strength > 0.003:
            self._paint_glass(painter, path, rect, glass_strength)
            self._paint_liquid_edge(painter, path, centre, rect, edge * tile_fade, t)

        scale = 1.0 - 0.20 * shrink
        box_side = size * 0.62 * scale * pop
        box = QRectF(centre.x() - box_side / 2.0, centre.y() - box_side / 2.0, box_side, box_side)
        check_side = size * (0.74 - 0.14 * morph) * scale * pop
        check_box = QRectF(centre.x() - check_side / 2.0, centre.y() - check_side / 2.0, check_side, check_side)
        width = size * (0.070 - 0.020 * _smooth(1.2, 2.3, t)) * scale
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setOpacity(disc_in)
        _draw_progress(painter, shield_path(box), shield_p, color, width, 0.0)
        _draw_progress(painter, check_path(check_box), 1.0, color, width, 0.0)
        painter.end()
