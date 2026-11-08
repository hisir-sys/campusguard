"""Single hover-expanding CampusGuard navigation sidebar.

The rail and labelled navigation are one surface: it stays narrow until the
pointer enters, then widens to reveal labels, camera search and account tools.
All page and theme actions continue through the existing signals.
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QSizePolicy, QGraphicsDropShadowEffect, QVBoxLayout, QWidget,
)

from campusguard.ui.brand_logo import LogoMark
from campusguard.ui.glass_nav import AccountButton
from campusguard.ui.icons import icon_pixmap
from campusguard.ui.theme import get_palette, qcolor

RAIL_WIDTH = 66
PANEL_WIDTH = 286
COMPACT_WIDTH = RAIL_WIDTH
EXPANDED_WIDTH = PANEL_WIDTH

SECTIONS = (
    ("HOME", (
        ("Dashboard", "dashboard", "layout-dashboard"),
        ("Cameras", "cameras", "video"),
        ("Incidents", "incidents", "file-warning"),
        ("Alerts", "alerts", "bell"),
        ("School server", "server-viewer", "server"),
    )),
    ("LEARN", (
        ("Services", "services", "layers"),
        ("About", "about", "info"),
        ("Tools", "tools", "wrench"),
        ("How it works", "how-it-works", "route"),
    )),
)


class _NavItem(QAbstractButton):
    def __init__(self, label: str, icon: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label, self._icon = label, icon
        self._active = self._hover = False
        self._compact = True
        self._badge = 0
        self.setFixedHeight(39)
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
        return QSize(PANEL_WIDTH - 24, 39)

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
        radius = h / 2 - 1 if self._compact else 12.0
        if self._active:
            fill = QLinearGradient(0, 0, 0, h)
            fill.setColorAt(0, qcolor(pal.ink, 35 if pal.name == "dark" else 24))
            fill.setColorAt(1, qcolor(pal.ink, 13 if pal.name == "dark" else 10))
            painter.setPen(QPen(qcolor(pal.ink, 95), 1))
            painter.setBrush(fill)
            painter.drawRoundedRect(body, radius, radius)
        elif self._hover:
            painter.setPen(QPen(qcolor(pal.text, 20), 1))
            painter.setBrush(qcolor(pal.text, 12))
            painter.drawRoundedRect(body, radius, radius)
        tint = pal.ink if self._active else (pal.text if self._hover else pal.text_dim)
        size = 19
        icon_x = (w - size) / 2 if self._compact else 14
        painter.drawPixmap(QPointF(icon_x, (h - size) / 2), icon_pixmap(self._icon, size, tint))
        if not self._compact:
            font = QFont(self.font())
            font.setPointSizeF(9.5)
            font.setWeight(QFont.Weight.DemiBold if self._active else QFont.Weight.Medium)
            painter.setFont(font)
            painter.setPen(QColor(pal.text if (self._active or self._hover) else pal.text_dim))
            right = 54 if self._badge else 12
            rect = QRectF(45, 0, w - 45 - right, h)
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                             QFontMetrics(font).elidedText(self._label, Qt.TextElideMode.ElideRight, int(rect.width())))
        if self._badge:
            text = "99+" if self._badge > 99 else str(self._badge)
            if self._compact:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(qcolor(pal.bad))
                painter.drawEllipse(QRectF(w - 20, 5, 10, 10))
            else:
                font = QFont(self.font())
                font.setPointSizeF(8)
                font.setWeight(QFont.Weight.Bold)
                painter.setFont(font)
                pw = max(22, QFontMetrics(font).horizontalAdvance(text) + 14)
                pill = QRectF(w - pw - 8, (h - 20) / 2, pw, 20)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(qcolor(pal.bad, 235))
                painter.drawRoundedRect(pill, 10, 10)
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(pill, int(Qt.AlignmentFlag.AlignCenter), text)


class _SectionLabel(QWidget):
    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text
        self._compact = True
        self.setFixedHeight(19)

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.setFixedHeight(18 if compact else 25)
        self.update()

    def paintEvent(self, event) -> None:
        pal = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        if self._compact:
            painter.setPen(QPen(qcolor(pal.text, 28), 1))
            painter.drawLine(QPointF(w * .32, h / 2), QPointF(w * .68, h / 2))
            return
        font = QFont(self.font())
        font.setPointSizeF(7.5)
        font.setWeight(QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.3)
        painter.setFont(font)
        painter.setPen(QColor(pal.muted))
        painter.drawText(QRectF(8, 0, w - 16, h), int(Qt.AlignmentFlag.AlignVCenter), self._text)


class _ThemeToggle(QAbstractButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dark = True
        self._compact = True
        self._hover = False
        self.setFixedHeight(39)
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
            painter.drawRoundedRect(QRectF(.5, .5, w - 1, h - 1), h / 2, h / 2)
        icon = "sun" if self._dark else "moon"
        size = 19
        x = (w - size) / 2 if self._compact else 14
        painter.drawPixmap(QPointF(x, (h - size) / 2), icon_pixmap(icon, size, pal.text_dim))
        if not self._compact:
            font = QFont(self.font())
            font.setPointSizeF(9.5)
            painter.setFont(font)
            painter.setPen(QColor(pal.text_dim))
            painter.drawText(QRectF(45, 0, w - 54, h), int(Qt.AlignmentFlag.AlignVCenter),
                             "Light mode" if self._dark else "Dark mode")


class _SidebarSurface(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, event) -> None:
        pal = get_palette()
        dark = pal.name == "dark"
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(.5, .5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, 28, 28)
        gradient = QLinearGradient(0, 0, self.width(), 0)
        if dark:
            gradient.setColorAt(0, QColor("#111512"))
            gradient.setColorAt(.5, QColor("#1C211D"))
            gradient.setColorAt(1, QColor("#101410"))
        else:
            gradient.setColorAt(0, QColor("#D8D8D6"))
            gradient.setColorAt(.5, QColor("#F0F0EE"))
            gradient.setColorAt(1, QColor("#D4D4D2"))
        painter.fillPath(path, gradient)
        glow = QRadialGradient(QPointF(self.width() * .5, 0), max(self.width(), 120))
        glow.setColorAt(0, qcolor(pal.ink, 24 if dark else 10))
        glow.setColorAt(1, qcolor(pal.ink, 0))
        painter.fillPath(path, glow)
        painter.setPen(QPen(qcolor(pal.text, 55 if dark else 180), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)


class Sidebar(QWidget):
    page_requested = Signal(str)
    theme_toggle_requested = Signal()
    login_requested = Signal()
    search_submitted = Signal(str)
    camera_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._compact = True
        self._buttons: dict[str, list[_NavItem]] = {}
        self._cameras = []
        self._width_animation = QVariantAnimation(self)
        self._width_animation.setDuration(190)
        self._width_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._width_animation.valueChanged.connect(lambda value: self.setFixedWidth(int(value)))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.surface = _SidebarSurface()
        self.surface.setMouseTracking(True)
        outer.addWidget(self.surface)
        root = QVBoxLayout(self.surface)
        root.setContentsMargins(9, 12, 9, 12)
        root.setSpacing(3)

        brand = QHBoxLayout()
        brand.setContentsMargins(0, 0, 0, 5)
        self.logo = LogoMark(size=30)
        self.logo.setToolTip("CampusGuard home")
        brand.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignLeft)
        self.brand_name = QLabel("CampusGuard")
        self.brand_name.setStyleSheet("font-size: 9pt; font-weight: 750; background: transparent;")
        brand.addWidget(self.brand_name, 1)
        root.addLayout(brand)

        self._section_labels: list[_SectionLabel] = []
        for title, items in SECTIONS:
            label = _SectionLabel(title)
            self._section_labels.append(label)
            root.addWidget(label)
            for text, key, icon in items:
                root.addWidget(self._make_item(text, key, icon))

        self.camera_heading = _SectionLabel("CAMERA SEARCH")
        self._section_labels.append(self.camera_heading)
        root.addWidget(self.camera_heading)
        self.camera_search = QLineEdit()
        self.camera_search.setPlaceholderText("Find a camera...")
        self.camera_search.setClearButtonEnabled(True)
        self.camera_search.setFixedHeight(35)
        self.camera_search.textChanged.connect(self._filter_cameras)
        self.camera_search.editingFinished.connect(
            lambda: None if self.underMouse() else self.set_compact(True)
        )
        root.addWidget(self.camera_search)
        self.camera_results = QListWidget()
        self.camera_results.setObjectName("sidebarCameraResults")
        self.camera_results.setFrameShape(QFrame.Shape.NoFrame)
        self.camera_results.setMaximumHeight(126)
        self.camera_results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.camera_results.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.camera_results.itemClicked.connect(self._open_camera_result)
        self.camera_results.hide()
        root.addWidget(self.camera_results)

        root.addStretch(1)
        self.account_button = AccountButton()
        self.account_button.clicked.connect(lambda _checked=False: self.login_requested.emit())
        root.addWidget(self.account_button)
        self.theme_toggle = _ThemeToggle()
        self.theme_toggle.clicked.connect(lambda _checked=False: self.theme_toggle_requested.emit())
        root.addWidget(self.theme_toggle)
        self.settings_button = self._make_item("System Settings", "settings", "settings")
        root.addWidget(self.settings_button)

        self.login_button = self.account_button
        self.rail_account = self.account_button
        self.rail = self.surface
        self.rail_bottom = self.surface
        self.panel = self.surface
        self.search = self.camera_search
        self.brand_tag = QLabel("")

        self.set_compact(True)
        self._apply_compact_visibility()

    def _make_item(self, text: str, key: str, icon: str) -> _NavItem:
        item = _NavItem(text, icon)
        item.clicked.connect(lambda _checked=False, target=key: self.page_requested.emit(target))
        self._buttons.setdefault(key, []).append(item)
        return item

    def _apply_compact_visibility(self) -> None:
        for label in self._section_labels:
            label.set_compact(self._compact)
        for items in self._buttons.values():
            for item in items:
                item.set_compact(self._compact)
        self.theme_toggle.set_compact(self._compact)
        self.account_button.set_compact(self._compact)
        self.brand_name.setVisible(not self._compact)
        self.camera_search.setVisible(not self._compact)
        self.camera_results.setVisible(not self._compact and self.camera_results.count() > 0)
        if self._compact:
            self.camera_search.clearFocus()

    def _animate_width(self, target: int) -> None:
        self._width_animation.stop()
        self._width_animation.setStartValue(self.width())
        self._width_animation.setEndValue(target)
        self._width_animation.start()

    def enterEvent(self, event) -> None:
        self.set_compact(False)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        # Stay open while the camera search is being used.
        if not self.camera_search.hasFocus():
            self.set_compact(True)
        super().leaveEvent(event)

    def _filter_cameras(self, query: str) -> None:
        needle = query.casefold().strip()
        self.camera_results.clear()
        for camera in self._cameras:
            haystack = f"{camera.name} {camera.camera_id} {camera.source_address}".casefold()
            if not needle or needle in haystack:
                item = QListWidgetItem(camera.name)
                item.setData(Qt.ItemDataRole.UserRole, camera.camera_id)
                item.setToolTip(f"{camera.name} · {camera.camera_id}")
                self.camera_results.addItem(item)
        self.camera_results.setVisible(not self._compact and self.camera_results.count() > 0)

    def _open_camera_result(self, item: QListWidgetItem) -> None:
        camera_id = item.data(Qt.ItemDataRole.UserRole)
        if camera_id:
            self.camera_selected.emit(str(camera_id))

    def set_cameras(self, cameras) -> None:
        self._cameras = list(cameras)
        self._filter_cameras(self.camera_search.text())

    def set_active(self, page: str) -> None:
        for key, items in self._buttons.items():
            for item in items:
                item.set_active(key == page)

    def set_badge(self, key: str, count: int) -> None:
        for item in self._buttons.get(key, []):
            item.set_badge(count)

    def set_theme(self, theme: str) -> None:
        self.theme_toggle.set_dark(theme == "dark")
        self.logo.update()
        self.surface.update()

    def set_operator(self, name: str | None) -> None:
        tip = f"Signed in as {name}. Click to log out." if name else "Sign in with your CampusGuard account."
        self.account_button.set_email(name)
        self.account_button.setToolTip(tip)

    def focus_search(self) -> None:
        self.set_compact(False)
        self.camera_search.setFocus()
        self.camera_search.selectAll()

    def toggle_compact(self) -> None:
        self.set_compact(not self._compact)

    def set_compact(self, compact: bool) -> None:
        compact = bool(compact)
        if compact == self._compact and self.width() == (COMPACT_WIDTH if compact else EXPANDED_WIDTH):
            return
        self._compact = compact
        self._apply_shadow()
        self._apply_compact_visibility()
        self._animate_width(COMPACT_WIDTH if compact else EXPANDED_WIDTH)

    def _apply_shadow(self) -> None:
        """Lift the expanded sidebar off the page it floats over."""
        if self._compact:
            self.surface.setGraphicsEffect(None)
            return
        shadow = QGraphicsDropShadowEffect(self.surface)
        shadow.setBlurRadius(34)
        shadow.setOffset(8, 0)
        shadow.setColor(QColor(0, 0, 0, 120 if get_palette().name == "dark" else 60))
        self.surface.setGraphicsEffect(shadow)

    def is_compact(self) -> bool:
        return self._compact
