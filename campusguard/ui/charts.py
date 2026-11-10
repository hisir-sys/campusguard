"""Statistics charts drawn with QPainter, in the app's palette.

TrendChart   - the main chart: a smooth area line with a hover crosshair and tooltip.
RankBars     - a ranked list with thin bars (the leader gets the accent, the rest stay neutral).
SeverityBar  - one stacked bar with a legend, for how severe the incidents were.
Nothing here touches the database: pages pass plain numbers in.
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from campusguard.ui.theme import get_palette, qcolor


def _smooth_path(points: list[QPointF]) -> QPainterPath:
    """Catmull-Rom spline through the points, as cubic beziers (no overshoot below the baseline)."""
    path = QPainterPath()
    if not points:
        return path
    path.moveTo(points[0])
    for i in range(len(points) - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else p2
        c1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6.0, p1.y() + (p2.y() - p0.y()) / 6.0)
        c2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6.0, p2.y() - (p3.y() - p1.y()) / 6.0)
        path.cubicTo(c1, c2, p2)
    return path


def _nice_max(value: float) -> int:
    if value <= 4:
        return 4
    for step in (5, 8, 10, 12, 16, 20, 25, 40, 50, 80, 100, 200, 500, 1000):
        if value <= step:
            return step
    return int(value) + 1


class TrendChart(QWidget):
    """Incidents over time. ``set_data(labels, values)`` with one value per bucket (day)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels: list[str] = []
        self._values: list[int] = []
        self._hover = -1
        self._progress = 1.0
        self.setMouseTracking(True)
        self.setMinimumHeight(176)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._reveal = QVariantAnimation(self)
        self._reveal.setDuration(700)
        self._reveal.setStartValue(0.0)
        self._reveal.setEndValue(1.0)
        self._reveal.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._reveal.valueChanged.connect(self._on_reveal)

    def _on_reveal(self, value) -> None:
        self._progress = float(value)
        self.update()

    def retint(self) -> None:
        self.update()

    def set_data(self, labels: list[str], values: list[int]) -> None:
        changed = (labels, values) != (self._labels, self._values)
        self._labels, self._values = list(labels), [int(v) for v in values]
        self._hover = -1
        if changed:
            self._reveal.stop()
            self._reveal.start()
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(520, 200)

    # -- geometry ------------------------------------------------------------
    def _plot(self) -> QRectF:
        return QRectF(34, 10, max(10.0, self.width() - 34 - 12), max(10.0, self.height() - 10 - 24))

    def _points(self, plot: QRectF, top: int) -> list[QPointF]:
        n = len(self._values)
        if n == 0:
            return []
        step = plot.width() / (n - 1) if n > 1 else 0.0
        return [
            QPointF(plot.left() + i * step, plot.bottom() - (v / top) * plot.height())
            for i, v in enumerate(self._values)
        ]

    # -- interaction ---------------------------------------------------------
    def mouseMoveEvent(self, event) -> None:
        plot = self._plot()
        n = len(self._values)
        if n:
            step = plot.width() / (n - 1) if n > 1 else 1.0
            index = int(round((event.position().x() - plot.left()) / step)) if n > 1 else 0
            index = max(0, min(n - 1, index))
        else:
            index = -1
        if index != self._hover:
            self._hover = index
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    # -- painting ------------------------------------------------------------
    def paintEvent(self, event) -> None:
        del event
        pal = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        plot = self._plot()
        top = _nice_max(max(self._values) if self._values else 0)
        accent = QColor(pal.lens)
        grid = qcolor(pal.text, 22 if pal.name == "dark" else 30)
        muted = QColor(pal.muted)
        font = QFont(self.font())
        font.setPointSizeF(8.0)
        painter.setFont(font)

        # grid + y labels
        for i in range(5):
            frac = i / 4.0
            y = plot.bottom() - frac * plot.height()
            painter.setPen(QPen(grid, 1, Qt.PenStyle.DotLine if i else Qt.PenStyle.SolidLine))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(muted)
            painter.drawText(QRectF(0, y - 8, plot.left() - 8, 16), int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), str(round(top * frac)))

        n = len(self._values)
        if n == 0:
            painter.setPen(muted)
            painter.drawText(plot, int(Qt.AlignmentFlag.AlignCenter), "No data yet")
            painter.end()
            return

        # x labels: about six, always including the first and last
        painter.setPen(muted)
        stride = max(1, round(n / 6))
        step = plot.width() / (n - 1) if n > 1 else 0.0
        for i, label in enumerate(self._labels):
            if i % stride == 0 or i == n - 1:
                if i == n - 1 or (n - 1 - i) >= stride * 0.6:
                    x = plot.left() + i * step
                    painter.drawText(QRectF(x - 28, plot.bottom() + 6, 56, 16), int(Qt.AlignmentFlag.AlignCenter), label)

        points = self._points(plot, top)
        painter.save()
        painter.setClipRect(QRectF(0, 0, plot.left() + plot.width() * self._progress + 14, self.height()))
        line = _smooth_path(points)
        area = QPainterPath(line)
        area.lineTo(QPointF(points[-1].x(), plot.bottom()))
        area.lineTo(QPointF(points[0].x(), plot.bottom()))
        area.closeSubpath()
        fill = QLinearGradient(0, plot.top(), 0, plot.bottom())
        fill.setColorAt(0.0, qcolor(pal.lens, 96 if pal.name == "dark" else 80))
        fill.setColorAt(1.0, qcolor(pal.lens, 0))
        painter.fillPath(area, fill)
        for width, alpha in ((7.0, 22), (4.0, 40)):  # soft glow under the line
            painter.setPen(QPen(qcolor(pal.lens, alpha), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(line)
        painter.setPen(QPen(accent, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(line)
        painter.restore()

        # the peak, always marked
        peak = max(range(n), key=lambda i: self._values[i])
        if self._values[peak] > 0 and self._progress > 0.98:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accent)
            painter.drawEllipse(points[peak], 3.4, 3.4)

        # hover: crosshair, point, tooltip
        if 0 <= self._hover < n:
            p = points[self._hover]
            painter.setPen(QPen(qcolor(pal.text, 60), 1))
            painter.drawLine(QPointF(p.x(), plot.top()), QPointF(p.x(), plot.bottom()))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(pal.lens, 60))
            painter.drawEllipse(p, 8, 8)
            painter.setBrush(accent)
            painter.drawEllipse(p, 4.2, 4.2)
            painter.setBrush(QColor(pal.glass))
            painter.drawEllipse(p, 1.8, 1.8)
            self._tooltip(painter, p, plot, pal)
        painter.end()

    def _tooltip(self, painter: QPainter, p: QPointF, plot: QRectF, pal) -> None:
        value = self._values[self._hover]
        text = f"{self._labels[self._hover]}  ·  {value} incident{'' if value == 1 else 's'}"
        font = QFont(self.font())
        font.setPointSizeF(8.5)
        font.setWeight(QFont.Weight.Medium)
        metrics = QFontMetricsF(font)
        w, h = metrics.horizontalAdvance(text) + 20, 26.0
        x = min(max(p.x() - w / 2, plot.left()), plot.right() - w)
        y = p.y() - h - 12
        if y < 0:
            y = p.y() + 12
        rect = QRectF(x, y, w, h)
        painter.setPen(QPen(qcolor(pal.line, 60 if pal.name == "dark" else 90), 1))
        painter.setBrush(qcolor(pal.glass, 235))
        painter.drawRoundedRect(rect, 9, 9)
        painter.setFont(font)
        painter.setPen(QColor(pal.text))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)


class RankBars(QWidget):
    """A ranked list: name, thin bar, count. Only the leader carries the accent."""

    ROW = 32

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[tuple[str, int]] = []
        self._hover = -1
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._grow = QVariantAnimation(self)
        self._grow.setDuration(600)
        self._grow.setStartValue(0.0)
        self._grow.setEndValue(1.0)
        self._grow.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._grow.valueChanged.connect(lambda v: self._set_progress(float(v)))
        self._progress = 1.0

    def _set_progress(self, value: float) -> None:
        self._progress = value
        self.update()

    def retint(self) -> None:
        self.update()

    def set_items(self, items: list[tuple[str, int]], limit: int = 5) -> None:
        items = [(name, int(count)) for name, count in items[:limit]]
        changed = items != self._items
        self._items = items
        self.setMinimumHeight(max(1, len(items)) * self.ROW)
        if changed:
            self._grow.stop()
            self._grow.start()
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(260, max(1, len(self._items)) * self.ROW)

    def mouseMoveEvent(self, event) -> None:
        index = int(event.position().y() // self.ROW)
        index = index if 0 <= index < len(self._items) else -1
        if index != self._hover:
            self._hover = index
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        del event
        pal = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        if not self._items:
            painter.setPen(QColor(pal.muted))
            painter.drawText(QRectF(0, 0, self.width(), self.ROW), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), "No incidents recorded")
            painter.end()
            return
        biggest = max(count for _name, count in self._items) or 1
        count_w = 34.0
        for i, (name, count) in enumerate(self._items):
            y = i * self.ROW
            if i == self._hover:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(qcolor(pal.text, 12))
                painter.drawRoundedRect(QRectF(-6, y + 1, self.width() + 12, self.ROW - 2), 8, 8)
            painter.setPen(QColor(pal.text if i == 0 or i == self._hover else pal.text_dim))
            painter.drawText(QRectF(0, y, self.width() - count_w - 8, 18), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self._elide(name, self.width() - count_w - 8))
            painter.setPen(QColor(pal.text if i == 0 else pal.muted))
            painter.drawText(QRectF(self.width() - count_w, y, count_w, 18), int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), str(count))
            track = QRectF(0, y + 21, self.width(), 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(pal.text, 14))
            painter.drawRoundedRect(track, 2, 2)
            fill = QRectF(0, y + 21, max(4.0, self.width() * (count / biggest) * self._progress), 4)
            if i == 0:
                gradient = QLinearGradient(fill.left(), 0, fill.right(), 0)
                gradient.setColorAt(0.0, qcolor(pal.lens, 150))
                gradient.setColorAt(1.0, QColor(pal.lens))
                painter.setBrush(gradient)
            else:
                painter.setBrush(qcolor(pal.text, 70 if i != self._hover else 110))
            painter.drawRoundedRect(fill, 2, 2)
        painter.end()

    def _elide(self, text: str, width: float) -> str:
        return QFontMetricsF(self.font()).elidedText(text, Qt.TextElideMode.ElideRight, max(10.0, width))


class SeverityBar(QWidget):
    """One stacked bar for the share of each severity, with a legend underneath."""

    ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._counts: dict[str, int] = {}
        self.setMinimumHeight(58)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(58)

    def retint(self) -> None:
        self.update()

    def set_counts(self, counts: dict[str, int]) -> None:
        self._counts = {k.upper(): int(v) for k, v in counts.items() if k}
        self.update()

    def _colors(self) -> dict[str, QColor]:
        pal = get_palette()
        return {
            "CRITICAL": QColor(pal.bad),
            "HIGH": QColor(pal.warn),
            "MEDIUM": QColor(pal.lens),
            "LOW": qcolor(pal.text, 90),
        }

    def paintEvent(self, event) -> None:
        del event
        pal = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        colors = self._colors()
        keys = [k for k in self.ORDER if self._counts.get(k)] + [k for k in self._counts if k not in self.ORDER and self._counts[k]]
        total = sum(self._counts.get(k, 0) for k in keys)
        bar = QRectF(0, 0, self.width(), 10)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(pal.text, 14))
        painter.drawRoundedRect(bar, 5, 5)
        if total:
            painter.save()
            clip = QPainterPath()
            clip.addRoundedRect(bar, 5, 5)
            painter.setClipPath(clip)
            x = 0.0
            gap = 2.0
            for k in keys:
                width = self.width() * self._counts[k] / total
                painter.setBrush(colors.get(k, qcolor(pal.text, 90)))
                painter.drawRect(QRectF(x, 0, max(0.0, width - (gap if k != keys[-1] else 0)), 10))
                x += width
            painter.restore()
        # legend
        font = QFont(self.font())
        font.setPointSizeF(8.5)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        x = 0.0
        shown = keys or list(self.ORDER)
        for k in shown:
            label = f"{k.capitalize()}  {self._counts.get(k, 0)}"
            width = metrics.horizontalAdvance(label) + 22
            if x + width > self.width() and x > 0:
                break
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colors.get(k, qcolor(pal.text, 90)))
            painter.drawEllipse(QPointF(x + 4, 31), 3.5, 3.5)
            painter.setPen(QColor(pal.text_dim))
            painter.drawText(QRectF(x + 14, 22, width, 18), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), label)
            x += width + 6
        painter.end()
