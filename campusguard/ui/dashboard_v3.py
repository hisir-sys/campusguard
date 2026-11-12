"""Dashboard (v3): stat cards, incidents chart, detection engine, live cameras, recent incidents."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from campusguard.settings import CameraConfig, CameraStats
from campusguard.storage import Repository
from campusguard.ui.common import CameraPreview
from campusguard.ui.v3widgets import (
    BarChart, clear_layout, GhostButton, GlassCard, Meter, Orb, Segmented, card_title, make_pill, mono_label,
)

_CLOSED = {"RESOLVED", "DISMISSED", "FALSE_ALARM", "CONFIRMED"}


def _parse(value: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def bucket_incidents(rows: list[dict], span: str, now: datetime | None = None) -> list[tuple[str, int]]:
    """Counts per bucket for the chart. 24h -> 8 x 3h, 7d -> 7 days, 30d -> 10 x 3 days (oldest first)."""
    now = (now or datetime.now(timezone.utc)).astimezone()
    if span == "24h":
        count, step, label = 8, timedelta(hours=3), "%H:00"
    elif span == "30d":
        count, step, label = 10, timedelta(days=3), "%d %b"
    else:
        count, step, label = 7, timedelta(days=1), "%a"
    edges = [now - step * (count - i) for i in range(count + 1)]
    counts = [0] * count
    for row in rows:
        moment = _parse(row.get("happened_at"))
        if moment is None:
            continue
        moment = moment.astimezone()
        for i in range(count):
            if edges[i] < moment <= edges[i + 1]:
                counts[i] += 1
                break
    return [(edges[i + 1].strftime(label), counts[i]) for i in range(count)]


def week_totals(rows: list[dict], now: datetime | None = None) -> tuple[int, int]:
    """(incidents in the last 7 days, incidents in the 7 days before)."""
    now = now or datetime.now(timezone.utc)
    this_week = previous = 0
    for row in rows:
        moment = _parse(row.get("happened_at"))
        if moment is None:
            continue
        age = now - moment
        if age <= timedelta(days=7):
            this_week += 1
        elif age <= timedelta(days=14):
            previous += 1
    return this_week, previous


class DashboardPage(QWidget):
    camera_selected = Signal(str)
    view_alerts_requested = Signal()
    report_requested = Signal()
    clear_notifications_requested = Signal()
    status_change_requested = Signal(str, str)

    def __init__(self, repository: Repository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self._closing = False
        self._cameras: dict[str, CameraConfig] = {}
        self._stats: dict[str, CameraStats] = {}
        self._ai_states: dict[str, tuple[str, float | None]] = {}
        self._model_statuses: dict[str, dict[str, str]] = {}
        self._tiles: dict[str, CameraPreview] = {}
        self._offline_tiles: list[QFrame] = []
        self._runtime_loaded: dict[str, bool] = {}
        self._runtime_messages: dict[str, str] = {}
        self._device_text: str | None = None
        self._settings = None
        self._rows: list[dict] = []
        self._incident_key = None
        self._selected_camera: str | None = None
        self._event_filter_targets: dict = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("dashboardWorkspaceScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        self.dashboard_scroll = scroll
        content = QWidget()
        content.setObjectName("dashboardContent")
        scroll.setWidget(content)
        outer.addWidget(scroll)
        root = QVBoxLayout(content)
        root.setContentsMargins(4, 4, 8, 28)
        root.setSpacing(16)

        # ---- row 1: stat cards --------------------------------------------------
        top = QHBoxLayout()
        top.setSpacing(16)
        self._hero = self._build_hero()
        self._online_card, self.online_value, self.online_sub = self._build_stat("Cameras online")
        self._open_card, self.incident_value, self.open_sub = self._build_stat("Open incidents")
        top.addWidget(self._hero, 5)
        top.addWidget(self._online_card, 2)
        top.addWidget(self._open_card, 2)
        root.addLayout(top)

        # ---- row 2: chart + engine ----------------------------------------------
        mid = QHBoxLayout()
        mid.setSpacing(16)
        self._chart_card = self._build_chart()
        self._engine_card = self._build_engine()
        mid.addWidget(self._chart_card, 5)
        mid.addWidget(self._engine_card, 3)
        root.addLayout(mid)

        # ---- row 3: live cameras + recent incidents -----------------------------
        bottom = QHBoxLayout()
        bottom.setSpacing(16)
        self._network_card = self._build_network()
        self._recent_card = self._build_recent()
        bottom.addWidget(self._network_card, 5)
        bottom.addWidget(self._recent_card, 3)
        root.addLayout(bottom)
        root.addStretch(1)

        self._stats_card = self._online_card  # kept for older callers
        self._render_chart()
        self.sync_cameras([])

    # ------------------------------------------------------------------ build
    def _build_hero(self) -> GlassCard:
        card = GlassCard()
        card.setMinimumHeight(176)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(4)
        label = QLabel("Incidents this week")
        label.setProperty("muted", True)
        lay.addWidget(label)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.week_value = QLabel("0")
        self.week_value.setObjectName("heroNumber")
        self.week_delta = make_pill("vs last week", "up")
        row.addWidget(self.week_value, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.week_delta, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        report = GhostButton("See report  →")
        report.clicked.connect(self.report_requested.emit)
        line = QHBoxLayout()
        line.addWidget(report)
        line.addStretch(1)
        lay.addLayout(line)
        return card

    def _build_stat(self, title: str) -> tuple[GlassCard, QLabel, QLabel]:
        card = GlassCard()
        card.setMinimumHeight(176)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(2)
        label = QLabel(title)
        label.setProperty("muted", True)
        value = QLabel("0")
        value.setObjectName("statNumber")
        sub = mono_label("", point=9)
        lay.addWidget(label)
        lay.addWidget(value)
        lay.addWidget(sub)
        lay.addStretch(1)
        return card, value, sub

    def _build_chart(self) -> GlassCard:
        card = GlassCard()
        card.setMinimumHeight(380)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(card_title("Incidents over time"))
        head.addStretch(1)
        self.span_tabs = Segmented(["24h", "7d", "30d"], "7d")
        self.span_tabs.changed.connect(lambda _s: self._render_chart())
        head.addWidget(self.span_tabs)
        lay.addLayout(head)
        self.chart = BarChart()
        lay.addWidget(self.chart, 1)
        return card

    def _build_engine(self) -> GlassCard:
        card = GlassCard()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(8)
        title = card_title("Detection engine")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        lay.addStretch(1)
        self.orb = Orb()
        lay.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignHCenter)
        self.engine_headline = QLabel("Watching 0 cameras")
        self.engine_headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.engine_headline.setStyleSheet("font-weight: 600; font-size: 11pt;")
        self.engine_sub = mono_label("Starting", point=9)
        self.engine_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.engine_sub.setWordWrap(True)
        lay.addWidget(self.engine_headline)
        lay.addWidget(self.engine_sub)
        lay.addStretch(1)
        # label/value pairs the Settings health card and tests read
        self.engine_values = {
            "violence_model": QLabel(""), "device": QLabel(""), "status": QLabel(""),
        }
        return card

    def _build_network(self) -> GlassCard:
        card = GlassCard()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(card_title("Live cameras"))
        head.addStretch(1)
        self.camera_count_pill = make_pill("0 cameras")
        head.addWidget(self.camera_count_pill)
        lay.addLayout(head)
        self.feed_content = QWidget()
        self._camera_grid = QGridLayout(self.feed_content)
        self._camera_grid.setContentsMargins(0, 0, 0, 0)
        self._camera_grid.setSpacing(12)
        self._camera_grid.setColumnStretch(0, 1)
        self._camera_grid.setColumnStretch(1, 1)
        lay.addWidget(self.feed_content, 1)
        return card

    def _build_recent(self) -> GlassCard:
        card = GlassCard()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(0)
        head = QHBoxLayout()
        head.addWidget(card_title("Recent incidents"))
        head.addStretch(1)
        all_btn = GhostButton("View all")
        all_btn.clicked.connect(self.view_alerts_requested.emit)
        head.addWidget(all_btn)
        lay.addLayout(head)
        self._recent_layout = QVBoxLayout()
        self._recent_layout.setContentsMargins(0, 8, 0, 0)
        self._recent_layout.setSpacing(0)
        lay.addLayout(self._recent_layout)
        lay.addStretch(1)
        return card

    # ------------------------------------------------------------------ data
    def _render_chart(self) -> None:
        self.chart.set_data(bucket_incidents(self._rows, self.span_tabs.current()))

    def refresh_summary(self) -> None:
        online = sum(
            self._stats.get(camera_id, CameraStats()).status == "LIVE" for camera_id in self._cameras
        )
        total = len(self._cameras)
        self.online_value.setText(f"{online} / {total}")
        self.online_sub.setText(f"{max(0, total - online)} offline")
        open_count = self.repository.open_incident_count()
        self.incident_value.setText(str(open_count))
        self._rows = self.repository.list_incidents(limit=5000)
        confidences = [
            float(r.get("confidence") or 0) for r in self._rows
            if str(r.get("status", "NEW")) not in _CLOSED
        ]
        average = int(round(100 * sum(confidences) / len(confidences))) if confidences else 0
        self.open_sub.setText(f"avg confidence {average}%" if confidences else "all clear")
        this_week, previous = week_totals(self._rows)
        self.week_value.setText(str(this_week))
        if previous:
            change = round(100 * (this_week - previous) / previous)
            arrow = "↑" if change > 0 else ("↓" if change < 0 else "→")
            self.week_delta.setText(f"{arrow} {abs(change)}% vs last week")
        else:
            self.week_delta.setText("no data last week" if not this_week else "first week")
        self._render_chart()
        self._show_recent(self._rows[:4])
        self._refresh_engine()

    def _show_recent(self, rows: list[dict]) -> None:
        key = tuple((r.get("public_id"), r.get("status"), round(float(r.get("confidence") or 0), 3)) for r in rows)
        if key == self._incident_key:
            return
        self._incident_key = key
        clear_layout(self._recent_layout)
        if not rows:
            empty = QLabel("No incidents recorded")
            empty.setProperty("muted", True)
            self._recent_layout.addWidget(empty)
            return
        for row in rows:
            self._recent_layout.addWidget(self._incident_row(row))

    def _incident_row(self, row: dict) -> QWidget:
        frame = QFrame()
        frame.setObjectName("incidentRow")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(0, 12, 0, 12)
        lay.setSpacing(12)
        names = QVBoxLayout()
        names.setSpacing(0)
        name = QLabel(str(row.get("camera_name", "Camera")))
        name.setStyleSheet("font-weight: 600;")
        moment = _parse(row.get("happened_at"))
        when = moment.astimezone().strftime("%d %b %H:%M") if moment else ""
        meta = mono_label(f"{row.get('public_id', '')} · {when}", point=8.5)
        names.addWidget(name)
        names.addWidget(meta)
        lay.addLayout(names, 1)
        confidence = float(row.get("confidence") or 0)
        meter = Meter(confidence)
        pct = mono_label(f"{int(round(confidence * 100))}%", point=9)
        lay.addWidget(meter)
        lay.addWidget(pct)
        status = str(row.get("status", "NEW"))
        public_id = str(row.get("public_id", ""))
        if status in {"NEW", "ACKNOWLEDGED"}:
            confirm = GhostButton("Confirm", primary=True)
            confirm.clicked.connect(lambda _=False, p=public_id: self._decide(p, "CONFIRMED"))
            false = GhostButton("False alarm")
            false.clicked.connect(lambda _=False, p=public_id: self._decide(p, "FALSE_ALARM"))
            lay.addWidget(confirm)
            lay.addWidget(false)
        else:
            lay.addWidget(make_pill(status.replace("_", " ").capitalize()))
        return frame

    def _decide(self, public_id: str, status: str) -> None:
        self.status_change_requested.emit(public_id, status)
        self.refresh_summary()

    # ------------------------------------------------------------------ cameras
    def sync_cameras(self, cameras: list[CameraConfig]) -> None:
        new_ids = {c.camera_id for c in cameras}
        for camera_id in set(self._tiles) - new_ids:
            tile = self._tiles.pop(camera_id)
            self._camera_grid.removeWidget(tile)
            tile.deleteLater()
            self._stats.pop(camera_id, None)
            self._ai_states.pop(camera_id, None)
            self._model_statuses.pop(camera_id, None)
        self._cameras = {c.camera_id: c for c in cameras}
        for camera in cameras:
            tile = self._tiles.get(camera.camera_id)
            if tile is None:
                tile = CameraPreview(camera)
                tile.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                tile.setMinimumWidth(0)
                tile.selected.connect(self.camera_selected.emit)
                self._tiles[camera.camera_id] = tile
            else:
                tile.set_camera(camera)
            self._update_tile(camera.camera_id)
        while self._camera_grid.count():
            item = self._camera_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                if widget.objectName() == "offlineCameraTile":
                    widget.deleteLater()
                else:
                    widget.setParent(None)
        self._offline_tiles.clear()
        widgets: list[QWidget] = [self._tiles[c.camera_id] for c in cameras]
        while len(widgets) < 2:
            widgets.append(self._build_offline_tile(len(widgets) + 1))
        for index, widget in enumerate(widgets):
            self._camera_grid.addWidget(widget, index // 2, index % 2)
        count = len(cameras)
        self.camera_count_pill.setText(f"{count} camera{'' if count == 1 else 's'}")
        self._refresh_engine()

    def _build_offline_tile(self, slot: int) -> QFrame:
        tile = QFrame()
        tile.setObjectName("offlineCameraTile")
        tile.setMinimumHeight(200)
        lay = QVBoxLayout(tile)
        lay.setContentsMargins(0, 0, 0, 0)
        surface = QLabel(f"Camera {slot}\nNo signal")
        surface.setAlignment(Qt.AlignmentFlag.AlignCenter)
        surface.setProperty("videoSurface", True)
        lay.addWidget(surface)
        self._offline_tiles.append(tile)
        return tile

    def update_camera_stats(self, camera_id: str, stats: CameraStats) -> None:
        self._stats[camera_id] = stats
        self._update_tile(camera_id)

    def update_frame(self, camera_id: str, image, state: str, confidence: float | None) -> None:
        if camera_id not in self._tiles:
            return
        self._ai_states[camera_id] = (state, confidence)
        self._tiles[camera_id].set_frame(QPixmap.fromImage(image), state, confidence)

    def _update_tile(self, camera_id: str) -> None:
        camera = self._cameras.get(camera_id)
        tile = self._tiles.get(camera_id)
        if not camera or not tile:
            return
        tile.set_status(self._stats.get(camera_id, CameraStats()), camera.ai_enabled)

    # ------------------------------------------------------------------ model status
    def update_model_status(self, camera_id: str, component: str, message: str) -> None:
        self._model_statuses.setdefault(camera_id, {})[component] = message
        if component in {"detector", "pose", "fight"}:
            self._runtime_loaded[component] = any(
                str(s.get(component, "")).upper().startswith("READY") for s in self._model_statuses.values()
            )
            self._runtime_messages[component] = message
            tile = self._tiles.get(camera_id)
            if tile is not None:
                tile.set_model_status(message)
        elif component == "device":
            self._device_text = message
        self._refresh_engine()

    def update_settings(self, confidence_threshold: float, detection_enabled: bool) -> None:
        return

    def update_model_configuration(self, settings) -> None:
        self._settings = settings
        self._refresh_engine()

    def _current_model_status(self) -> tuple[str, str]:
        if self._settings is None:
            return "Waiting", "warn"
        required = ("detector", "pose", "fight")
        loaded = sum(self._runtime_loaded.get(key) is True for key in required)
        if loaded == len(required):
            return "ACTIVE", "good"
        if loaded > 0:
            return "PARTIAL", "warn"
        if self._runtime_loaded:
            return "NOT READY", "bad"
        return "READY", "good"

    def _refresh_engine(self) -> None:
        settings = self._settings
        if settings is None:
            return
        status, tone = self._current_model_status()
        watching = sum(1 for c in self._cameras.values() if c.ai_enabled)
        self.engine_headline.setText(f"Watching {watching} camera{'' if watching == 1 else 's'}")
        device = self._device_text or str(getattr(settings, "device", "auto")).upper()
        self.engine_sub.setText(f"{status.capitalize()} · {device}")
        self.engine_values["violence_model"].setText("Spontim 1.0")
        self.engine_values["device"].setText(device)
        self.engine_values["status"].setText(status)
        self.orb.set_running(status in {"ACTIVE", "READY", "PARTIAL"})

    # ------------------------------------------------------------------ lifecycle
    def retint(self) -> None:
        for widget in (self.chart, self.orb, self.span_tabs):
            widget.update()
        self._incident_key = None

    def _detach_card_event_filters(self) -> None:
        self._event_filter_targets.clear()

    def closeEvent(self, event) -> None:
        self._closing = True
        self._detach_card_event_filters()
        super().closeEvent(event)
