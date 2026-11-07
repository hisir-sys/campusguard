"""Left navigation sidebar (replaces the floating rail + bottom dock).

One solid panel: brand, search, grouped navigation with an alert badge, theme
toggle and the account chip. It exposes the same API the main window used with
the old TopBar/BottomBar so every page keeps working unchanged.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
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

from campusguard.ui.brand_logo import LogoMark
from campusguard.ui.glass_nav import AccountButton
from campusguard.ui.icons import icon_pixmap
from campusguard.ui.theme import get_palette, qcolor

FULL_WIDTH = 248
COMPACT_WIDTH = 76

SECTIONS = (
    (
        "OPERATIONS",
        (
            ("Dashboard", "dashboard", "layout-dashboard"),
            ("Cameras", "cameras", "video"),
            ("Incidents", "incidents", "file-warning"),
            ("Alerts", "alerts", "bell"),
            ("School server", "server-viewer", "server"),
        ),
    ),
    ("SYSTEM", (("Settings", "settings", "settings"),)),
    (
        "LEARN",
        (
            ("Services", "services", "layers"),
            ("About", "about", "info"),
            ("Tools", "tools", "wrench"),
            ("How it works", "how-it-works", "route"),
        ),
    ),
)


class _NavItem(QAbstractButton):
    def __init__(self, label: str, icon: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = label
        self._icon = icon
        self._active = False
        self._hover = False
        self._compact = False
        self._badge = 0
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setToolTip(label)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.update()

    def set_badge(self, count: int) -> None:
        self._badge = max(0, int(count))
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(FULL_WIDTH - 24, 40)

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
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = float(self.width()), float(self.height())
        body = QRectF(0.5, 0.5, w - 1, h - 1)
        if self._active:
            painter.setPen(QPen(qcolor(pal.ink, 70), 1))
            painter.setBrush(qcolor(pal.ink, 26))
            painter.drawRoundedRect(body, 11, 11)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(pal.ink))
            painter.drawRoundedRect(QRectF(0, h * 0.28, 3, h * 0.44), 1.5, 1.5)
        elif self._hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(pal.text, 14))
            painter.drawRoundedRect(body, 11, 11)
        tint = pal.ink if self._active else (pal.text if self._hover else pal.text_dim)
        size = 19
        icon_x = (w - size) / 2.0 if self._compact else 14.0
        painter.drawPixmap(QPointF(icon_x, (h - size) / 2.0), icon_pixmap(self._icon, size, tint))
        if not self._compact:
            font = QFont(self.font())
            font.setPointSizeF(10.0)
            font.setWeight(QFont.Weight.DemiBold if self._active else QFont.Weight.Medium)
            painter.setFont(font)
            painter.setPen(QColor(pal.text if (self._active or self._hover) else pal.text_dim))
            right = 56.0 if self._badge else 14.0
            text_rect = QRectF(14 + size + 12, 0, w - (14 + size + 12) - right, h)
            elided = QFontMetrics(font).elidedText(self._label, Qt.TextElideMode.ElideRight, int(text_rect.width()))
            painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), elided)
        if self._badge:
            text = "99+" if self._badge > 99 else str(self._badge)
            if self._compact:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(qcolor(pal.bad))
                painter.drawEllipse(QRectF(w - 20, 6, 10, 10))
            else:
                font = QFont(self.font())
                font.setPointSizeF(8.0)
                font.setWeight(QFont.Weight.Bold)
                painter.setFont(font)
                pill_w = max(22.0, QFontMetrics(font).horizontalAdvance(text) + 14)
                pill = QRectF(w - pill_w - 12, (h - 20) / 2.0, pill_w, 20)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(qcolor(pal.bad, 235))
                painter.drawRoundedRect(pill, 10, 10)
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(pill, int(Qt.AlignmentFlag.AlignCenter), text)


class _SectionLabel(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setProperty("muted", True)
        self.setStyleSheet("font-size: 8pt; font-weight: 700; letter-spacing: 1.4px; padding: 10px 14px 4px 14px; background: transparent;")


class _ThemeToggle(QAbstractButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dark = True
        self._compact = False
        self._hover = False
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self.update()

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
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
        if self._hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(pal.text, 14))
            painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 11, 11)
        size = 19
        icon = "sun" if self._dark else "moon"
        x = (w - size) / 2.0 if self._compact else 14.0
        painter.drawPixmap(QPointF(x, (h - size) / 2.0), icon_pixmap(icon, size, pal.text_dim))
        if not self._compact:
            font = QFont(self.font())
            font.setPointSizeF(10.0)
            painter.setFont(font)
            painter.setPen(QColor(pal.text_dim))
            painter.drawText(
                QRectF(14 + size + 12, 0, w - 60, h),
                int(Qt.AlignmentFlag.AlignVCenter),
                "Light mode" if self._dark else "Dark mode",
            )


class Sidebar(QFrame):
    page_requested = Signal(str)
    theme_toggle_requested = Signal()
    login_requested = Signal()
    search_submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setProperty("card", True)
        self.setFixedWidth(FULL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._compact = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 16, 12, 12)
        root.setSpacing(2)

        self.brand_row = QWidget()
        brand = QHBoxLayout(self.brand_row)
        brand.setContentsMargins(6, 0, 6, 0)
        brand.setSpacing(10)
        self.logo = LogoMark(size=30)
        brand.addWidget(self.logo)
        self.brand_text = QWidget()
        text_col = QVBoxLayout(self.brand_text)
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)
        self.brand_name = QLabel("CampusGuard")
        self.brand_name.setStyleSheet("font-size: 12pt; font-weight: 700; background: transparent;")
        self.brand_tag = QLabel("Security operations")
        self.brand_tag.setProperty("muted", True)
        self.brand_tag.setStyleSheet("font-size: 8pt; background: transparent;")
        text_col.addWidget(self.brand_name)
        text_col.addWidget(self.brand_tag)
        brand.addWidget(self.brand_text, 1)
        root.addWidget(self.brand_row)
        root.addSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search   Ctrl K")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedHeight(38)
        self.search.returnPressed.connect(lambda: self.search_submitted.emit(self.search.text().strip()))
        root.addWidget(self.search)

        self._buttons: dict[str, _NavItem] = {}
        self._section_labels: list[_SectionLabel] = []
        for title, items in SECTIONS:
            label = _SectionLabel(title)
            self._section_labels.append(label)
            root.addWidget(label)
            for text, key, icon in items:
                item = _NavItem(text, icon)
                item.clicked.connect(lambda _c=False, target=key: self.page_requested.emit(target))
                root.addWidget(item)
                self._buttons[key] = item

        root.addStretch(1)
        self.theme_toggle = _ThemeToggle()
        self.theme_toggle.clicked.connect(lambda _c=False: self.theme_toggle_requested.emit())
        root.addWidget(self.theme_toggle)
        root.addSpacing(4)
        self.login_button = AccountButton()
        self.login_button.clicked.connect(lambda _c=False: self.login_requested.emit())
        root.addWidget(self.login_button)
        self.set_compact(False)

    # ----- API used by the main window ---------------------------------
    def set_active(self, page: str) -> None:
        for key, item in self._buttons.items():
            item.set_active(key == page)

    def set_badge(self, key: str, count: int) -> None:
        item = self._buttons.get(key)
        if item is not None:
            item.set_badge(count)

    def set_theme(self, theme: str) -> None:
        self.theme_toggle.set_dark(theme == "dark")
        self.logo.update()
        self.update()

    def set_operator(self, name: str | None) -> None:
        self.login_button.set_email(name)
        self.login_button.setToolTip(
            f"Signed in as {name}. Click to log out." if name else "Sign in with your CampusGuard account."
        )

    def focus_search(self) -> None:
        if self._compact:
            self.set_compact(False)
        self.search.setFocus()
        self.search.selectAll()

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.setFixedWidth(COMPACT_WIDTH if compact else FULL_WIDTH)
        self.brand_text.setVisible(not compact)
        self.search.setVisible(not compact)
        for label in self._section_labels:
            label.setVisible(not compact)
        for item in self._buttons.values():
            item.set_compact(compact)
        self.theme_toggle.set_compact(compact)
        self.login_button.set_compact(compact)
        self.login_button.setFixedWidth(44 if compact else FULL_WIDTH - 24)

    def is_compact(self) -> bool:
        return self._compact
