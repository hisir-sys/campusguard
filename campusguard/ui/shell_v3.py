"""v3 shell pieces: the page header with its four actions, and the Ctrl K command palette."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

from campusguard.ui.command_search import Command, search_commands
from campusguard.ui.theme import get_palette
from campusguard.ui.v3widgets import GhostButton, GlassCard, make_pill

PAGE_TITLES: dict[str, tuple[str, str]] = {
    "dashboard": ("Dashboard", "Live overview of cameras, incidents and the detection engine"),
    "cameras": ("Cameras", "Add, edit and monitor every camera"),
    "incidents": ("Incidents", "Review, confirm and export every detected fight"),
    "alerts": ("Alerts", "Alerts raised on this server and on the other servers of the school"),
    "settings": ("Settings", "Detection, alerts, appearance and connection"),
    "server-viewer": ("School server", "Cameras, incidents and alerts of the connected school server"),
    "services": ("Services", "What CampusGuard runs for the school"),
    "about": ("About", "The product, the people and the promise"),
    "tools": ("Tools", "The technology behind detection, tracking and alerts"),
    "how-it-works": ("How it works", "From camera frame to phone alert"),
}


class HeaderBar(QWidget):
    palette_requested = Signal()
    incidents_requested = Signal()
    theme_requested = Signal()
    simulate_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("headerBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 8, 0)
        lay.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title = QLabel("Dashboard")
        self.title.setObjectName("pageHeading")
        self.subtitle = QLabel("")
        self.subtitle.setProperty("muted", True)
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        lay.addLayout(titles, 1)
        self.palette_button = GhostButton("Ctrl K")
        self.palette_button.setToolTip("Search pages, settings and actions")
        self.incidents_button = GhostButton("Incidents")
        self.theme_button = GhostButton("Light / Dark")
        self.simulate_button = GhostButton("Simulate alert", primary=True)
        self.simulate_button.setToolTip("Show a sample alert. Nothing is saved and nobody is notified")
        self.badge = make_pill("0", "new")
        self.badge.hide()
        self.palette_button.clicked.connect(self.palette_requested.emit)
        self.incidents_button.clicked.connect(self.incidents_requested.emit)
        self.theme_button.clicked.connect(self.theme_requested.emit)
        self.simulate_button.clicked.connect(self.simulate_requested.emit)
        row = QHBoxLayout(self.incidents_button)
        row.setContentsMargins(0, 0, 12, 0)
        row.addStretch(1)
        row.addWidget(self.badge)
        self.incidents_button.setMinimumWidth(110)
        for button in (self.palette_button, self.incidents_button, self.theme_button, self.simulate_button):
            lay.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
        self.setFixedHeight(64)

    def set_page(self, key: str) -> None:
        title, subtitle = PAGE_TITLES.get(key, (key.title(), ""))
        self.title.setText(title)
        self.subtitle.setText(subtitle)

    def set_open_count(self, count: int) -> None:
        self.badge.setText(str(count))
        self.badge.setVisible(count > 0)


class CommandPalette(QWidget):
    """Centered search over pages, settings and actions (Ctrl K)."""

    closed = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._commands: list[Command] = []
        self._shown: list[Command] = []
        self.hide()
        self._fade = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_fade)
        self.panel = GlassCard(self, radius=20)
        self.panel.setFixedWidth(560)
        lay = QVBoxLayout(self.panel)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Search")
        self.input.textChanged.connect(self._refresh)
        self.input.installEventFilter(self)
        lay.addWidget(self.input)
        self.results = QListWidget()
        self.results.setFrameShape(QFrame.Shape.NoFrame)
        self.results.setStyleSheet("QListWidget { background: transparent; border: none; } "
                                   "QListWidget::item { padding: 9px 12px; border-radius: 10px; }")
        self.results.itemActivated.connect(lambda _i: self._run())
        self.results.itemClicked.connect(lambda _i: self._run())
        lay.addWidget(self.results)
        self.hint = QLabel("↑ ↓ to move   Enter to open   Esc to close")
        self.hint.setProperty("muted", True)
        lay.addWidget(self.hint)

    def _on_fade(self, value) -> None:
        self._fade = float(value)
        self.update()

    def set_commands(self, commands: list[Command]) -> None:
        self._commands = list(commands)

    def open_palette(self) -> None:
        self.setGeometry(self.parentWidget().rect())
        self.input.clear()
        self._refresh("")
        self.show()
        self.raise_()
        self._place()
        self._anim.stop()
        self._anim.setStartValue(self._fade)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self.input.setFocus()

    def close_palette(self) -> None:
        self.hide()
        self._fade = 0.0
        self.closed.emit()

    def _place(self) -> None:
        rows = max(1, min(8, self.results.count()))
        self.results.setFixedHeight(rows * 40 + 6)
        self.panel.adjustSize()
        self.panel.move((self.width() - self.panel.width()) // 2, max(40, self.height() // 6))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.isVisible():
            self._place()

    def _refresh(self, text: str) -> None:
        text = text.strip()
        pages = [c for c in self._commands if c.group == "Page"]
        self._shown = search_commands(self._commands, text) if text else pages[:8]
        self.results.clear()
        for command in self._shown:
            item = QListWidgetItem(f"{command.title}      {command.group}")
            self.results.addItem(item)
        if self._shown:
            self.results.setCurrentRow(0)
        if self.isVisible():
            self._place()

    def _run(self) -> None:
        row = self.results.currentRow()
        if 0 <= row < len(self._shown):
            command = self._shown[row]
            self.close_palette()
            command.run()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.input and isinstance(event, QKeyEvent) and event.type() == event.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                self.results.setCurrentRow(min(self.results.count() - 1, self.results.currentRow() + 1))
                return True
            if key == Qt.Key.Key_Up:
                self.results.setCurrentRow(max(0, self.results.currentRow() - 1))
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._run()
                return True
            if key == Qt.Key.Key_Escape:
                self.close_palette()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_palette()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        if not self.panel.geometry().contains(event.position().toPoint()):
            self.close_palette()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        dark = get_palette().name == "dark"
        scrim = QColor(0, 0, 0, int((150 if dark else 90) * self._fade))
        painter.fillRect(self.rect(), scrim)
        painter.end()
