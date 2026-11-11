"""Services (v3): what CampusGuard keeps running, with the controls that exist, plus start-up."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from campusguard import autostart
from campusguard.ui.v3widgets import GhostButton, GlassCard, Switch, card_title, make_pill, mono_label


class _Row(QFrame):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.setObjectName("incidentRow")
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(0, 12, 0, 12)
        self.lay.setSpacing(12)
        self.name = QLabel(name)
        self.name.setStyleSheet("font-weight: 600;")
        self.pill = make_pill("")
        self.detail = mono_label("", point=9)
        self.detail.setMinimumWidth(180)
        self.detail.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lay.addWidget(self.name, 1)
        self.lay.addWidget(self.detail)
        self.lay.addWidget(self.pill)

    def set_state(self, running: bool, label: str, detail: str) -> None:
        self.pill.setText(label)
        self.pill.setProperty("v3pill", "up" if running else "plain")
        self.pill.style().unpolish(self.pill)
        self.pill.style().polish(self.pill)
        self.detail.setText(detail)


class ServicesPage(QWidget):
    detection_toggled = Signal(bool)
    reconnect_all_requested = Signal()
    clear_footage_requested = Signal()
    connection_settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 8, 24)
        root.setSpacing(16)
        card = GlassCard()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(0)
        head = QHBoxLayout()
        head.addWidget(card_title("Background services"))
        head.addStretch(1)
        self.summary = mono_label("", point=9)
        head.addWidget(self.summary)
        lay.addLayout(head)
        lay.addSpacing(8)

        self.detection_row = _Row("Detection engine")
        self.detection_button = GhostButton("Pause", primary=True)
        self.detection_button.clicked.connect(self._toggle_detection)
        self.detection_row.lay.addWidget(self.detection_button)
        self._detection_on = True

        self.ingest_row = _Row("Camera connections")
        reconnect = GhostButton("Reconnect all")
        reconnect.clicked.connect(self.reconnect_all_requested.emit)
        self.ingest_row.lay.addWidget(reconnect)

        self.link_row = _Row("School server link")
        link = GhostButton("Open settings")
        link.clicked.connect(self.connection_settings_requested.emit)
        self.link_row.lay.addWidget(link)

        self.storage_row = _Row("Footage storage")
        clear = GhostButton("Clear footage")
        clear.clicked.connect(self.clear_footage_requested.emit)
        self.storage_row.lay.addWidget(clear)

        for row in (self.detection_row, self.ingest_row, self.link_row, self.storage_row):
            lay.addWidget(row)
        root.addWidget(card)

        startup = GlassCard()
        s = QVBoxLayout(startup)
        s.setContentsMargins(20, 18, 20, 18)
        s.setSpacing(0)
        s.addWidget(card_title("Startup"))
        s.addSpacing(8)
        row = QFrame()
        row.setObjectName("incidentRow")
        r = QHBoxLayout(row)
        r.setContentsMargins(0, 12, 0, 12)
        self.autostart_label = QLabel("Start CampusGuard when Windows starts")
        self.autostart_state = mono_label("Off", point=9)
        self.autostart_switch = Switch(autostart.is_enabled())
        self.autostart_switch.setEnabled(autostart.supported())
        self.autostart_switch.toggled.connect(self._autostart_changed)
        self.autostart_state.setText("On" if self.autostart_switch.isChecked() else "Off")
        r.addWidget(self.autostart_label, 1)
        r.addWidget(self.autostart_state)
        r.addWidget(self.autostart_switch)
        s.addWidget(row)
        if not autostart.supported():
            note = mono_label("Available on Windows only", point=8.5)
            s.addWidget(note)
        root.addWidget(startup)
        root.addStretch(1)

    def _autostart_changed(self, on: bool) -> None:
        if not autostart.set_enabled(on):
            self.autostart_switch.blockSignals(True)
            self.autostart_switch.setChecked(autostart.is_enabled())
            self.autostart_switch.blockSignals(False)
            on = self.autostart_switch.isChecked()
        self.autostart_state.setText("On" if on else "Off")

    def _toggle_detection(self) -> None:
        self.detection_toggled.emit(not self._detection_on)

    def update_state(self, detection_on: bool, live: int, total: int, mode: str, server: str, clips: int, megabytes: float) -> None:
        self._detection_on = detection_on
        self.detection_row.set_state(detection_on, "Running" if detection_on else "Paused", f"{total} camera{'' if total == 1 else 's'} watched" if detection_on else "no detection")
        self.detection_button.setText("Pause" if detection_on else "Resume")
        self.ingest_row.set_state(live == total and total > 0, "Running" if live else "Stopped", f"{live} of {total} live")
        remote = mode != "local"
        self.link_row.set_state(remote, "Connected" if remote else "Local only", server if remote else "this computer")
        self.storage_row.set_state(clips > 0, f"{clips} clip{'' if clips == 1 else 's'}", f"{megabytes:,.0f} MB used")
        running = sum([detection_on, live > 0, remote])
        self.summary.setText(f"{running} of 3 running")
