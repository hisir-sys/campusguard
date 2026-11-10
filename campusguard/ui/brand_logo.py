"""CampusGuard logo: three rounded pills and a dot, drawn in code so it is sharp at any size.

LogoMark   - the static mark for the app chrome.
LogoReveal - the launch animation: the pills slide in, the dot pops and ripples, the wordmark
             rises letter by letter, then the tagline and loading bar appear.
Colours follow the active theme (dark / light).
"""
from __future__ import annotations

import math
import sqlite3
import json
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from campusguard.ui.theme import get_palette

LOGO_LIME_DARK = "#FFFFFF"           # white mark on midnight
LOGO_LIME_LIGHT = "#0B0D12"          # midnight mark on paper
LENS_DARK = "#5CD6F5"                # accent, dark theme
LENS_LIGHT = "#0A7EA4"               # accent, light theme
SPLASH = {
    "dark": {"bg": "#0B0D12", "fg": "#FFFFFF", "mute": "#A3A9B8", "line": "#2A2E3A"},
    "light": {"bg": "#F4F4F2", "fg": "#0B0D12", "mute": "#5B6070", "line": "#D3D5DB"},
}


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


def _smooth(edge0: float, edge1: float, x: float) -> float:
    if edge1 <= edge0:
        return 1.0 if x >= edge1 else 0.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3 - 2 * t)


def bezier(x1: float, y1: float, x2: float, y2: float):
    """CSS cubic-bezier easing as a function of progress 0..1."""

    def at(a: float, b: float, t: float) -> float:
        return 3 * a * (1 - t) ** 2 * t + 3 * b * (1 - t) * t ** 2 + t ** 3

    def ease(x: float) -> float:
        if x <= 0.0:
            return 0.0
        if x >= 1.0:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(24):
            mid = (lo + hi) / 2
            if at(x1, x2, mid) < x:
                lo = mid
            else:
                hi = mid
        return at(y1, y2, (lo + hi) / 2)

    return ease


# The mark lives in a 100 x 100 design space (as in the brand file); its bounds are 6..94.
MARK_BOUNDS = (6.0, 6.0, 88.0, 88.0)
PILLS = {
    "top": (20.0, 6.0, 74.0, 26.0),
    "bottom": (20.0, 68.0, 74.0, 26.0),
    "stem": (6.0, 38.0, 26.0, 24.0),
}
DOT = (80.0, 50.0, 9.0)


def _draw_pill(painter: QPainter, rect: tuple[float, float, float, float], color: QColor, dx=0.0, dy=0.0, scale=1.0, opacity=1.0) -> None:
    if opacity <= 0.002:
        return
    x, y, w, h = rect
    cx, cy = x + w / 2, y + h / 2
    painter.save()
    painter.setOpacity(painter.opacity() * opacity)
    painter.translate(cx + dx, cy + dy)
    painter.scale(scale, scale)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawRoundedRect(QRectF(-w / 2, -h / 2, w, h), 12, 12)
    painter.restore()


def draw_mark(painter: QPainter, box: QRectF, color: QColor, *, stem=1.0, top=1.0, bottom=1.0, dot=1.0, ring=None, dot_color: QColor | None = None) -> None:
    """Draw the mark scaled into ``box``. Each part takes its animation progress (0..1);
    ``ring`` is (scale, opacity) for the ripple around the dot."""
    bx, by, bw, bh = MARK_BOUNDS
    scale = min(box.width() / bw, box.height() / bh)
    painter.save()
    painter.translate(box.center().x() - (bx + bw / 2) * scale, box.center().y() - (by + bh / 2) * scale)
    painter.scale(scale, scale)
    ease = bezier(0.2, 0.8, 0.2, 1.0)
    e = ease(stem)
    _draw_pill(painter, PILLS["stem"], color, dx=-45 * (1 - e), scale=0.85 + 0.15 * e, opacity=e)
    e = ease(top)
    _draw_pill(painter, PILLS["top"], color, dx=35 * (1 - e), dy=-35 * (1 - e), scale=0.85 + 0.15 * e, opacity=e)
    e = ease(bottom)
    _draw_pill(painter, PILLS["bottom"], color, dx=35 * (1 - e), dy=35 * (1 - e), scale=0.85 + 0.15 * e, opacity=e)
    cx, cy, r = DOT
    if ring is not None and ring[1] > 0.002:
        painter.save()
        painter.setOpacity(painter.opacity() * ring[1])
        painter.setPen(QPen(color, 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rr = r * ring[0]
        painter.drawEllipse(QPointF(cx, cy), rr, rr)
        painter.restore()
    if dot > 0.002:
        # pop: 0 -> 1.4 (at 60%) -> 1
        scale_dot = dot / 0.6 * 1.4 if dot < 0.6 else 1.4 - 0.4 * (dot - 0.6) / 0.4
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot_color or color)
        painter.drawEllipse(QPointF(cx, cy), r * scale_dot, r * scale_dot)
        painter.restore()
    painter.restore()


class LogoMark(QWidget):
    """The static logo for the app chrome."""

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
        draw_mark(painter, QRectF(0, 0, self.width(), self.height()), QColor(self._tint) if self._tint else ui_logo_color())
        painter.end()


class LogoReveal(QWidget):
    """Launch animation, ported from the brand's startup film:

    stem, top and bottom pills slide in (0.2 / 0.4 / 0.6 s), the dot pops (1.1 s) and sends two
    ripples (1.6 s), the wordmark rises letter by letter (1.3 s), the tagline fades in (2.2 s)
    and a thin bar fills (0.5 s to 3.3 s). After DURATION it is simply held."""

    DURATION = 3.4
    WORDMARK = "CampusGuard"
    TAGLINE = "AI FIGHT DETECTION"

    def __init__(self, parent: QWidget | None = None, size: int = 120) -> None:
        super().__init__(parent)
        self._unit = size / 150.0           # everything is authored for a 150 px mark
        self._pad = size * 0.3
        self.setFixedSize(int(size * 3.2), int(size * 2.55 + self._pad))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._mark_size = size

    def _tick(self) -> None:
        self.update()
        if self.is_done():
            self._timer.stop()

    def seconds(self) -> float:
        return self._clock.elapsed() / 1000.0

    def progress(self) -> float:
        return min(1.0, self.seconds() / self.DURATION)

    def is_done(self) -> bool:
        return self.progress() >= 1.0

    def start(self) -> None:
        if not self._timer.isActive():
            self._clock.restart()
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def retint(self) -> None:
        self.update()

    @staticmethod
    def _phase(t: float, start: float, duration: float) -> float:
        return max(0.0, min(1.0, (t - start) / duration))

    def paintEvent(self, event) -> None:
        del event
        t = self.seconds()
        u = self._unit
        colors = SPLASH["light" if get_palette().name == "light" else "dark"]
        fg, mute, line = QColor(colors["fg"]), QColor(colors["mute"]), QColor(colors["line"])
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        w = float(self.width())

        # mark
        mark = self._mark_size
        mark_box = QRectF((w - mark) / 2.0, self._pad, mark, mark)
        ring = None
        rt = t - 1.6
        if rt >= 0.0:
            cycle = (rt % 1.3) / 1.3 if rt < 2.6 else None
            if cycle is not None:
                ease = bezier(0.0, 0.0, 0.58, 1.0)(cycle)
                ring = (1.0 + 3.0 * ease, 0.7 * (1.0 - ease))
        draw_mark(
            painter, mark_box, fg,
            stem=self._phase(t, 0.2, 0.8), top=self._phase(t, 0.4, 0.8), bottom=self._phase(t, 0.6, 0.8),
            dot=self._phase(t, 1.1, 0.6), ring=ring,
        )

        # wordmark, letters rise from below a clip line
        font = QFont("Outfit")
        font.setPixelSize(max(10, int(64 * u)))
        font.setWeight(QFont.Weight.DemiBold)
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100)
        font.setKerning(True)
        metrics = QFontMetricsF(font)
        text_w = metrics.horizontalAdvance(self.WORDMARK) - 0.04 * font.pixelSize() * len(self.WORDMARK)
        line_h = metrics.height() * 1.0
        top = self._pad + mark + 22 * u
        baseline = top + metrics.ascent()
        x = (w - text_w) / 2.0
        painter.save()
        painter.setClipRect(QRectF(0, top, w, line_h + 6 * u))
        painter.setFont(font)
        for i, ch in enumerate(self.WORDMARK):
            p = bezier(0.2, 0.8, 0.2, 1.0)(self._phase(t, 1.3 + i * 0.045, 0.6))
            advance = metrics.horizontalAdvance(ch)
            if p > 0.002:
                painter.setOpacity(p)
                painter.setPen(fg)
                painter.drawText(QPointF(x, baseline + (1 - p) * 0.7 * line_h), ch)
            x += advance - 0.04 * font.pixelSize()
        painter.restore()

        # tagline
        tag_p = self._phase(t, 2.2, 0.8)
        if tag_p > 0.002:
            tag_font = QFont("Outfit")
            tag_font.setPixelSize(max(8, int(13 * u * 1.0)))
            tag_font.setWeight(QFont.Weight.Medium)
            tag_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.32 * tag_font.pixelSize())
            painter.setFont(tag_font)
            painter.setOpacity(tag_p)
            painter.setPen(mute)
            tag_metrics = QFontMetricsF(tag_font)
            tw = tag_metrics.horizontalAdvance(self.TAGLINE)
            ty = top + line_h + 14 * u + tag_metrics.ascent()
            painter.drawText(QPointF((w - tw) / 2.0 + 0.16 * tag_font.pixelSize(), ty), self.TAGLINE)

        # loading bar
        bar_p = self._phase(t, 0.4, 0.4)
        if bar_p > 0.002:
            bar_w = 180 * u
            bar_y = top + line_h + 14 * u + 13 * u + 18 * u + 10 * u
            painter.setOpacity(bar_p)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(line)
            painter.drawRoundedRect(QRectF((w - bar_w) / 2.0, bar_y, bar_w, 2.0), 1, 1)
            fill = bezier(0.6, 0.0, 0.3, 1.0)(self._phase(t, 0.5, 2.8))
            painter.setBrush(fg)
            painter.drawRoundedRect(QRectF((w - bar_w) / 2.0, bar_y, bar_w * fill, 2.0), 1, 1)
        painter.end()
