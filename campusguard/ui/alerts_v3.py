"""Alerts (v3): how staff are notified, then the alert history of this server and its peers."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from campusguard.storage import Repository
from campusguard.ui.incidents_v3 import when
from campusguard.ui.v3widgets import clear_layout, GhostButton, GlassCard, Meter, Switch, card_title, make_pill, mono_label

CHANNELS = (
    ("alert_sound_toggle", "Alarm sound on this computer"),
    ("auto_open_whatsapp_toggle", "Open WhatsApp automatically for Critical alerts"),
    ("ntfy_attach_toggle", "Attach the video clip to push alerts"),
)


class AlertsPage(QWidget):
    clear_all_requested = Signal()
    channel_toggled = Signal(str, bool)
    test_alert_requested = Signal()
    phone_settings_requested = Signal()
    review_requested = Signal(str)

    def __init__(self, repository: Repository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self._key = None
        self._switches: dict[str, Switch] = {}

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        host = QWidget()
        scroll.setWidget(host)
        root = QVBoxLayout(host)
        root.setContentsMargins(4, 4, 8, 24)
        root.setSpacing(16)

        # ---- channels
        channels = GlassCard()
        c = QVBoxLayout(channels)
        c.setContentsMargins(20, 18, 20, 18)
        c.setSpacing(0)
        c.addWidget(card_title("Notification channels"))
        c.addSpacing(10)
        for key, label in CHANNELS:
            row = QFrame()
            row.setObjectName("incidentRow")
            r = QHBoxLayout(row)
            r.setContentsMargins(0, 12, 0, 12)
            r.addWidget(QLabel(label), 1)
            state = mono_label("Off", point=9)
            switch = Switch(False)
            switch.toggled.connect(lambda on, k=key, s=state: (s.setText("On" if on else "Off"), self.channel_toggled.emit(k, on)))
            self._switches[key] = switch
            r.addWidget(state)
            r.addWidget(switch)
            self._states = getattr(self, "_states", {})
            self._states[key] = state
            c.addWidget(row)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 12, 0, 0)
        test = GhostButton("Send test alert", primary=True)
        test.clicked.connect(self.test_alert_requested.emit)
        phone = GhostButton("Phone alert settings")
        phone.clicked.connect(self.phone_settings_requested.emit)
        buttons.addWidget(test)
        buttons.addWidget(phone)
        buttons.addStretch(1)
        c.addLayout(buttons)
        root.addWidget(channels)

        # ---- history
        history = GlassCard()
        h = QVBoxLayout(history)
        h.setContentsMargins(20, 18, 20, 18)
        h.setSpacing(0)
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(card_title("Alert history"))
        self.count_label = mono_label("", point=9)
        head.addWidget(self.count_label)
        head.addStretch(1)
        clear = GhostButton("Clear all")
        clear.clicked.connect(self.clear_all_requested.emit)
        head.addWidget(clear)
        h.addLayout(head)
        h.addSpacing(8)
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(0)
        h.addLayout(self.rows_layout)
        root.addWidget(history)
        root.addStretch(1)
        self.refresh()

    def set_channel_states(self, states: dict[str, bool]) -> None:
        for key, value in states.items():
            switch = self._switches.get(key)
            if switch is not None and switch.isChecked() != bool(value):
                switch.blockSignals(True)
                switch.setChecked(bool(value))
                switch.blockSignals(False)
                switch._t = 1.0 if value else 0.0
                switch.update()
            if key in self._states:
                self._states[key].setText("On" if value else "Off")

    def refresh(self) -> None:
        local = self.repository.list_alerts(limit=60)
        remote = self.repository.list_remote_alerts(limit=60)
        key = (
            tuple((a["alert_id"], a["acknowledged"], a.get("status")) for a in local),
            tuple((a["id"], a.get("status")) for a in remote),
        )
        if key == self._key:
            return
        self._key = key
        clear_layout(self.rows_layout)
        active = sum(1 for a in local if not a["acknowledged"])
        self.count_label.setText(f"{active} active · {len(local) + len(remote)} total")
        rows = [("local", a) for a in local] + [("remote", a) for a in remote]
        if not rows:
            empty = QLabel("No alerts yet")
            empty.setProperty("muted", True)
            empty.setContentsMargins(0, 14, 0, 0)
            self.rows_layout.addWidget(empty)
            return
        for origin, alert in rows:
            self.rows_layout.addWidget(self._row(origin, alert))

    def _row(self, origin: str, alert: dict) -> QWidget:
        frame = QFrame()
        frame.setObjectName("incidentRow")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(0, 12, 0, 12)
        lay.setSpacing(12)
        names = QVBoxLayout()
        names.setSpacing(0)
        title = QLabel(str(alert.get("camera_name", "Camera")))
        title.setStyleSheet("font-weight: 600;")
        ident = alert.get("public_id") or alert.get("source_incident_id") or ""
        names.addWidget(title)
        names.addWidget(mono_label(f"{ident} · {when(alert.get('happened_at'))}", point=8.5))
        lay.addLayout(names, 1)
        if origin == "remote":
            lay.addWidget(make_pill(str(alert.get("source_name") or "Other server")))
        severity = str(alert.get("severity", "")).capitalize()
        lay.addWidget(make_pill(severity, "new" if severity.upper() in {"HIGH", "CRITICAL"} else "plain"))
        confidence = float(alert.get("confidence") or 0)
        lay.addWidget(Meter(confidence))
        lay.addWidget(mono_label(f"{int(round(confidence * 100))}%", point=9))
        if origin == "local":
            if alert.get("acknowledged"):
                lay.addWidget(make_pill("acknowledged"))
            else:
                ack = GhostButton("Acknowledge", primary=True)
                ack.clicked.connect(lambda _=False, i=int(alert["alert_id"]): self._acknowledge(i))
                lay.addWidget(ack)
            review = GhostButton("Review")
            review.clicked.connect(lambda _=False, p=str(ident): self.review_requested.emit(p))
            lay.addWidget(review)
        return frame

    def _acknowledge(self, alert_id: int) -> None:
        self.repository.acknowledge_alert(alert_id)
        self._key = None
        self.refresh()
