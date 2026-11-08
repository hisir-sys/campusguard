"""CampusGuard navigation: single icon rail + hover-opened Home panel.

Layout (copied from the "rail + panel" reference):

* Left rail, top capsule: logo, one **Home** icon, then the four Learn icons.
* Left rail, bottom capsule: theme toggle, account, settings.
* Hovering **Home** floats a second panel out beside the rail with Dashboard,
  Cameras, Incidents, Alerts and School server, plus a camera search box at
  the bottom. The panel overlays the page, so nothing reflows.

All page / theme / login actions keep going through the same signals.
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QSizePolicy, QVBoxLayout, QWidget,
)

from campusguard.ui.brand_logo import LogoMark
from campusguard.ui.command_search import Command, search_commands
from campusguard.ui.glass_nav import AccountButton
from campusguard.ui.icons import icon_pixmap
from campusguard.ui.theme import get_palette, qcolor

RAIL_WIDTH = 68
PANEL_WIDTH = 262
GAP = 8
COMPACT_WIDTH = RAIL_WIDTH
EXPANDED_WIDTH = RAIL_WIDTH + GAP + PANEL_WIDTH
BOTTOM_CAPSULE_HEIGHT = 236

# Pages that live "inside Home".
HOME_PAGES = ("dashboard", "cameras", "incidents", "alerts", "server-viewer")
HOME_GROUPS = (
    ("OVERVIEW", (("Dashboard", "dashboard", "layout-dashboard"), ("Cameras", "cameras", "video"))),
    ("ACTIVITY", (("Incidents", "incidents", "file-warning"), ("Alerts", "alerts", "bell"))),
    ("NETWORK", (("School server", "server-viewer", "server"),)),
)
LEARN = (
    ("Services", "services", "layers"),
    ("About", "about", "info"),
    ("Tools", "tools", "wrench"),
    ("How it works", "how-it-works", "route"),
)
# Kept for code that still imports the old structure.
SECTIONS = (("HOME", tuple(i for _t, items in HOME_GROUPS for i in items)), ("LEARN", LEARN))


def _tones() -> dict[str, QColor]:
    """Colour set for the nav surfaces (light copies the reference greys)."""
    pal = get_palette()
    if pal.name == "dark":
        return {
            "outer_top": QColor(255, 255, 255, 20), "outer_bottom": QColor(255, 255, 255, 7),
            "outer_edge": QColor(255, 255, 255, 52),
            "pill_top": QColor("#1B1C20"), "pill_bottom": QColor("#0B0C0E"),
            "pill_edge": QColor(255, 255, 255, 24),
            "icon": QColor("#8D9098"), "icon_hot": QColor("#FFFFFF"),
            "tile": QColor(255, 255, 255, 30), "tile_edge": QColor(255, 255, 255, 52),
            "panel_top": QColor("#202125"), "panel_bottom": QColor("#141518"),
            "panel_edge": QColor(255, 255, 255, 40),
            "active_top": QColor(255, 255, 255, 38), "active_bottom": QColor(255, 255, 255, 14),
            "active_edge": QColor(255, 255, 255, 58),
            "caption": QColor(255, 255, 255, 56),
            "badge": QColor(255, 255, 255, 24),
        }
    return {
        "outer_top": QColor("#B6B6B6"), "outer_bottom": QColor("#9F9F9F"),
        "outer_edge": QColor(255, 255, 255, 110),
        "pill_top": QColor("#2B292C"), "pill_bottom": QColor("#1F1D20"),
        "pill_edge": QColor(0, 0, 0, 70),
        "icon": QColor("#A8A7AA"), "icon_hot": QColor("#FFFFFF"),
        "tile": QColor("#838383"), "tile_edge": QColor(255, 255, 255, 50),
        "panel_top": QColor("#B0B0B0"), "panel_bottom": QColor("#A3A3A3"),
        "panel_edge": QColor(255, 255, 255, 120),
        "active_top": QColor(218, 223, 221, 245), "active_bottom": QColor(186, 192, 190, 235),
        "active_edge": QColor(255, 255, 255, 190),
        "caption": QColor(0, 0, 0, 70),
        "badge": QColor("#D7DBDA"),
    }


def _paint_capsule(widget: QWidget, radius: float, top: QColor, bottom: QColor, edge: QColor,
                   caption: str = "", span: tuple[float, float] | None = None) -> None:
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    w, h = float(widget.width()), float(widget.height())
    rect = QRectF(.5, .5, w - 1, h - 1)
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    fill = QLinearGradient(0, 0, 0, h)
    fill.setColorAt(0, top)
    fill.setColorAt(1, bottom)
    painter.fillPath(path, fill)
    painter.setPen(QPen(edge, 1.2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    if caption:
        painter.save()
        font = QFont(widget.font())
        font.setPointSizeF(6.5)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.2)
        painter.setFont(font)
        painter.setPen(_tones()["caption"])
        y0, y1 = span if span else (0.0, h)
        painter.translate(w / 2.0, (y0 + y1) / 2.0)
        painter.rotate(-90)
        length = max(10.0, y1 - y0)
        painter.drawText(QRectF(-length / 2.0, -9, length, 18), int(Qt.AlignmentFlag.AlignCenter), caption)
        painter.restore()


class _Capsule(QFrame):
    """Light outer capsule that holds a dark pill."""

    def __init__(self, caption: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._caption = caption
        self.pill: QWidget | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, event) -> None:
        t = _tones()
        span = None
        if self.pill is not None:
            g = self.pill.geometry()
            if g.top() > self.height() / 2:  # pill at the bottom: caption above it
                span = (14.0, g.top() - 10.0)
            else:  # pill at the top: caption below it
                span = (g.bottom() + 14.0, self.height() - 16.0)
        _paint_capsule(self, 31, t["outer_top"], t["outer_bottom"], t["outer_edge"], self._caption, span)


class _Pill(QFrame):
    """The dark icon pill inside a capsule."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, event) -> None:
        t = _tones()
        _paint_capsule(self, 24, t["pill_top"], t["pill_bottom"], t["pill_edge"])


class _Panel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, event) -> None:
        t = _tones()
        pal = get_palette()
        _paint_capsule(self, 28, t["panel_top"], t["panel_bottom"], t["panel_edge"])
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        glow = QRadialGradient(QPointF(self.width() * .5, 0), max(self.width(), 120))
        glow.setColorAt(0, qcolor(pal.ink, 22 if pal.name == "dark" else 0))
        glow.setColorAt(1, qcolor(pal.ink, 0))
        path = QPainterPath()
        path.addRoundedRect(QRectF(.5, .5, self.width() - 1, self.height() - 1), 28, 28)
        painter.fillPath(path, glow)


class _RailButton(QAbstractButton):
    """Icon (or avatar letter) button that sits on a dark pill."""

    entered = Signal()

    def __init__(self, label: str, icon: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon = icon
        self._letter = ""
        self._active = False
        self._hover = False
        self._badge = 0
        self.setFixedSize(RAIL_WIDTH - 24, 42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setToolTip(label)

    def set_icon(self, icon: str) -> None:
        self._icon = icon
        self.update()

    def set_letter(self, letter: str) -> None:
        self._letter = letter
        self.update()

    def set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    def set_badge(self, count: int) -> None:
        self._badge = max(0, int(count))
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        self.entered.emit()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        t = _tones()
        pal = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = float(self.width()), float(self.height())
        body = QRectF(.5, .5, w - 1, h - 1)
        if self._active or self._hover:
            painter.setPen(QPen(t["tile_edge"], 1))
            painter.setBrush(t["tile"] if self._active else QColor(255, 255, 255, 18))
            painter.drawRoundedRect(body, 14, 14)
        tint = t["icon_hot"] if (self._active or self._hover) else t["icon"]
        if self._letter:
            painter.setPen(QPen(tint, 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            circle = QRectF((w - 26) / 2, (h - 26) / 2, 26, 26)
            painter.drawEllipse(circle)
            font = QFont(self.font())
            font.setPointSizeF(9.5)
            font.setWeight(QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(circle, int(Qt.AlignmentFlag.AlignCenter), self._letter)
        else:
            size = 20
            painter.drawPixmap(QPointF((w - size) / 2, (h - size) / 2), icon_pixmap(self._icon, size, tint.name()))
        if self._badge:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(pal.bad))
            painter.drawEllipse(QRectF(w - 15, 5, 9, 9))


class _PanelItem(QAbstractButton):
    def __init__(self, label: str, icon: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label, self._icon = label, icon
        self._active = self._hover = False
        self._badge = 0
        self._count: int | None = None
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    def set_badge(self, count: int) -> None:
        self._badge = max(0, int(count))
        self._count = self._badge
        self.update()

    def set_count(self, count: int | None) -> None:
        self._count = count
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(PANEL_WIDTH - 28, 40)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        t = _tones()
        pal = get_palette()
        dark = pal.name == "dark"
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = float(self.width()), float(self.height())
        body = QRectF(1.5, 1.0, w - 3, h - 4)
        if self._active:
            if not dark:  # soft drop shadow under the raised frosted pill
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 0, 0, 28))
                painter.drawRoundedRect(body.translated(0, 2.2), 13, 13)
            fill = QLinearGradient(0, 0, 0, h)
            fill.setColorAt(0, t["active_top"])
            fill.setColorAt(1, t["active_bottom"])
            painter.setPen(QPen(t["active_edge"], 1))
            painter.setBrush(fill)
            painter.drawRoundedRect(body, 13, 13)
            if dark:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(qcolor(pal.ink))
                painter.drawRoundedRect(QRectF(0, h * .28, 3, h * .44), 1.5, 1.5)
        elif self._hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 14) if dark else QColor(255, 255, 255, 110))
            painter.drawRoundedRect(body, 13, 13)
        tint = pal.ink if (self._active and dark) else (pal.text if (self._active or self._hover) else pal.text_dim)
        painter.drawPixmap(QPointF(14, (h - 19) / 2 - 1), icon_pixmap(self._icon, 19, tint))
        font = QFont(self.font())
        font.setPointSizeF(10.0)
        font.setWeight(QFont.Weight.DemiBold if self._active else QFont.Weight.Medium)
        painter.setFont(font)
        painter.setPen(QColor(pal.text if (self._active or self._hover) else pal.text_dim))
        rect = QRectF(46, 0, w - 46 - 44, h - 2)
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), self._label)
        if self._count is None:
            return
        # count chip on the right, like the reference
        chip = QRectF(w - 34, (h - 2 - 20) / 2, 22, 20)
        alerting = self._label == "Alerts" and self._count > 0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(pal.bad, 235) if alerting else t["badge"])
        painter.drawRoundedRect(chip, 10, 10)
        small = QFont(self.font())
        small.setPointSizeF(7.5)
        small.setWeight(QFont.Weight.Bold)
        painter.setFont(small)
        painter.setPen(QColor("#FFFFFF") if alerting else QColor(pal.text_dim))
        painter.drawText(chip, int(Qt.AlignmentFlag.AlignCenter), "99+" if self._count > 99 else str(self._count))


class _Divider(QWidget):
    def __init__(self, text: str = "") -> None:
        super().__init__()
        self._text = text
        self.setFixedHeight(30 if text else 12)

    def paintEvent(self, event) -> None:
        pal = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        painter.setPen(QPen(qcolor(pal.text, 26), 1))
        if not self._text:
            painter.drawLine(QPointF(4, h / 2), QPointF(w - 4, h / 2))
            return
        font = QFont(self.font())
        font.setPointSizeF(8.0)
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        painter.setPen(QColor(pal.muted))
        painter.drawText(QRectF(6, 6, w - 12, h - 6), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                         self._text.title())


class _SearchEdit(QLineEdit):
    """Search box whose Up/Down keys move through the result list."""
    step = Signal(int)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Down:
            self.step.emit(1)
        elif event.key() == Qt.Key.Key_Up:
            self.step.emit(-1)
        else:
            super().keyPressEvent(event)


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
        self._commands: list[Command] = []
        self._hover_open = True
        self._dark = True
        self._cameras: list = []
        self._items: dict[str, list] = {}

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(GAP)

        # ---------------- rail ------------------------------------------
        rail_col = QVBoxLayout()
        rail_col.setContentsMargins(0, 0, 0, 0)
        rail_col.setSpacing(GAP)

        self.rail = _Capsule("CAMPUSGUARD NAV")
        self.rail.setFixedWidth(RAIL_WIDTH)
        rail_layout = QVBoxLayout(self.rail)
        rail_layout.setContentsMargins(7, 7, 7, 14)
        self.nav_pill = _Pill()
        pill = QVBoxLayout(self.nav_pill)
        pill.setContentsMargins(5, 10, 5, 10)
        pill.setSpacing(4)
        self.logo = LogoMark(size=28, tint="#EEF0F3")
        self.logo.setToolTip("CampusGuard")
        pill.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignHCenter)
        pill.addSpacing(6)
        self.home_button = _RailButton("Home", "home")
        self.home_button.entered.connect(self._open_panel)
        self.home_button.clicked.connect(lambda _c=False: self.page_requested.emit("dashboard"))
        self._register("home", self.home_button)
        pill.addWidget(self.home_button)
        pill.addSpacing(4)
        for text, key, icon in LEARN:
            button = _RailButton(text, icon)
            button.entered.connect(self._close_panel)
            button.clicked.connect(lambda _c=False, target=key: self.page_requested.emit(target))
            self._register(key, button)
            pill.addWidget(button)
        self.rail.pill = self.nav_pill
        rail_layout.addWidget(self.nav_pill, 0, Qt.AlignmentFlag.AlignTop)
        rail_layout.addStretch(1)
        rail_col.addWidget(self.rail, 1)

        self.rail_bottom = _Capsule("")
        self.rail_bottom.setFixedSize(RAIL_WIDTH, BOTTOM_CAPSULE_HEIGHT)
        bottom_layout = QVBoxLayout(self.rail_bottom)
        bottom_layout.setContentsMargins(7, 7, 7, 7)
        bottom_layout.addStretch(1)
        self.tools_pill = _Pill()
        tools = QVBoxLayout(self.tools_pill)
        tools.setContentsMargins(5, 8, 5, 8)
        tools.setSpacing(4)
        self.theme_toggle = _RailButton("Switch light / dark theme", "sun")
        self.theme_toggle.entered.connect(self._close_panel)
        self.theme_toggle.clicked.connect(lambda _c=False: self.theme_toggle_requested.emit())
        tools.addWidget(self.theme_toggle)
        self.rail_account = _RailButton("Sign in", "")
        self.rail_account.set_letter("?")
        self.rail_account.entered.connect(self._close_panel)
        self.rail_account.clicked.connect(lambda _c=False: self.login_requested.emit())
        tools.addWidget(self.rail_account)
        self.settings_button = _RailButton("System settings", "settings")
        self.settings_button.entered.connect(self._close_panel)
        self.settings_button.clicked.connect(lambda _c=False: self.page_requested.emit("settings"))
        self._register("settings", self.settings_button)
        tools.addWidget(self.settings_button)
        self.rail_bottom.pill = self.tools_pill
        bottom_layout.addWidget(self.tools_pill)
        rail_col.addWidget(self.rail_bottom, 0)
        outer.addLayout(rail_col, 0)

        # ---------------- Home panel --------------------------------------
        self.panel = _Panel()
        self.panel.setFixedWidth(PANEL_WIDTH)
        panel = QVBoxLayout(self.panel)
        panel.setContentsMargins(14, 16, 14, 14)
        panel.setSpacing(2)

        self.account_button = AccountButton()
        self.account_button.clicked.connect(lambda _c=False: self.login_requested.emit())
        panel.addWidget(self.account_button)
        panel.addSpacing(4)

        for index, (title, items) in enumerate(HOME_GROUPS):
            panel.addWidget(_Divider(title if index == 0 else ""))
            for text, key, icon in items:
                item = _PanelItem(text, icon)
                item.clicked.connect(lambda _c=False, target=key: self.page_requested.emit(target))
                self._register(key, item)
                panel.addWidget(item)
        panel.addStretch(1)

        panel.addWidget(_Divider("Search"))
        self.camera_search = _SearchEdit()
        self.camera_search.setPlaceholderText("Search cameras, pages, settings")
        self.camera_search.setClearButtonEnabled(True)
        self.camera_search.setFixedHeight(38)
        self.camera_search.textChanged.connect(self._filter_cameras)
        self.camera_search.returnPressed.connect(self._submit_search)
        self.camera_search.step.connect(self._step_results)
        panel.addWidget(self.camera_search)
        panel.addSpacing(4)
        self.camera_results = QListWidget()
        self.camera_results.setObjectName("sidebarCameraResults")
        self.camera_results.setFrameShape(QFrame.Shape.NoFrame)
        self.camera_results.setFixedHeight(150)
        self.camera_results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.camera_results.itemClicked.connect(self._open_camera_result)
        panel.addWidget(self.camera_results)
        for item in self._items.get("alerts", []):
            if isinstance(item, _PanelItem):
                item.set_count(0)
        self.panel.hide()
        self.panel.setFixedWidth(0)
        outer.addWidget(self.panel, 0)

        self.login_button = self.account_button
        self.search = self.camera_search
        self.brand_name = QLabel("")
        self.brand_tag = QLabel("")
        self.setFixedWidth(COMPACT_WIDTH)
        self._width_animation = QVariantAnimation(self)
        self._width_animation.setDuration(270)
        self._width_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._width_animation.valueChanged.connect(lambda value: self.setFixedWidth(int(value)))
        self._panel_width_animation = QVariantAnimation(self)
        self._panel_width_animation.setDuration(240)
        self._panel_width_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._panel_width_animation.valueChanged.connect(
            lambda value: self.panel.setFixedWidth(int(value))
        )
        self._panel_width_animation.finished.connect(self._finish_panel_transition)
        self._filter_cameras("")

    # ----- internals ----------------------------------------------------
    def _register(self, key: str, widget) -> None:
        self._items.setdefault(key, []).append(widget)

    def set_hover_open(self, enabled: bool) -> None:
        self._hover_open = bool(enabled)

    def _open_panel(self) -> None:
        if self._hover_open:
            self.set_compact(False)

    def _close_panel(self) -> None:
        if not self.camera_search.hasFocus():
            self.set_compact(True)

    def leaveEvent(self, event) -> None:
        self._close_panel()
        super().leaveEvent(event)

    def set_commands(self, commands: list[Command]) -> None:
        self._commands = list(commands)
        self._filter_cameras(self.camera_search.text())

    def _filter_cameras(self, query: str) -> None:
        needle = query.casefold().strip()
        self.camera_results.clear()
        for camera in self._cameras:
            haystack = f"{camera.name} {camera.camera_id} {camera.source_address}".casefold()
            if not needle or needle in haystack:
                item = QListWidgetItem(camera.name)
                item.setData(Qt.ItemDataRole.UserRole, ("camera", str(camera.camera_id)))
                item.setToolTip(f"{camera.name} · {camera.camera_id}")
                self.camera_results.addItem(item)
        for index, command in enumerate(search_commands(self._commands, needle)):
            item = QListWidgetItem(f"{command.title}  ·  {command.group}")
            item.setData(Qt.ItemDataRole.UserRole, ("command", index, command))
            self.camera_results.addItem(item)
        if self.camera_results.count() == 0:
            hint = QListWidgetItem("No cameras yet" if not self._cameras and not needle else "No match - Enter searches incidents")
            hint.setFlags(Qt.ItemFlag.NoItemFlags)
            self.camera_results.addItem(hint)
        elif needle:
            self.camera_results.setCurrentRow(0)

    def _step_results(self, delta: int) -> None:
        count = self.camera_results.count()
        if not count:
            return
        row = max(0, min(count - 1, self.camera_results.currentRow() + delta))
        self.camera_results.setCurrentRow(row)

    def _run_result(self, data) -> bool:
        if not data:
            return False
        if data[0] == "camera":
            self.camera_selected.emit(data[1])
        else:
            data[2].run()
        return True

    def _submit_search(self) -> None:
        """Enter: empty -> Cameras page; match -> that camera / command; else search incidents."""
        text = self.camera_search.text().strip()
        if not text:
            self.page_requested.emit("cameras")
            return
        current = self.camera_results.currentItem()
        data = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        if self._run_result(data):
            self.camera_search.clear()
            self.camera_search.clearFocus()
            return
        self.search_submitted.emit(text)

    def _open_camera_result(self, item: QListWidgetItem) -> None:
        if self._run_result(item.data(Qt.ItemDataRole.UserRole)):
            self.camera_search.clear()

    def _apply_shadow(self) -> None:
        # A drop shadow is clipped at the widget edge and leaves a hard strip.
        self.panel.setGraphicsEffect(None)

    # ----- API used by the main window ---------------------------------
    def set_cameras(self, cameras) -> None:
        self._cameras = list(cameras)
        for item in self._items.get("cameras", []):
            if isinstance(item, _PanelItem):
                item.set_count(len(self._cameras))
        self._filter_cameras(self.camera_search.text())

    def set_active(self, page: str) -> None:
        in_home = page in HOME_PAGES
        for key, widgets in self._items.items():
            for widget in widgets:
                if key == "home":
                    widget.set_active(in_home)
                else:
                    widget.set_active(key == page)

    def set_badge(self, key: str, count: int) -> None:
        for widget in self._items.get(key, []):
            widget.set_badge(count)
        if key in HOME_PAGES:
            total = sum(
                getattr(w, "_badge", 0)
                for k in ("alerts",)
                for w in self._items.get(k, [])
                if isinstance(w, _PanelItem)
            )
            self.home_button.set_badge(total)

    def set_theme(self, theme: str) -> None:
        self._dark = theme == "dark"
        self.theme_toggle.set_icon("sun" if self._dark else "moon")
        self.theme_toggle.setToolTip("Switch to light mode" if self._dark else "Switch to dark mode")
        self.logo.update()
        for widget in (self.rail, self.rail_bottom, self.nav_pill, self.tools_pill, self.panel):
            widget.update()
        self._apply_shadow()

    def set_operator(self, name: str | None) -> None:
        tip = f"Signed in as {name}. Click to log out." if name else "Sign in with your CampusGuard account."
        self.account_button.set_email(name)
        self.account_button.setToolTip(tip)
        self.rail_account.set_letter((name or "?")[:1].upper())
        self.rail_account.setToolTip(tip)

    def focus_search(self) -> None:
        self.set_compact(False)
        self.camera_search.setFocus()
        self.camera_search.selectAll()

    def toggle_compact(self) -> None:
        self.set_compact(not self._compact)

    def set_compact(self, compact: bool) -> None:
        compact = bool(compact)
        target_width = COMPACT_WIDTH if compact else EXPANDED_WIDTH
        if compact == self._compact and self.width() == target_width:
            return
        self._compact = compact
        self._apply_shadow()
        if compact:
            self.camera_search.clearFocus()
        else:
            self.panel.show()
            self.panel.raise_()

        self._width_animation.stop()
        self._width_animation.setStartValue(self.width())
        self._width_animation.setEndValue(target_width)
        self._width_animation.start()

        self._panel_width_animation.stop()
        self._panel_width_animation.setStartValue(self.panel.width())
        self._panel_width_animation.setEndValue(0 if compact else PANEL_WIDTH)
        self._panel_width_animation.start()

    def _finish_panel_transition(self) -> None:
        if self._compact and self.panel.width() <= 1:
            self.panel.hide()

    def is_compact(self) -> bool:
        return self._compact
