"""CampusGuard logo: an open "C" with a lens dot, drawn in code so it is sharp at any size.

LogoMark   - the static glyph (C + lens dot) for the app chrome.
LogoReveal - the launch animation: a glass disc melts into a glass tile while the C draws in
             and the lens dot appears. The finished tile stays.
Colours follow the active theme (dark / light).
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

LOGO_LIME_DARK = "#ECEEF1"          # fog-white C on graphite
LOGO_LIME_LIGHT = "#1B1D22"          # graphite C on the light grey
LENS_DARK = "#9DB6E8"                # lens dot, dark theme
LENS_LIGHT = "#4F6FA8"               # lens dot, light theme


def lens_color() -> QColor:
    return QColor(LENS_LIGHT if get_palette().name == "light" else LENS_DARK)


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


def c_path(box: QRectF) -> QPainterPath:
    """The open C: a 276 degree arc centred in ``box`` (radius 27% of the side)."""
    side = min(box.width(), box.height())
    radius = side * 0.27
    rect = QRectF(box.center().x() - radius, box.center().y() - radius, radius * 2, radius * 2)
    path = QPainterPath()
    path.arcMoveTo(rect, 42)
    path.arcTo(rect, 42, 276)
    return path


def draw_lens(painter: QPainter, box: QRectF, opacity: float = 1.0) -> None:
    side = min(box.width(), box.height())
    painter.save()
    painter.setOpacity(painter.opacity() * opacity)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(lens_color())
    centre = QPointF(box.center().x() + side * 0.154, box.center().y())
    r = side * 0.0625
    painter.drawEllipse(centre, r, r)
    painter.restore()


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
        # glyph only: the C fills the widget (tile side = widget side / 0.80)
        tile = QRectF(box)
        tile.setSize(box.size() / 0.80)
        tile.moveCenter(box.center())
        width = tile.width() * 0.135
        _draw_progress(painter, c_path(tile), 1.0, (QColor(self._tint) if self._tint else ui_logo_color()), width, 0.0)
        draw_lens(painter, tile)
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
            body.setColorAt(1.0, QColor(204, 205, 208))
        else:
            body.setColorAt(0.0, QColor(66, 70, 76))
            body.setColorAt(1.0, QColor(9, 11, 12))
        painter.fillPath(path, QBrush(body))
        rim = QLinearGradient(rect.topLeft(), rect.bottomRight())
        rim.setColorAt(0.0, QColor(255, 255, 255, 235 if not light else 200))
        rim.setColorAt(0.5, QColor(190, 194, 202, 70))
        rim.setColorAt(1.0, QColor(150, 156, 166, 210 if not light else 150))
        painter.setPen(QPen(QBrush(rim), max(1.2, rect.width() * 0.016)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.restore()

    def _paint_liquid_edge(self, painter: QPainter, path: QPainterPath, centre: QPointF, rect: QRectF, strength: float, t: float) -> None:
        """Silver light gathering and drifting along the tile's edge."""
        if strength <= 0.004:
            return
        light = get_palette().name == "light"
        painter.save()
        painter.setClipPath(path)
        stops = (
            (0.00, "#F4F5F7"), (0.08, "#F4F5F7"), (0.17, "#7C828C"), (0.25, "#C9CDD4"),
            (0.33, "#F4F5F7"), (0.42, "#8A8F99"), (0.50, "#F4F5F7"), (0.58, "#F4F5F7"),
            (0.67, "#7C828C"), (0.75, "#C9CDD4"), (0.83, "#F4F5F7"), (0.92, "#8A8F99"),
        )
        for width_factor, alpha in ((0.24, 0.14), (0.15, 0.30), (0.08, 0.58)):
            gradient = QConicalGradient(centre, -(t * 55.0) % 360.0)
            for position, hex_color in stops:
                gradient.setColorAt(position, _alpha(QColor(hex_color), alpha * strength * (0.7 if light else 1.0)))
            gradient.setColorAt(1.0, _alpha(QColor(stops[0][1]), alpha * strength * (0.7 if light else 1.0)))
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
        c_p = _smooth(0.95, 1.85, t)
        dot_p = _smooth(1.65, 2.2, t)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        color = logo_color()
        pop = 0.82 + 0.18 * disc_in
        side = size * (0.52 + 0.26 * morph) * pop
        path = self._tile_path(centre, side, 1.0 - morph)
        rect = QRectF(centre.x() - side / 2.0, centre.y() - side / 2.0, side, side)
        if disc_in > 0.003:
            self._paint_glass(painter, path, rect, disc_in)   # the tile stays: it is part of the logo
            self._paint_liquid_edge(painter, path, centre, rect, edge, t)

        width = side * 0.135
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setOpacity(disc_in)
        _draw_progress(painter, c_path(rect), c_p, color, width, 0.0)
        draw_lens(painter, rect, dot_p)
        painter.end()
