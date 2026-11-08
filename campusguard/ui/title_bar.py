"""Themed window title bar (replaces the native Windows caption).

Drag to move (Windows snap works through ``startSystemMove``), double-click to
maximise, and minimise / maximise / close buttons that follow the app theme.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QLabel, QWidget

from campusguard.ui.icons import IconLabel, icon_pixmap
from campusguard.ui.theme import get_palette, qcolor

BAR_HEIGHT = 42
_CLOSE_RED = "#B9656D"


class _CaptionButton(QAbstractButton):
    def __init__(self, icon: str, danger: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon = icon
        self._danger = danger
        self._hover = False
        self.setFixedSize(QSize(44, 30))
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_icon(self, icon: str) -> None:
        self._icon = icon
        self.update()

    def retint(self) -> None:
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        pal = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        color = pal.text_dim
        if self._hover:
            fill = QColor(_CLOSE_RED) if self._danger else qcolor(pal.text, 26)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(QRectF(2, 1, w - 4, h - 2), 8, 8)
            color = "#FFFFFF" if self._danger else pal.text
        size = 16
        painter.drawPixmap(QPointF((w - size) / 2.0, (h - size) / 2.0), icon_pixmap(self._icon, size, color))


class TitleBar(QWidget):
    def __init__(self, window: QWidget, title: str = "CampusGuard", subtitle: str = "Security Operations") -> None:
        super().__init__(window)
        self._window = window
        self.setObjectName("titleBar")
        self.setFixedHeight(BAR_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 8, 0)
        row.setSpacing(10)
        self.logo = IconLabel("shield-check", 20, "accent")
        row.addWidget(self.logo)
        self.title = QLabel(title)
        self.title.setStyleSheet("font-weight: 700; font-size: 10pt; background: transparent;")
        row.addWidget(self.title)
        self.subtitle = QLabel(subtitle)
        self.subtitle.setProperty("muted", True)
        self.subtitle.setStyleSheet("font-size: 9pt; background: transparent;")
        row.addWidget(self.subtitle)
        row.addStretch(1)

        self.minimize_button = _CaptionButton("minus")
        self.maximize_button = _CaptionButton("square")
        self.close_button = _CaptionButton("x", danger=True)
        self.minimize_button.setToolTip("Minimise")
        self.maximize_button.setToolTip("Maximise")
        self.close_button.setToolTip("Close")
        for button in (self.minimize_button, self.maximize_button, self.close_button):
            row.addWidget(button)
        self.minimize_button.clicked.connect(window.showMinimized)
        self.maximize_button.clicked.connect(self.toggle_maximized)
        self.close_button.clicked.connect(window.close)

    def toggle_maximized(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def sync_state(self) -> None:
        maximized = self._window.isMaximized()
        self.maximize_button.set_icon("restore" if maximized else "square")
        self.maximize_button.setToolTip("Restore" if maximized else "Maximise")

    def retint(self) -> None:
        self.logo.retint()
        for button in (self.minimize_button, self.maximize_button, self.close_button):
            button.retint()
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event) -> None:
        # A hairline under the bar separates it from the workspace.
        pal = get_palette()
        painter = QPainter(self)
        painter.setPen(qcolor(pal.line, min(120, pal.line_alpha + 30)))
        painter.drawLine(14, self.height() - 1, self.width() - 14, self.height() - 1)
