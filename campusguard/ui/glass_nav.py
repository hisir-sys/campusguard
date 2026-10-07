"""Glass-style navigation for CampusGuard.

Pieces:

* ``BackdropWidget``  - the window background (dark gradient with soft glows) that the
  translucent bars and cards sit on, which is what makes them look like glass.
* ``GlassBar``        - a rounded translucent bar. A soft light follows the mouse and a
  bright streak runs along the top edge under the cursor.
* ``NavButton``       - text (+ optional icon) button. On hover the text brightens and a
  indigo active underline grows from the center; the active page keeps the underline.
* ``SearchControl``   - a search icon that expands into a indigo focus field (ESC / x to close).
* ``TopBar`` / ``BottomBar`` - the two ready-made bars used by the main window.

Everything here is custom-painted from the palette in ``theme.py``, so a theme switch
only needs a repaint (``retint()`` is called on these widgets by ``apply_theme``).
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from campusguard.ui.icons import IconLabel, icon_pixmap
from campusguard.ui.theme import get_palette, mix_colors, qcolor, rgba


def _make_anim(owner: QWidget, duration: int, on_value) -> QVariantAnimation:
    anim = QVariantAnimation(owner)
    anim.setDuration(duration)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.valueChanged.connect(lambda value: on_value(float(value)))
    return anim


def _run(anim: QVariantAnimation, start: float, end: float) -> None:
    anim.stop()
    anim.setStartValue(float(start))
    anim.setEndValue(float(end))
    anim.start()


# ----------------------------------------------------------------------------
# Window backdrop
# ----------------------------------------------------------------------------
class BackdropWidget(QWidget):
    """Paints the dark/light gradient and the soft glows behind everything."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache: QPixmap | None = None
        self._cache_key: tuple = ()

    def retint(self) -> None:
        self._cache = None
        self.update()

    def resizeEvent(self, event) -> None:
        self._cache = None
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:
        pal = get_palette()
        ratio = self.devicePixelRatioF()
        key = (self.width(), self.height(), ratio, pal.name)
        if self._cache is None or key != self._cache_key:
            self._cache = self._build(pal, ratio)
            self._cache_key = key
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._cache)

    def _build(self, pal, ratio: float) -> QPixmap:
        w = max(1, self.width())
        h = max(1, self.height())
        pixmap = QPixmap(max(1, int(w * ratio)), max(1, int(h * ratio)))
        pixmap.setDevicePixelRatio(ratio)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        base = QLinearGradient(0, 0, 0, h)
        base.setColorAt(0.0, QColor(pal.bg0))
        base.setColorAt(1.0, QColor(pal.bg1))
        painter.fillRect(QRectF(0, 0, w, h), QBrush(base))

        reach = float(max(w, h))
        self._glow(painter, w, h, QPointF(w * 0.10, -h * 0.05), reach * 0.55, pal.glow1, pal.glow1_alpha)
        self._glow(painter, w, h, QPointF(w * 0.92, h * 1.0), reach * 0.60, pal.glow2, pal.glow2_alpha)
        self._glow(painter, w, h, QPointF(w * 0.60, h * 0.30), reach * 0.30, pal.glow2, int(pal.glow2_alpha * 0.5))

        # two soft diagonal bands, like the folded wallpaper behind the glass in the reference
        for start_y, end_y, bulge in ((0.78, 0.50, 0.30), (0.95, 0.68, 0.12)):
            band = QPainterPath()
            band.moveTo(-w * 0.1, h * start_y)
            band.cubicTo(w * 0.30, h * (start_y - bulge), w * 0.60, h * (start_y + 0.25), w * 1.1, h * end_y)
            band.lineTo(w * 1.1, h * (end_y + 0.20))
            band.cubicTo(w * 0.60, h * (start_y + 0.45), w * 0.30, h * (start_y + 0.05), -w * 0.1, h * (start_y + 0.25))
            band.closeSubpath()
            sheen = QLinearGradient(0, 0, w, 0)
            sheen.setColorAt(0.0, qcolor(pal.veil, 0))
            sheen.setColorAt(0.5, qcolor(pal.veil, int(pal.veil_alpha * 0.8)))
            sheen.setColorAt(1.0, qcolor(pal.veil, 0))
            painter.fillPath(band, QBrush(sheen))

        painter.end()
        return pixmap

    @staticmethod
    def _glow(painter: QPainter, w: int, h: int, center: QPointF, radius: float, color: str, alpha: int) -> None:
        gradient = QRadialGradient(center, radius)
        gradient.setColorAt(0.0, qcolor(color, alpha))
        gradient.setColorAt(1.0, qcolor(color, 0))
        painter.fillRect(QRectF(0, 0, w, h), QBrush(gradient))


# ----------------------------------------------------------------------------
# Glass bar
# ----------------------------------------------------------------------------
class GlassBar(QWidget):
    """A rounded translucent bar with a mouse-following light and top-edge streak."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hover = 0.0
        self._hovering = False
        self._spot_x = 0.0
        self._hover_anim = _make_anim(self, 240, self._set_hover)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def retint(self) -> None:
        self.update()

    def _set_hover(self, value: float) -> None:
        self._hover = value
        if value <= 0.001 and not self._hovering:
            self._timer.stop()
        self.update()

    def enterEvent(self, event) -> None:
        self._hovering = True
        self._spot_x = float(self.mapFromGlobal(QCursor.pos()).x())
        _run(self._hover_anim, self._hover, 1.0)
        if not self._timer.isActive():
            self._timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovering = False
        _run(self._hover_anim, self._hover, 0.0)
        super().leaveEvent(event)

    def _tick(self) -> None:
        pos = self.mapFromGlobal(QCursor.pos())
        target = float(min(max(pos.x(), 0), self.width()))
        self._spot_x += (target - self._spot_x) * 0.22
        self.update()

    def paintEvent(self, event) -> None:
        pal = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = float(self.width())
        h = float(self.height())
        radius = min(18.0, h / 2.0)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0), radius, radius)

        fill = QLinearGradient(0, 0, 0, h)
        fill.setColorAt(0.0, qcolor(pal.glass, pal.glass_alpha + 18))
        fill.setColorAt(1.0, qcolor(pal.glass, pal.glass_alpha - 14))
        painter.fillPath(path, QBrush(fill))

        painter.save()
        painter.setClipPath(path)

        sheen = QLinearGradient(0, 0, 0, h * 0.55)
        sheen.setColorAt(0.0, qcolor("#ffffff", pal.sheen_alpha))
        sheen.setColorAt(1.0, qcolor("#ffffff", 0))
        painter.fillRect(QRectF(0, 0, w, h * 0.55), QBrush(sheen))

        if self._hover > 0.01:
            spot = QRadialGradient(QPointF(self._spot_x, h * 0.5), max(120.0, w * 0.18))
            spot.setColorAt(0.0, qcolor(pal.accent, int(34 * self._hover)))
            spot.setColorAt(1.0, qcolor(pal.accent, 0))
            painter.fillRect(QRectF(0, 0, w, h), QBrush(spot))

            streak = QLinearGradient(self._spot_x - 100, 0, self._spot_x + 100, 0)
            streak.setColorAt(0.0, qcolor(pal.edge, 0))
            streak.setColorAt(0.5, qcolor(pal.edge, int(220 * self._hover)))
            streak.setColorAt(1.0, qcolor(pal.edge, 0))
            painter.fillRect(QRectF(0, 0, w, 1.6), QBrush(streak))
        painter.restore()

        pen = QPen(qcolor(pal.line, pal.line_alpha + int(30 * self._hover)))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)


# ----------------------------------------------------------------------------
# Buttons
# ----------------------------------------------------------------------------
class NavButton(QAbstractButton):
    """Text (+ optional icon) nav item with a hover/active red underline."""

    ICON_SIZE = 16

    def __init__(
        self,
        text: str,
        icon: str | None = None,
        expand: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setText(text)
        self._icon = icon
        self._hover = 0.0
        self._active = 0.0
        self._badge = 0
        self._hover_anim = _make_anim(self, 170, self._set_hover)
        self._active_anim = _make_anim(self, 240, self._set_active_value)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setFixedHeight(48)
        horizontal = QSizePolicy.Policy.Expanding if expand else QSizePolicy.Policy.Minimum
        self.setSizePolicy(horizontal, QSizePolicy.Policy.Fixed)

    # --- state -----------------------------------------------------------
    def set_active(self, active: bool) -> None:
        _run(self._active_anim, self._active, 1.0 if active else 0.0)

    def set_badge(self, count: int) -> None:
        count = max(0, int(count))
        if count != self._badge:
            self._badge = count
            self.update()

    def retint(self) -> None:
        self.update()

    def _set_hover(self, value: float) -> None:
        self._hover = value
        self.update()

    def _set_active_value(self, value: float) -> None:
        self._active = value
        self.update()

    def enterEvent(self, event) -> None:
        _run(self._hover_anim, self._hover, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        _run(self._hover_anim, self._hover, 0.0)
        super().leaveEvent(event)

    # --- sizing / painting -------------------------------------------------
    def _label_font(self) -> QFont:
        font = QFont(self.font())
        font.setWeight(QFont.Weight.Medium)
        return font

    def _content_width(self) -> float:
        metrics = QFontMetrics(self._label_font())
        width = float(metrics.horizontalAdvance(self.text()))
        if self._icon:
            width += self.ICON_SIZE + 8
        return width

    def sizeHint(self) -> QSize:
        self.ensurePolished()
        return QSize(int(self._content_width()) + 36, 48)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event) -> None:
        pal = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w = float(self.width())
        h = float(self.height())
        cy = h / 2.0
        font = self._label_font()
        metrics = QFontMetrics(font)

        reveal = max(self._hover, self._active)
        text_color = mix_colors(QColor(pal.text_dim), QColor(pal.text), reveal)

        # soft pill behind the active item
        if self._active > 0.01:
            pill = QRectF(2.0, 2.0, w - 4.0, h - 4.0)
            painter.setPen(QPen(qcolor(pal.accent, int(60 * self._active)), 1.0))
            painter.setBrush(qcolor(pal.accent, int(22 * self._active)))
            painter.drawRoundedRect(pill, 12.0, 12.0)

        content_w = self._content_width()
        x = (w - content_w) / 2.0
        if self._icon:
            icon_color = mix_colors(text_color, QColor(pal.accent), self._active)
            pixmap = icon_pixmap(self._icon, self.ICON_SIZE, icon_color.name())
            painter.drawPixmap(QPointF(x, cy - self.ICON_SIZE / 2.0), pixmap)
            x += self.ICON_SIZE + 8

        painter.setFont(font)
        painter.setPen(text_color)
        baseline = cy + (metrics.ascent() - metrics.descent()) / 2.0
        painter.drawText(QPointF(x, baseline), self.text())

        # the red underline grows from the center
        if reveal > 0.01:
            underline_w = (content_w + 8.0) * reveal
            underline_y = h - 4.0
            left = (w - underline_w) / 2.0
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(pal.accent, int(60 * reveal)))
            painter.drawRoundedRect(QRectF(left - 2, underline_y - 1.5, underline_w + 4, 4.0), 2.0, 2.0)
            painter.setBrush(qcolor(pal.accent, 255))
            painter.drawRoundedRect(QRectF(left, underline_y, underline_w, 2.0), 1.0, 1.0)

        if self._badge > 0:
            small = QFont(font)
            small.setPointSizeF(max(6.5, font.pointSizeF() - 2.5))
            small.setWeight(QFont.Weight.Bold)
            small_metrics = QFontMetrics(small)
            label = "9+" if self._badge > 9 else str(self._badge)
            badge_w = max(16.0, small_metrics.horizontalAdvance(label) + 9.0)
            left = (w + content_w) / 2.0 + 3.0
            badge_rect = QRectF(left, cy - metrics.height() / 2.0 - 7.0, badge_w, 16.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(pal.bad, 255))
            painter.drawRoundedRect(badge_rect, 8.0, 8.0)
            painter.setFont(small)
            painter.setPen(QColor("#ffffff"))
            text_x = badge_rect.left() + (badge_w - small_metrics.horizontalAdvance(label)) / 2.0
            text_y = badge_rect.center().y() + (small_metrics.ascent() - small_metrics.descent()) / 2.0
            painter.drawText(QPointF(text_x, text_y), label)


class RoundIconButton(QAbstractButton):
    """A circular icon-only button (search, theme toggle, close)."""

    def __init__(self, icon: str, size: int = 34, tone: str = "text", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon = icon
        self._tone = tone
        self._size = int(size)
        self._hover = 0.0
        self._hover_anim = _make_anim(self, 150, self._set_hover)
        self.setFixedSize(self._size, self._size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_icon(self, icon: str) -> None:
        self._icon = icon
        self.update()

    def set_tone(self, tone: str) -> None:
        self._tone = tone
        self.update()

    def retint(self) -> None:
        self.update()

    def _set_hover(self, value: float) -> None:
        self._hover = value
        self.update()

    def enterEvent(self, event) -> None:
        _run(self._hover_anim, self._hover, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        _run(self._hover_anim, self._hover, 0.0)
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        pal = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        size = float(self._size)
        if self._hover > 0.01:
            painter.setPen(QPen(qcolor(pal.line, int((pal.line_alpha + 14) * self._hover)), 1.0))
            painter.setBrush(qcolor(pal.veil, int(pal.veil_alpha * 2.0 * self._hover)))
            painter.drawEllipse(QRectF(1.0, 1.0, size - 2.0, size - 2.0))

        if self._tone == "accent":
            color = QColor(pal.accent)
        else:
            color = mix_colors(QColor(pal.text_dim), QColor(pal.text), self._hover)
        glyph = max(12, int(size * 0.5))
        pixmap = icon_pixmap(self._icon, glyph, color.name())
        painter.drawPixmap(QPointF((size - glyph) / 2.0, (size - glyph) / 2.0), pixmap)


class GlassButton(QAbstractButton):
    """A small rounded text button with a subtle border (the Log in button)."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self._hover = 0.0
        self._hover_anim = _make_anim(self, 150, self._set_hover)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setFixedHeight(40)

    def retint(self) -> None:
        self.update()

    def _set_hover(self, value: float) -> None:
        self._hover = value
        self.update()

    def enterEvent(self, event) -> None:
        _run(self._hover_anim, self._hover, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        _run(self._hover_anim, self._hover, 0.0)
        super().leaveEvent(event)

    def _label_font(self) -> QFont:
        font = QFont(self.font())
        font.setWeight(QFont.Weight.DemiBold)
        return font

    def sizeHint(self) -> QSize:
        self.ensurePolished()
        metrics = QFontMetrics(self._label_font())
        return QSize(metrics.horizontalAdvance(self.text()) + 34, 40)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def setText(self, text: str) -> None:
        super().setText(text)
        self.updateGeometry()
        self.update()

    def paintEvent(self, event) -> None:
        pal = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        painter.setPen(QPen(qcolor(pal.line, int(pal.line_alpha * 1.8 + 50 * self._hover)), 1.0))
        painter.setBrush(qcolor(pal.veil, int(pal.veil_alpha * 1.5 + pal.veil_alpha * 1.5 * self._hover)))
        painter.drawRoundedRect(rect, 11.0, 11.0)

        font = self._label_font()
        metrics = QFontMetrics(font)
        painter.setFont(font)
        painter.setPen(QColor(pal.text))
        text_w = metrics.horizontalAdvance(self.text())
        baseline = h / 2.0 + (metrics.ascent() - metrics.descent()) / 2.0
        painter.drawText(QPointF((w - text_w) / 2.0, baseline), self.text())


# ----------------------------------------------------------------------------
# Search
# ----------------------------------------------------------------------------
class _SearchEdit(QLineEdit):
    escape_pressed = Signal()
    focus_lost = Signal()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.focus_lost.emit()


class SearchControl(QWidget):
    """Search icon that expands (and pushes the nav items left) into a red-outlined field."""

    submitted = Signal(str)

    COLLAPSED_WIDTH = 34
    EXPANDED_WIDTH = 280

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._open = 0.0
        self._is_open = False
        self.setFixedSize(self.COLLAPSED_WIDTH, 34)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        self.icon_button = RoundIconButton("search", 34)
        self.edit = _SearchEdit()
        self.edit.setPlaceholderText("Search incidents, cameras…")
        self.edit.setMinimumWidth(1)
        self.edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.esc_badge = QLabel("ESC")
        self.close_button = RoundIconButton("x", 22)
        self._tail = QWidget()
        self._tail.setFixedWidth(5)

        row.addWidget(self.icon_button)
        row.addWidget(self.edit, 1)
        row.addWidget(self.esc_badge)
        row.addWidget(self.close_button)
        row.addWidget(self._tail)
        for widget in (self.edit, self.esc_badge, self.close_button, self._tail):
            widget.hide()

        self._anim = _make_anim(self, 280, self._apply)
        self.icon_button.clicked.connect(lambda _checked=False: self._icon_clicked())
        self.close_button.clicked.connect(lambda _checked=False: self.collapse())
        self.edit.returnPressed.connect(self._submit)
        self.edit.escape_pressed.connect(self.collapse)
        self.edit.focus_lost.connect(self._focus_lost)
        self.retint()

    # --- public ---------------------------------------------------------
    @property
    def is_open(self) -> bool:
        return self._is_open

    def expand(self) -> None:
        if self._is_open:
            self.edit.setFocus()
            return
        self._is_open = True
        self.icon_button.set_tone("accent")
        self.edit.show()
        _run(self._anim, self._open, 1.0)
        self.edit.setFocus()

    def collapse(self, clear: bool = True) -> None:
        if not self._is_open:
            return
        self._is_open = False
        if clear:
            self.edit.clear()
        for widget in (self.esc_badge, self.close_button, self._tail):
            widget.hide()
        self.icon_button.set_tone("text")
        self.edit.clearFocus()
        _run(self._anim, self._open, 0.0)

    def retint(self) -> None:
        pal = get_palette()
        self.edit.setStyleSheet(
            "QLineEdit { background: transparent; border: none; padding: 0 2px; "
            f"color: {pal.text}; selection-background-color: {pal.accent}; "
            "selection-color: #ffffff; }"
        )
        self.esc_badge.setStyleSheet(
            f"QLabel {{ background: transparent; color: {pal.muted}; "
            f"border: 1px solid {rgba(pal.line, pal.line_alpha + 20)}; border-radius: 5px; "
            "padding: 1px 5px; font-size: 7pt; font-weight: 700; }"
        )
        self.update()

    # --- internals ------------------------------------------------------
    def _apply(self, value: float) -> None:
        self._open = value
        self.setFixedWidth(int(self.COLLAPSED_WIDTH + (self.EXPANDED_WIDTH - self.COLLAPSED_WIDTH) * value))
        if self._is_open and value > 0.85:
            for widget in (self.esc_badge, self.close_button, self._tail):
                if widget.isHidden():
                    widget.show()
        if not self._is_open and value < 0.02:
            self.edit.hide()
        self.update()

    def _icon_clicked(self) -> None:
        if not self._is_open:
            self.expand()
        elif self.edit.text().strip():
            self._submit()
        else:
            self.collapse()

    def _submit(self) -> None:
        self.submitted.emit(self.edit.text().strip())

    def _focus_lost(self) -> None:
        if self._is_open and not self.edit.text().strip():
            QTimer.singleShot(150, self._collapse_if_idle)

    def _collapse_if_idle(self) -> None:
        if self._is_open and not self.edit.hasFocus() and not self.edit.text().strip():
            self.collapse()

    def paintEvent(self, event) -> None:
        if self._open <= 0.01:
            return
        pal = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = float(self.width())
        h = float(self.height())
        radius = h / 2.0
        glow = QPainterPath()
        glow.addRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0), radius, radius)
        painter.fillPath(glow, qcolor(pal.field, int(pal.field_alpha * self._open)))
        painter.setPen(QPen(qcolor(pal.accent, int(70 * self._open)), 3.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0), radius, radius)
        painter.setPen(QPen(qcolor(pal.accent, int(230 * self._open)), 1.2))
        painter.drawRoundedRect(QRectF(1.0, 1.0, w - 2.0, h - 2.0), radius, radius)


# ----------------------------------------------------------------------------
# The two bars
# ----------------------------------------------------------------------------
class _Logo(QWidget):
    clicked = Signal()

    def __init__(self, expanded: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 10, 0)
        row.setSpacing(10)
        self.icon = IconLabel("shield", 24, "accent")
        self.label = QLabel("CampusGuard")
        self.label.setStyleSheet("font-size: 12.5pt; font-weight: 750;")
        row.addWidget(self.icon)
        row.addWidget(self.label, 1)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_expanded(expanded)

    def set_expanded(self, expanded: bool) -> None:
        self.label.setVisible(expanded)
        self.updateGeometry()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _SideNavButton(QAbstractButton):
    def __init__(self, text: str, icon: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = text
        self._icon = icon
        self._active = 0.0
        self._hover = 0.0
        self._expanded = False
        self._badge = 0
        self._hover_anim = _make_anim(self, 160, self._set_hover)
        self._active_anim = _make_anim(self, 220, self._set_active)
        self.setFixedHeight(50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self.updateGeometry()
        self.update()

    def set_active(self, active: bool) -> None:
        _run(self._active_anim, self._active, 1.0 if active else 0.0)

    def set_badge(self, count: int) -> None:
        self._badge = max(0, int(count))
        self.update()

    def _set_hover(self, value: float) -> None:
        self._hover = value
        self.update()

    def _set_active(self, value: float) -> None:
        self._active = value
        self.update()

    def enterEvent(self, event) -> None:
        _run(self._hover_anim, self._hover, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        _run(self._hover_anim, self._hover, 0.0)
        super().leaveEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(58 if not self._expanded else 196, 50)

    def paintEvent(self, event) -> None:
        pal = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w = float(self.width())
        h = float(self.height())
        reveal = max(self._hover, self._active)

        if self._active > 0.01:
            painter.setPen(QPen(qcolor(pal.accent, int(80 * self._active)), 1))
            painter.setBrush(qcolor(pal.accent, int(26 * self._active)))
            painter.drawRoundedRect(QRectF(2, 2, w - 4, h - 4), 12, 12)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(pal.accent, 255))
            painter.drawRoundedRect(QRectF(3, 11, 3, h - 22), 1.5, 1.5)
        elif reveal > 0.01:
            painter.setPen(QPen(qcolor(pal.line, int(18 + 22 * self._hover)), 1))
            painter.setBrush(qcolor(pal.veil, int(20 * self._hover)))
            painter.drawRoundedRect(QRectF(2, 2, w - 4, h - 4), 12, 12)

        color = mix_colors(QColor(pal.text_dim), QColor(pal.text), reveal)
        icon_size = 19
        painter.drawPixmap(QPointF(18, (h - icon_size) / 2), icon_pixmap(self._icon, icon_size, color.name()))

        if self._expanded:
            font = QFont(self.font())
            font.setPointSizeF(9.5)
            font.setWeight(QFont.Weight.Medium)
            painter.setFont(font)
            painter.setPen(color)
            painter.drawText(QPointF(50, h / 2 + 4), self._label)

        if self._badge > 0:
            label = "9+" if self._badge > 9 else str(self._badge)
            badge_rect = QRectF(w - 29, 8, 21, 18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(pal.bad, 255))
            painter.drawRoundedRect(badge_rect, 9, 9)
            painter.setFont(QFont(self.font()))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, label)


class TopBar(GlassBar):
    """Expandable left operations rail. Kept as TopBar for MainWindow compatibility."""

    page_requested = Signal(str)
    theme_toggle_requested = Signal()
    login_requested = Signal()
    search_submitted = Signal(str)

    ITEMS = (
        ("Services", "services", "layers"),
        ("About", "about", "info"),
        ("Tools", "tools", "wrench"),
        ("How It Works", "how-it-works", "route"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sideRail")
        self.setFixedWidth(76)
        self.setMinimumWidth(76)
        self.setMaximumWidth(236)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self._expanded = False
        self._width_anim = _make_anim(self, 220, self._apply_width)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 14, 10, 14)
        root.setSpacing(8)

        self.logo = _Logo(False)
        self.logo.clicked.connect(lambda: self.page_requested.emit("dashboard"))
        root.addWidget(self.logo)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: rgba(255,255,255,0.08); border:none;")
        root.addWidget(divider)
        root.addSpacing(6)

        self._buttons: dict[str, _SideNavButton] = {}
        for label, key, icon in self.ITEMS:
            button = _SideNavButton(label, icon)
            button.clicked.connect(lambda _checked=False, target=key: self.page_requested.emit(target))
            root.addWidget(button)
            self._buttons[key] = button

        root.addStretch(1)

        self.search = SearchControl()
        self.search.submitted.connect(self.search_submitted.emit)
        self.search.setFixedWidth(48)
        root.addWidget(self.search, 0, Qt.AlignmentFlag.AlignHCenter)

        self.theme_button = RoundIconButton("sun", 40)
        self.theme_button.clicked.connect(lambda _checked=False: self.theme_toggle_requested.emit())
        root.addWidget(self.theme_button, 0, Qt.AlignmentFlag.AlignHCenter)

        self.login_button = GlassButton("Log in")
        self.login_button.clicked.connect(lambda _checked=False: self.login_requested.emit())
        root.addWidget(self.login_button, 0, Qt.AlignmentFlag.AlignHCenter)

        self._refresh_expanded_state()

    def _apply_width(self, value: float) -> None:
        width = int(76 + (236 - 76) * value)
        self.setFixedWidth(width)
        self._refresh_expanded_state()

    def _refresh_expanded_state(self) -> None:
        for button in self._buttons.values():
            button.set_expanded(self._expanded)
        self.logo.set_expanded(self._expanded)
        self.search.setFixedWidth(196 if self._expanded else 48)
        self.login_button.setVisible(self._expanded)
        if self._expanded:
            self.login_button.setFixedWidth(196)
        self.update()

    def enterEvent(self, event) -> None:
        self._expanded = True
        _run(self._width_anim, self._width_anim.currentValue() if self._width_anim.currentValue() is not None else 0.0, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._expanded = False
        _run(self._width_anim, self._width_anim.currentValue() if self._width_anim.currentValue() is not None else 1.0, 0.0)
        super().leaveEvent(event)

    def set_active(self, page: str) -> None:
        for key, button in self._buttons.items():
            button.set_active(key == page)

    def set_theme(self, theme: str) -> None:
        if theme == "dark":
            self.theme_button.set_icon("sun")
            self.theme_button.setToolTip("Switch to light mode")
        else:
            self.theme_button.set_icon("moon")
            self.theme_button.setToolTip("Switch to dark mode")

    def set_operator(self, name: str | None) -> None:
        if name:
            self.login_button.setText(f"Log out · {name}")
            self.login_button.setToolTip("This is a local display label, not an authenticated account.")
        else:
            self.login_button.setText("Log in")
            self.login_button.setToolTip("Set a local operator display label. This does not authenticate an account.")

    def focus_search(self) -> None:
        self._expanded = True
        self._refresh_expanded_state()
        _run(self._width_anim, 0.0, 1.0)
        self.search.expand()


class _DockButton(QAbstractButton):
    def __init__(self, text: str, icon: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = text
        self._icon = icon
        self._hover = 0.0
        self._active = 0.0
        self._badge = 0
        self._width = 62.0
        self._width_anim = _make_anim(self, 180, self._apply_width)
        self._hover_anim = _make_anim(self, 160, self._set_hover)
        self._active_anim = _make_anim(self, 220, self._set_active)
        self.setFixedHeight(54)
        self.setFixedWidth(62)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _apply_width(self, value: float) -> None:
        self._width = value
        self.setFixedWidth(int(value))
        self.update()

    def _set_hover(self, value: float) -> None:
        self._hover = value
        self.update()

    def _set_active(self, value: float) -> None:
        self._active = value
        self.update()

    def set_active(self, active: bool) -> None:
        _run(self._active_anim, self._active, 1.0 if active else 0.0)
        if active:
            _run(self._width_anim, self._width, 122.0)
        elif not self.underMouse():
            _run(self._width_anim, self._width, 62.0)

    def set_badge(self, count: int) -> None:
        self._badge = max(0, int(count))
        self.update()

    def enterEvent(self, event) -> None:
        _run(self._hover_anim, self._hover, 1.0)
        _run(self._width_anim, self._width, 122.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        _run(self._hover_anim, self._hover, 0.0)
        if not self._active:
            _run(self._width_anim, self._width, 62.0)
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        pal = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w = float(self.width())
        h = float(self.height())
        reveal = max(self._hover, self._active)

        if reveal > 0.01:
            painter.setPen(QPen(qcolor(pal.accent, int(65 * reveal)), 1))
            painter.setBrush(qcolor(pal.accent, int(24 * reveal)))
            painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 15, 15)

        icon_size = 20
        color = mix_colors(QColor(pal.text_dim), QColor(pal.text), reveal)
        painter.drawPixmap(QPointF(18, (h - icon_size) / 2), icon_pixmap(self._icon, icon_size, color.name()))

        if w > 90:
            font = QFont(self.font())
            font.setPointSizeF(9.5)
            font.setWeight(QFont.Weight.Medium)
            painter.setFont(font)
            painter.setPen(color)
            painter.drawText(QPointF(48, h / 2 + 4), self._label)

        if self._active > 0.01:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(pal.accent, 255))
            painter.drawRoundedRect(QRectF(8, h - 4, w - 16, 2), 1, 1)

        if self._badge > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(pal.bad, 255))
            painter.drawEllipse(QRectF(w - 16, 8, 10, 10))


class BottomBar(GlassBar):
    """Floating glass operations dock: icons by default, labels on hover/active."""

    page_requested = Signal(str)

    TABS = (
        ("Dashboard", "dashboard", "layout-dashboard"),
        ("Cameras", "cameras", "video"),
        ("Incidents", "incidents", "file-warning"),
        ("Alerts", "alerts", "bell"),
        ("Settings", "settings", "settings"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(72)
        self.setMinimumWidth(360)
        self.setMaximumWidth(720)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(9, 9, 9, 9)
        row.setSpacing(6)
        self._buttons: dict[str, _DockButton] = {}
        for label, key, icon in self.TABS:
            button = _DockButton(label, icon)
            button.clicked.connect(lambda _checked=False, target=key: self.page_requested.emit(target))
            row.addWidget(button)
            self._buttons[key] = button

    def set_active(self, page: str) -> None:
        for key, button in self._buttons.items():
            button.set_active(key == page)

    def set_badge(self, key: str, count: int) -> None:
        button = self._buttons.get(key)
        if button is not None:
            button.set_badge(count)
