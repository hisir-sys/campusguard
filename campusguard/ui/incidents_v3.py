"""Incidents (v3): filterable list on the left, the selected incident on the right."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget,
)

from campusguard.storage import Repository
from campusguard.ui.history_pages import FootagePlayerDialog
from campusguard.ui.v3widgets import (
    GhostButton, GlassCard, Meter, Segmented, card_title, make_pill, mono_label,
)

NEW = {"NEW", "ACKNOWLEDGED"}
CONFIRMED = {"CONFIRMED", "RESOLVED"}
FALSE_ALARM = {"FALSE_ALARM", "DISMISSED"}
TABS = ["All", "New", "Confirmed", "False alarm"]


def tab_matches(tab: str, status: str) -> bool:
    if tab == "New":
        return status in NEW
    if tab == "Confirmed":
        return status in CONFIRMED
    if tab == "False alarm":
        return status in FALSE_ALARM
    return True


def status_label(status: str) -> str:
    if status in CONFIRMED:
        return "confirmed"
    if status in FALSE_ALARM:
        return "false alarm"
    return "new"


def when(value: str) -> str:
    try:
        return datetime.fromisoformat(str(value)).astimezone().strftime("%d %b %H:%M")
    except (TypeError, ValueError):
        return str(value)


def first_frame(path: str, width: int = 480) -> QPixmap | None:
    """First frame of the clip as a thumbnail, or None when it cannot be decoded."""
    try:
        import cv2
    except Exception:
        return None
    try:
        capture = cv2.VideoCapture(path)
        ok, frame = capture.read()
        capture.release()
        if not ok:
            return None
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, _ = frame.shape
        image = QImage(frame.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        return QPixmap.fromImage(image).scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
    except Exception:
        return None


class IncidentsPage(QWidget):
    status_change_requested = Signal(str, str)
    clear_all_requested = Signal()
    clear_footage_requested = Signal()
    whatsapp_requested = Signal(str)
    export_requested = Signal()

    def __init__(self, repository: Repository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self._rows: list[dict] = []
        self._selected: str | None = None
        self._footage_viewer: FootagePlayerDialog | None = None
        self._rendered_key = None

        root = QHBoxLayout(self)
        root.setContentsMargins(4, 4, 8, 20)
        root.setSpacing(16)

        # ---- list card
        self.list_card = GlassCard()
        lay = QVBoxLayout(self.list_card)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(card_title("Incidents"))
        self.count_label = mono_label("0", point=9)
        head.addWidget(self.count_label)
        head.addStretch(1)
        self.tabs = Segmented(TABS, "All")
        self.tabs.changed.connect(lambda _t: self.refresh())
        head.addWidget(self.tabs)
        lay.addLayout(head)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search camera, ID or event")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(lambda _t: self.refresh())
        lay.addWidget(self.search_input)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().setAutoFillBackground(False)
        self.rows_host = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_host)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(0)
        self.scroll.setWidget(self.rows_host)
        lay.addWidget(self.scroll, 1)
        foot = QHBoxLayout()
        self.export_button = GhostButton("Export CSV")
        self.export_button.clicked.connect(self.export_requested.emit)
        self.clear_footage_button = GhostButton("Clear footage")
        self.clear_footage_button.clicked.connect(self.clear_footage_requested.emit)
        self.clear_all_button = GhostButton("Clear all")
        self.clear_all_button.clicked.connect(self.clear_all_requested.emit)
        foot.addWidget(self.export_button)
        foot.addStretch(1)
        foot.addWidget(self.clear_footage_button)
        foot.addWidget(self.clear_all_button)
        lay.addLayout(foot)
        root.addWidget(self.list_card, 5)

        # ---- detail card
        self.detail = GlassCard()
        self.detail.setMinimumWidth(380)
        d = QVBoxLayout(self.detail)
        d.setContentsMargins(20, 18, 20, 18)
        d.setSpacing(10)
        self.detail_title = card_title("Select an incident")
        d.addWidget(self.detail_title)
        self.preview = QLabel("Select an incident to review its clip")
        self.preview.setProperty("videoSurface", True)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(220)
        d.addWidget(self.preview)
        play_row = QHBoxLayout()
        self.play_button = GhostButton("Play", primary=True)
        self.play_button.clicked.connect(self._play)
        self.clip_label = mono_label("", point=9)
        play_row.addWidget(self.play_button)
        play_row.addWidget(self.clip_label, 1)
        d.addLayout(play_row)
        self.meta_label = mono_label("", point=9)
        d.addWidget(self.meta_label)
        self.meter = Meter(0.0, width=200)
        d.addWidget(self.meter)
        self.status_pill = make_pill("new", "new")
        d.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignLeft)
        actions = QHBoxLayout()
        self.confirm_button = GhostButton("Confirm", primary=True)
        self.confirm_button.clicked.connect(lambda: self._decide("CONFIRMED"))
        self.false_button = GhostButton("False alarm")
        self.false_button.clicked.connect(lambda: self._decide("FALSE_ALARM"))
        self.resolve_button = GhostButton("Resolve")
        self.resolve_button.clicked.connect(lambda: self._decide("RESOLVED"))
        actions.addWidget(self.confirm_button)
        actions.addWidget(self.false_button)
        actions.addWidget(self.resolve_button)
        actions.addStretch(1)
        d.addLayout(actions)
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText("Add a note for this incident")
        self.note.setFixedHeight(86)
        d.addWidget(self.note)
        self._note_timer = QTimer(self)
        self._note_timer.setSingleShot(True)
        self._note_timer.setInterval(900)
        self._note_timer.timeout.connect(self._save_note)
        self.note.textChanged.connect(self._note_changed)
        self._loading_note = False
        tools = QHBoxLayout()
        self.whatsapp_button = GhostButton("Send on WhatsApp")
        self.whatsapp_button.clicked.connect(
            lambda: self._selected and self.whatsapp_requested.emit(self._selected)
        )
        tools.addWidget(self.whatsapp_button)
        tools.addStretch(1)
        d.addLayout(tools)
        d.addStretch(1)
        root.addWidget(self.detail, 3)
        self._show_detail(None)
        self.refresh()

    # ------------------------------------------------------------------ list
    def refresh(self) -> None:
        self._rows = self.repository.list_incidents(limit=1000)
        needle = self.search_input.text().strip().casefold()
        tab = self.tabs.current()
        shown = [
            r for r in self._rows
            if tab_matches(tab, str(r.get("status", "NEW")))
            and (not needle or needle in f"{r.get('camera_name', '')} {r.get('public_id', '')} {r.get('event', '')}".casefold())
        ]
        self.count_label.setText(f"{len(shown)} of {len(self._rows)}")
        key = (tuple((r["public_id"], r.get("status"), round(float(r.get("confidence") or 0), 3), r.get("footage_path")) for r in shown), self._selected)
        if key != self._rendered_key:
            self._rendered_key = key
            while self.rows_layout.count():
                item = self.rows_layout.takeAt(0)
                if item.widget() is not None:
                    item.widget().deleteLater()
            if not shown:
                empty = QLabel("No incidents match" if self._rows else "No incidents recorded")
                empty.setProperty("muted", True)
                empty.setContentsMargins(0, 16, 0, 0)
                self.rows_layout.addWidget(empty)
            for row in shown:
                self.rows_layout.addWidget(self._row_widget(row))
            self.rows_layout.addStretch(1)
        current = next((r for r in self._rows if r["public_id"] == self._selected), None)
        if current is None and shown:
            # Nothing chosen yet (or the chosen one is gone): show the newest listed incident.
            self._selected = str(shown[0]["public_id"])
            current = shown[0]
            self._rendered_key = None
            self.refresh()
            return
        if current is None:
            self._selected = None
        self._show_detail(current, keep_note=True)

    def _row_widget(self, row: dict) -> QWidget:
        public_id = str(row["public_id"])
        status = str(row.get("status", "NEW"))
        frame = _ClickRow(public_id == self._selected)
        frame.clicked.connect(lambda p=public_id: self.select(p))
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(0, 12, 0, 12)
        lay.setSpacing(12)
        names = QVBoxLayout()
        names.setSpacing(0)
        name = QLabel(str(row.get("camera_name", "Camera")))
        name.setStyleSheet("font-weight: 600;" + ("text-decoration: underline;" if public_id == self._selected else ""))
        names.addWidget(name)
        names.addWidget(mono_label(f"{public_id} · {when(row.get('happened_at'))}", point=8.5))
        lay.addLayout(names, 1)
        confidence = float(row.get("confidence") or 0)
        lay.addWidget(Meter(confidence))
        lay.addWidget(mono_label(f"{int(round(confidence * 100))}%", point=9))
        if status in NEW:
            confirm = GhostButton("Confirm", primary=True)
            confirm.clicked.connect(lambda _=False, p=public_id: self._set(p, "CONFIRMED"))
            false = GhostButton("False alarm")
            false.clicked.connect(lambda _=False, p=public_id: self._set(p, "FALSE_ALARM"))
            lay.addWidget(confirm)
            lay.addWidget(false)
        else:
            lay.addWidget(make_pill(status_label(status)))
        return frame

    def select(self, public_id: str) -> None:
        self._selected = public_id
        self._rendered_key = None
        self.refresh()

    # ------------------------------------------------------------------ detail
    def _show_detail(self, row: dict | None, keep_note: bool = False) -> None:
        enabled = row is not None
        for widget in (self.play_button, self.confirm_button, self.false_button, self.resolve_button,
                       self.whatsapp_button, self.note):
            widget.setEnabled(enabled)
        if row is None:
            self.detail_title.setText("Select an incident")
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Select an incident to review its clip")
            self.clip_label.setText("")
            self.meta_label.setText("")
            self.meter.set_value(0)
            self.status_pill.hide()
            return
        status = str(row.get("status", "NEW"))
        self.detail_title.setText(str(row["public_id"]))
        path = str(row.get("footage_path") or "")
        has_clip = bool(path) and Path(path).is_file()
        self.play_button.setEnabled(has_clip)
        if has_clip:
            if getattr(self, "_thumb_for", None) != path:
                self._thumb_for = path
                pixmap = first_frame(path)
                if pixmap is not None:
                    self.preview.setPixmap(pixmap.scaled(self.preview.width() or 360, 220,
                                                         Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation))
                else:
                    self.preview.setPixmap(QPixmap())
                    self.preview.setText(f"{row.get('camera_name', '')}\nClip saved")
            self.clip_label.setText(Path(path).name)
        else:
            self._thumb_for = None
            self.preview.setPixmap(QPixmap())
            self.preview.setText(f"{row.get('camera_name', '')}\nNo clip saved for this incident")
            self.clip_label.setText("no clip")
        confidence = float(row.get("confidence") or 0)
        self.meta_label.setText(f"{when(row.get('happened_at'))} · {int(round(confidence * 100))}% confidence · {row.get('severity', '')}")
        self.meter.set_value(confidence)
        self.status_pill.setText(status_label(status))
        self.status_pill.setProperty("v3pill", "new" if status in NEW else "plain")
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)
        self.status_pill.show()
        open_ = status in NEW
        self.confirm_button.setVisible(open_)
        self.false_button.setVisible(open_)
        self.resolve_button.setVisible(status == "CONFIRMED")
        if not (keep_note and self.note.hasFocus()):
            self._load_note(str(row["public_id"]))

    def _load_note(self, public_id: str) -> None:
        text = ""
        for entry in self.repository.list_audit(limit=2000):
            if entry.get("action") == "incident_note" and entry.get("target") == public_id:
                text = str(entry.get("detail") or "")
                break
        self._loading_note = True
        if self.note.toPlainText() != text:
            self.note.setPlainText(text)
        self._loading_note = False

    def _note_changed(self) -> None:
        if not self._loading_note and self._selected:
            self._note_timer.start()

    def _save_note(self) -> None:
        if self._selected:
            self.repository.log_audit("incident_note", self._selected, self.note.toPlainText().strip()[:500])

    # ------------------------------------------------------------------ actions
    def _decide(self, status: str) -> None:
        if self._selected:
            self._set(self._selected, status)

    def _set(self, public_id: str, status: str) -> None:
        self.status_change_requested.emit(public_id, status)

    def _play(self) -> None:
        row = next((r for r in self._rows if r["public_id"] == self._selected), None)
        path = str(row.get("footage_path") or "") if row else ""
        if path and Path(path).is_file():
            self._open_footage(path, str(row["public_id"]))

    def _open_footage(self, path: str, public_id: str) -> None:
        if self._footage_viewer is not None:
            self._footage_viewer.close()
            self._footage_viewer.deleteLater()
        self._footage_viewer = FootagePlayerDialog(path, f"Incident {public_id}", self.window())
        self._footage_viewer.destroyed.connect(lambda: setattr(self, "_footage_viewer", None))
        self._footage_viewer.setGeometry(self.window().rect())
        self._footage_viewer.show()
        self._footage_viewer.raise_()


class _ClickRow(QFrame):
    clicked = Signal()

    def __init__(self, selected: bool = False) -> None:
        super().__init__()
        self.setObjectName("incidentRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._selected = selected

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
