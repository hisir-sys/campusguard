"""Window backdrop and the account button used by the navigation rail."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QWidget,
)

from campusguard.ui.icons import icon_pixmap
from campusguard.ui.theme import get_palette, qcolor


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
        self._glow(painter, w, h, QPointF(w * 0.12, -h * 0.02), reach * 0.62, pal.glow1, pal.glow1_alpha)
        self._glow(painter, w, h, QPointF(w * 0.95, h * 1.02), reach * 0.66, pal.glow2, pal.glow2_alpha)
        self._glow(painter, w, h, QPointF(w * 0.60, h * 0.30), reach * 0.30, pal.glow2, int(pal.glow2_alpha * 0.5))

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


class AccountButton(GlassButton):
    """Account chip: avatar initial, "Signed in" + elided email, and a log-out glyph.

    The email can never overflow: it is elided to the available width and the
    full address is in the tooltip. Collapsed, only the avatar circle remains.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Log in", parent)
        self._email: str | None = None
        self._compact = False
        self.setFixedHeight(48)

    def set_email(self, email: str | None) -> None:
        self._email = (email or "").strip() or None
        self.setText("Log out" if self._email else "Log in")
        self.update()

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.setFixedHeight(40 if compact else 48)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(196, 48)

    def paintEvent(self, event) -> None:
        pal = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w = float(self.width())
        h = float(self.height())
        if not self._compact:
            painter.setPen(QPen(qcolor(pal.line, int(pal.line_alpha * 1.8 + 50 * self._hover)), 1.0))
            painter.setBrush(qcolor(pal.veil, int(pal.veil_alpha * 1.5 + pal.veil_alpha * 1.5 * self._hover)))
            painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0), 12.0, 12.0)
        diameter = 32.0
        cx = w / 2.0 if self._compact else 8.0 + diameter / 2.0
        circle = QRectF(cx - diameter / 2.0, (h - diameter) / 2.0, diameter, diameter)
        painter.setPen(QPen(qcolor(pal.ink, 150), 1.0))
        painter.setBrush(qcolor(pal.ink, 34 + int(30 * self._hover)))
        painter.drawEllipse(circle)
        initial = (self._email or "?")[:1].upper()
        font = QFont(self.font())
        font.setPointSizeF(10.5)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor(pal.ink))
        painter.drawText(circle, int(Qt.AlignmentFlag.AlignCenter), initial)
        if self._compact:
            return
        if not self._email:
            painter.setFont(self._label_font())
            painter.setPen(QColor(pal.text))
            painter.drawText(QRectF(circle.right() + 10, 0, w - circle.right() - 18, h), int(Qt.AlignmentFlag.AlignVCenter), "Log in")
            return
        icon_size = 16
        icon_x = w - icon_size - 12.0
        painter.drawPixmap(QPointF(icon_x, (h - icon_size) / 2.0), icon_pixmap("log-out", icon_size, get_palette().text_dim))
        text_left = circle.right() + 10.0
        text_w = icon_x - text_left - 8.0
        small = QFont(self.font())
        small.setPointSizeF(7.5)
        small.setWeight(QFont.Weight.Medium)
        painter.setFont(small)
        painter.setPen(QColor(pal.muted))
        painter.drawText(QRectF(text_left, 6, text_w, 16), int(Qt.AlignmentFlag.AlignVCenter), "SIGNED IN")
        main = QFont(self.font())
        main.setPointSizeF(9.0)
        main.setWeight(QFont.Weight.DemiBold)
        painter.setFont(main)
        painter.setPen(QColor(pal.text))
        elided = QFontMetrics(main).elidedText(self._email, Qt.TextElideMode.ElideMiddle, int(text_w))
        painter.drawText(QRectF(text_left, 21, text_w, 20), int(Qt.AlignmentFlag.AlignVCenter), elided)


# ----------------------------------------------------------------------------
# Search
# ----------------------------------------------------------------------------
