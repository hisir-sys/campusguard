"""v3 building blocks: glass card with rim and cursor spotlight, pill controls, switch,
segmented tabs, meter, bar chart and the detection-engine orb. Everything reads the live
palette, so a theme change only needs ``update()``."""
from __future__ import annotations

import math

from PySide6.QtCore import (
    QEasingCurve, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget,
)

from campusguard.ui.theme import get_palette, qcolor

MONO = "JetBrains Mono"
DISPLAY = "Outfit"


def mono(point: float = 9, weight: int = 400) -> QFont:
    font = QFont(MONO, -1)
    font.setPointSizeF(point)
    font.setWeight(QFont.Weight(weight))
    return font


def is_dark() -> bool:
    return get_palette().name == "dark"


def hairline(alpha_dark: int = 24, alpha_light: int = 22) -> QColor:
    p = get_palette()
    return qcolor(p.line, alpha_dark if is_dark() else alpha_light)


class GlassCard(QFrame):
    """A card with the v3 rim highlight and a soft spotlight that follows the cursor."""

    def __init__(self, parent: QWidget | None = None, radius: int = 20, lift: bool = True) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self._radius = radius
        self._mouse = QPointF(-1000, -1000)
        self._glow = 0.0
        self._selected = False
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(380)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_glow)
        self._lift = lift

    def set_selected(self, value: bool) -> None:
        self._selected = value
        self.update()

    def _on_glow(self, value) -> None:
        self._glow = float(value)
        self.update()

    def enterEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._glow)
        self._anim.setEndValue(1.0)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._glow)
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event) -> None:
        self._mouse = event.position()
        if self._glow > 0:
            self.update()
        super().mouseMoveEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        dark = is_dark()
        if self._glow > 0.01:
            path = QPainterPath()
            path.addRoundedRect(rect, self._radius, self._radius)
            painter.save()
            painter.setClipPath(path)
            grad = QRadialGradient(self._mouse, 260)
            grad.setColorAt(0.0, QColor(255, 255, 255, int((36 if dark else 190) * self._glow)))
            grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(self.rect(), QBrush(grad))
            painter.restore()
        # rim: bright at top-left and bottom-right, transparent between
        rim = QLinearGradient(rect.topLeft(), rect.bottomRight())
        rim.setColorAt(0.0, QColor(255, 255, 255, 102 if dark else 255))
        rim.setColorAt(0.35, QColor(255, 255, 255, 0))
        rim.setColorAt(0.65, QColor(255, 255, 255, 0))
        rim.setColorAt(1.0, QColor(255, 255, 255, 26 if dark else 140))
        painter.setPen(QPen(QBrush(rim), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, self._radius, self._radius)
        if self._selected or self._glow > 0.4:
            p = get_palette()
            colour = qcolor(p.text, 255 if self._selected else int(120 * self._glow))
            painter.setPen(QPen(colour, 1.0))
            painter.drawRoundedRect(rect, self._radius, self._radius)
        painter.end()


class Segmented(QWidget):
    """Pill-shaped tabs, one selected (24h / 7d / 30d)."""

    changed = Signal(str)

    def __init__(self, options: list[str], current: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._options = list(options)
        self._current = current or (options[0] if options else "")
        self._rects: list[QRectF] = []
        self._hover = -1
        self._pos = float(self._index())
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(300)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._slide)

    def _index(self) -> int:
        return self._options.index(self._current) if self._current in self._options else 0

    def _slide(self, value) -> None:
        self._pos = float(value)
        self.update()

    def current(self) -> str:
        return self._current

    def set_current(self, value: str, emit: bool = False) -> None:
        if value not in self._options or value == self._current:
            return
        self._current = value
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(float(self._index()))
        self._anim.start()
        if emit:
            self.changed.emit(value)

    def _cell(self) -> int:
        metrics = self.fontMetrics()
        return max((metrics.horizontalAdvance(o) for o in self._options), default=30) + 26

    def sizeHint(self) -> QSize:
        return QSize(self._cell() * len(self._options) + 8, 32)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def mouseMoveEvent(self, event) -> None:
        self._hover = self._hit(event.position())
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = -1
        self.update()

    def _hit(self, point) -> int:
        cell = self._cell()
        index = int((point.x() - 4) // cell)
        return index if 0 <= index < len(self._options) else -1

    def mousePressEvent(self, event) -> None:
        index = self._hit(event.position())
        if index >= 0:
            self.set_current(self._options[index], emit=True)

    def paintEvent(self, event) -> None:
        p = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outer = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(hairline(), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(outer, outer.height() / 2, outer.height() / 2)
        cell = self._cell()
        pill = QRectF(4 + self._pos * cell, 4, cell, self.height() - 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(p.accent))
        painter.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
        font = QFont(self.font())
        font.setPointSizeF(9.0)
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        for i, label in enumerate(self._options):
            rect = QRectF(4 + i * cell, 4, cell, self.height() - 8)
            overlap = max(0.0, 1.0 - abs(self._pos - i))
            on = QColor(p.on_accent if hasattr(p, "on_accent") else ("#0A0A0B" if is_dark() else "#FFFFFF"))
            off = QColor(p.text if i == self._hover else p.muted)
            mix = QColor(
                int(off.red() + (on.red() - off.red()) * overlap),
                int(off.green() + (on.green() - off.green()) * overlap),
                int(off.blue() + (on.blue() - off.blue()) * overlap),
            )
            painter.setPen(mix)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.end()


class Switch(QAbstractButton):
    """40x24 toggle with a springy knob."""

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(40, 24)
        self._t = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(380)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._anim.valueChanged.connect(self._tick)
        self.toggled.connect(self._start)

    def _tick(self, value) -> None:
        self._t = float(value)
        self.update()

    def _start(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._t)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, value: bool) -> None:  # noqa: N802 - Qt naming
        super().setChecked(value)
        if not self._anim.state() == QVariantAnimation.State.Running:
            self._t = 1.0 if value else 0.0
            self.update()

    def paintEvent(self, event) -> None:
        p = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(self.rect())
        t = max(0.0, min(1.0, self._t))
        off = hairline(30, 26)
        on = QColor(p.text)
        colour = QColor(
            int(off.red() + (on.red() - off.red()) * t),
            int(off.green() + (on.green() - off.green()) * t),
            int(off.blue() + (on.blue() - off.blue()) * t),
            int(off.alpha() + (255 - off.alpha()) * t),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawRoundedRect(track, 12, 12)
        knob_x = 3 + 16 * self._t
        knob = QColor(p.muted if t < 0.5 else p.bg0)
        painter.setBrush(knob)
        painter.drawEllipse(QRectF(knob_x, 3, 18, 18))
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(p.text), 2))
            painter.drawRoundedRect(track.adjusted(-2, -2, 2, 2), 14, 14)
        painter.end()


class Meter(QWidget):
    """Thin confidence bar (64 x 4)."""

    def __init__(self, value: float = 0.0, width: int = 64, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = max(0.0, min(1.0, value))
        self.setFixedSize(width, 6)

    def set_value(self, value: float) -> None:
        self._value = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = 4
        y = (self.height() - h) / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(hairline(30, 26))
        painter.drawRoundedRect(QRectF(0, y, self.width(), h), 2, 2)
        painter.setBrush(QColor(get_palette().text))
        painter.drawRoundedRect(QRectF(0, y, self.width() * self._value, h), 2, 2)
        painter.end()


class Dot(QWidget):
    """Status dot: filled = online, hollow = offline, coral = alert."""

    def __init__(self, state: str = "on", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self.setFixedSize(10, 10)

    def set_state(self, state: str) -> None:
        self._state = state
        self.update()

    def paintEvent(self, event) -> None:
        p = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 1, 8, 8)
        if self._state == "off":
            painter.setPen(QPen(QColor(p.muted), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(p.bad if self._state == "alert" else p.text))
        painter.drawEllipse(rect)
        painter.end()


def make_pill(text: str, tone: str = "") -> QLabel:
    """A small rounded label. tone: '' neutral, 'new' coral, 'up' filled neutral."""
    label = QLabel(text)
    label.setProperty("v3pill", tone or "plain")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def mono_label(text: str, muted: bool = True, point: float = 9.0) -> QLabel:
    label = QLabel(text)
    label.setFont(mono(point))
    if muted:
        label.setProperty("muted", True)
    return label


class BarChart(QWidget):
    """Incidents over time: bars with value labels, the latest bar highlighted, grid lines."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: list[tuple[str, int]] = []
        self._hover = -1
        self._progress = 1.0
        self.setMouseTracking(True)
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(800)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._tick)

    def _tick(self, value) -> None:
        self._progress = float(value)
        self.update()

    def set_data(self, data: list[tuple[str, int]], animate: bool = True) -> None:
        changed = data != self._data
        self._data = list(data)
        if changed and animate:
            self._anim.stop()
            self._anim.start()
        else:
            self.update()

    def data(self) -> list[tuple[str, int]]:
        return list(self._data)

    def _geometry(self) -> tuple[QRectF, float]:
        area = QRectF(4, 22, self.width() - 8, self.height() - 22 - 26)
        top = max([v for _, v in self._data] + [1])
        return area, float(top)

    def _bar_rect(self, index: int, value: int, area: QRectF, top: float) -> QRectF:
        n = max(1, len(self._data))
        slot = area.width() / n
        width = min(50.0, slot * 0.42)
        height = max(area.height() * value / top * self._progress, 2.0)
        cx = area.left() + slot * index + slot / 2
        return QRectF(cx - width / 2, area.bottom() - height, width, height)

    def mouseMoveEvent(self, event) -> None:
        area, top = self._geometry()
        found = -1
        for i, (_, v) in enumerate(self._data):
            slot = area.width() / max(1, len(self._data))
            if abs(event.position().x() - (area.left() + slot * i + slot / 2)) < slot / 2:
                found = i
        if found != self._hover:
            self._hover = found
            if found >= 0:
                label, value = self._data[found]
                self.setToolTip(f"{label}: {value}")
            else:
                self.setToolTip("")
            self.update()

    def leaveEvent(self, event) -> None:
        self._hover = -1
        self.update()

    def paintEvent(self, event) -> None:
        p = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area, top = self._geometry()
        painter.setPen(QPen(hairline(22, 20), 1))
        for g in range(4):
            y = area.top() + area.height() * g / 3
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
        font = mono(9)
        painter.setFont(font)
        n = len(self._data)
        for i, (label, value) in enumerate(self._data):
            rect = self._bar_rect(i, value, area, top)
            last = i == n - 1
            colour = QColor(p.text)
            colour.setAlpha(255 if last else (110 if i == self._hover else 76))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(QColor(p.muted))
            slot = area.width() / max(1, n)
            cx = area.left() + slot * i + slot / 2
            if n <= 14 or i % 2 == 0:
                painter.drawText(
                    QRectF(cx - slot / 2, rect.top() - 20, slot, 16),
                    Qt.AlignmentFlag.AlignCenter, str(value),
                )
                painter.drawText(
                    QRectF(cx - slot, area.bottom() + 6, slot * 2, 18),
                    Qt.AlignmentFlag.AlignCenter, label,
                )
        painter.end()


class Orb(QWidget):
    """The detection engine mark: dashed outer ring, two arcs turning against each other and a breathing sphere."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(140, 140)
        self._t = 0.0
        self._running = True
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._step)
        self._timer.start()

    def set_running(self, running: bool) -> None:
        self._running = running

    def _step(self) -> None:
        if self._running and self.isVisible():
            self._t += 0.04
            self.update()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        self._timer.start()
        super().showEvent(event)

    def paintEvent(self, event) -> None:
        p = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        text = QColor(p.text)
        muted = QColor(p.muted)
        # outer dashed ring turning slowly
        painter.save()
        painter.translate(c)
        painter.rotate(math.degrees(self._t) / 24 * 4)
        pen = QPen(muted, 1, Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([3, 4])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), 69, 69)
        painter.restore()
        # middle arc, opposite way
        painter.save()
        painter.translate(c)
        painter.rotate(-math.degrees(self._t) * 0.9)
        painter.setPen(QPen(text, 1.2))
        painter.drawArc(QRectF(-50, -50, 100, 100), 40 * 16, 110 * 16)
        painter.restore()
        # inner double arc
        painter.save()
        painter.translate(c)
        painter.rotate(math.degrees(self._t) * 1.4)
        painter.setPen(QPen(text, 1.2))
        painter.drawArc(QRectF(-30, -30, 60, 60), 120 * 16, 80 * 16)
        painter.drawArc(QRectF(-30, -30, 60, 60), 300 * 16, 80 * 16)
        painter.restore()
        # breathing sphere
        scale = 1.0 + 0.06 * math.sin(self._t * 1.9)
        radius = 12 * scale
        grad = QRadialGradient(QPointF(c.x() - radius * 0.3, c.y() - radius * 0.4), radius * 1.6)
        grad.setColorAt(0.0, text)
        grad.setColorAt(1.0, muted)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(c, radius, radius)
        painter.end()


class GhostButton(QPushButton):
    """Pill button. primary = solid, otherwise a hairline outline."""

    def __init__(self, text: str = "", primary: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            self.setProperty("primary", True)
        self.setMinimumHeight(34)


def card_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("cardtitle", True)
    return label


def row_layout(*widgets: QWidget, spacing: int = 12) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for w in widgets:
        layout.addWidget(w)
    return layout
