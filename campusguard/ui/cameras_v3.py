"""Cameras (v3): a card grid with Edit, Disable/Enable, Reconnect and Remove on every camera."""
from __future__ import annotations

import time

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from campusguard.settings import SENSITIVITY_LEVELS, CameraConfig, CameraStats
from campusguard.ui.common import CameraFormDialog
from campusguard.ui.theme import get_palette
from campusguard.ui.v3widgets import GhostButton, GlassCard, is_dark, make_pill, mono_label

ONLINE = {"LIVE", "ONLINE", "CONNECTED"}
BAD = {"OFFLINE", "ERROR", "DISCONNECTED"}
CARD_MIN_WIDTH = 340


def sensitivity_label(offset: float) -> str:
    """Short name (Low / Medium / High) of the sensitivity level closest to offset."""
    best = min(SENSITIVITY_LEVELS, key=lambda level: abs(float(level[1]) - float(offset)))
    return str(best[0]).split(" ")[0].split("(")[0].strip() or str(best[0])


def card_status(camera: CameraConfig, stats: CameraStats) -> tuple[str, str]:
    """(text, tone) for the pill on a card. tone is '', 'new' (coral) or 'up'."""
    status = (stats.status or "CONNECTING").upper()
    if not camera.ai_enabled:
        return "AI off", ""
    if status in ONLINE:
        return "Live", "up"
    if status in BAD:
        return status.capitalize(), "new"
    return status.capitalize(), ""


class ElidedLabel(QLabel):
    """Single-line label that ends with an ellipsis instead of being clipped."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self._full = text
        self._elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        shown = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideMiddle, max(0, self.width() - 2))
        QLabel.setText(self, shown)


class Thumb(QWidget):
    """The live frame of a camera. Until frames arrive (or while the camera is off) it shows
    striped placeholder, dimmed when AI is off."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(128)
        self._dim = False
        self._frame: QPixmap | None = None

    def set_frame(self, frame: QPixmap | None) -> None:
        self._frame = frame
        self.update()

    def has_frame(self) -> bool:
        return self._frame is not None

    def set_dim(self, value: bool) -> None:
        self._dim = value
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        dark = is_dark()
        base = QColor(255, 255, 255, 8 if dark else 40)
        p.fillPath(path, base)
        p.save()
        p.setClipPath(path)
        if self._frame is not None:
            source = self._frame
            scale = max(self.width() / source.width(), self.height() / source.height())
            w, h = source.width() * scale, source.height() * scale
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawPixmap(QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h), source, QRectF(source.rect()))
            if self._dim:
                p.fillRect(self.rect(), QColor(0, 0, 0, 120))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 10 if dark else 70), 6))
            for x in range(-self.height(), self.width() + self.height(), 16):
                p.drawLine(x, self.height(), x + self.height(), 0)
        p.restore()
        text = QColor(get_palette().text)
        text.setAlpha(60 if self._dim else 40)
        p.setPen(QPen(text, 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 12, 12)
        p.end()


class _CardBody(GlassCard):
    open_requested = Signal(str)
    edit_requested = Signal(str)
    remove_requested = Signal(str)
    reconnect_requested = Signal(str)
    ai_changed = Signal(str, bool)

    def __init__(self, camera: CameraConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.camera = camera
        self.stats = CameraStats()
        self.setObjectName("cameraCard")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click to open the live view full screen")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        self.thumb = Thumb()
        thumb_layout = QVBoxLayout(self.thumb)
        thumb_layout.setContentsMargins(10, 10, 10, 10)
        self.name_pill = make_pill(camera.name)
        self.status_pill = make_pill("Connecting")
        thumb_layout.addWidget(self.name_pill, 0, Qt.AlignmentFlag.AlignLeft)
        thumb_layout.addStretch(1)
        thumb_layout.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignLeft)
        root.addWidget(self.thumb)

        info = QHBoxLayout()
        info.setSpacing(8)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = QLabel(camera.name)
        self.title.setStyleSheet("font-weight: 600; font-size: 13px;")
        self.meta = mono_label("", point=8.5)
        self.meta.setWordWrap(True)
        self.address = ElidedLabel()
        self.address.setFont(self.meta.font())
        self.address.setProperty("muted", True)
        self.address.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.addWidget(self.title)
        text.addWidget(self.meta)
        text.addWidget(self.address)
        info.addLayout(text, 1)
        self.toggle = GhostButton("Disable")
        self.toggle.setToolTip("Turn AI fight detection on or off for this camera")
        self.toggle.clicked.connect(lambda: self.ai_changed.emit(self.camera.camera_id, not self.camera.ai_enabled))
        info.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(info)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        edit = GhostButton("Edit")
        edit.clicked.connect(lambda: self.edit_requested.emit(self.camera.camera_id))
        reconnect = GhostButton("Reconnect")
        reconnect.clicked.connect(lambda: self.reconnect_requested.emit(self.camera.camera_id))
        remove = GhostButton("Remove")
        remove.clicked.connect(lambda: self.remove_requested.emit(self.camera.camera_id))
        for button in (edit, reconnect, remove):
            actions.addWidget(button)
        actions.addStretch(1)
        root.addLayout(actions)
        self._refresh()

    def update_camera(self, camera: CameraConfig) -> None:
        self.camera = camera
        self._refresh()

    def update_stats(self, stats: CameraStats) -> None:
        self.stats = stats
        if (stats.status or "").upper() not in ONLINE:
            self.thumb.set_frame(None)
        self._refresh()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.open_requested.emit(self.camera.camera_id)
        super().mouseReleaseEvent(event)

    def _refresh(self) -> None:
        camera = self.camera
        text, tone = card_status(camera, self.stats)
        self.name_pill.setText(camera.name)
        self.title.setText(camera.name)
        zone = camera.group_name or camera.source_type.upper()
        self.meta.setText(f"{zone} · {sensitivity_label(camera.threshold_offset)}")
        self.address.setText(camera.source_address)
        self.address.setToolTip(self.stats.message or camera.source_address)
        self.status_pill.setText(text)
        for pill, value in ((self.status_pill, tone or "plain"),):
            pill.setProperty("v3pill", value)
            pill.style().unpolish(pill)
            pill.style().polish(pill)
        self.toggle.setText("Disable" if camera.ai_enabled else "Enable")
        self.thumb.set_dim(not camera.ai_enabled)


class CameraCard(QWidget):
    """A camera card that rises 6 px while the pointer is over it. The wrapper keeps the grid
    cell the same size; only the card inside it moves."""

    LIFT = 6
    open_requested = Signal(str)
    edit_requested = Signal(str)
    remove_requested = Signal(str)
    reconnect_requested = Signal(str)
    ai_changed = Signal(str, bool)

    def __init__(self, camera: CameraConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self._last_frame = 0.0
        self.body = _CardBody(camera)
        for name in ("open_requested", "edit_requested", "remove_requested", "reconnect_requested", "ai_changed"):
            getattr(self.body, name).connect(getattr(self, name))
        self._layout = QVBoxLayout(self)
        self._layout.addWidget(self.body)
        self._rise = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_rise)
        self._set_rise(0.0)

    @property
    def camera(self) -> CameraConfig:
        return self.body.camera

    def _set_rise(self, value) -> None:
        self._rise = float(value)
        lift = round(self.LIFT * self._rise)
        self._layout.setContentsMargins(0, self.LIFT - lift, 0, lift)

    def _ease(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._rise)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, event) -> None:
        self._ease(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._ease(0.0)
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # keep the live picture 16:9 however wide the card is
        height = max(128, int((self.width() - 40) * 9 / 16))
        if self.body.thumb.height() != height:
            self.body.thumb.setFixedHeight(height)

    def update_camera(self, camera: CameraConfig) -> None:
        self.body.update_camera(camera)

    def update_stats(self, stats: CameraStats) -> None:
        self.body.update_stats(stats)

    def set_frame(self, image) -> None:
        """Show the newest live frame; at most about ten per second per card."""
        now = time.monotonic()
        if now - self._last_frame < 0.1 or not self.isVisibleTo(self.window()):
            return
        self._last_frame = now
        thumb = self.body.thumb
        scaled = image.scaled(thumb.width() * 2, thumb.height() * 2, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                              Qt.TransformationMode.FastTransformation)
        thumb.set_frame(QPixmap.fromImage(scaled))


class CamerasPage(QWidget):
    open_requested = Signal(str)
    add_requested = Signal(dict)
    edit_requested = Signal(str, dict)
    local_test_requested = Signal()
    remove_requested = Signal(str)
    reconnect_requested = Signal(str)
    ai_changed = Signal(str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cards: dict[str, CameraCard] = {}
        self._stats: dict[str, CameraStats] = {}
        self._order: list[str] = []
        self._columns = 0
        self.credentials_provider = None  # callable(camera_id) -> CameraCredentials | None

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 8, 12)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.summary_label = mono_label("No cameras yet", point=9.5)
        header.addWidget(self.summary_label, 1)
        self.group_filter = QComboBox()
        self.group_filter.setMinimumWidth(160)
        self.group_filter.addItem("All zones", "")
        self.group_filter.currentIndexChanged.connect(self._apply_filter)
        header.addWidget(self.group_filter)
        self.attention_filter = QCheckBox("Needs attention")
        self.attention_filter.setToolTip("Show only cameras that are offline or in error")
        self.attention_filter.toggled.connect(self._apply_filter)
        header.addWidget(self.attention_filter)
        local = GhostButton("Test a video file")
        local.setToolTip("Test a local video file with the production AI pipeline. It is not added as a camera.")
        local.clicked.connect(self.local_test_requested.emit)
        header.addWidget(local)
        add = GhostButton("Add camera", primary=True)
        add.clicked.connect(self._add_camera)
        header.addWidget(add)
        root.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().setAutoFillBackground(False)
        self.content = QWidget()
        outer = QVBoxLayout(self.content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(16)
        outer.addLayout(self.grid)
        self.empty_state = self._create_empty_state()
        outer.addWidget(self.empty_state)
        outer.addStretch(1)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)

    def _create_empty_state(self) -> QFrame:
        card = GlassCard()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(30, 36, 30, 36)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("No camera sources configured")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        text = QLabel("Add a USB device, RTSP stream, HTTP/MJPEG stream or IP camera to begin monitoring.")
        text.setProperty("muted", True)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setWordWrap(True)
        button = GhostButton("Add your first camera", primary=True)
        button.clicked.connect(self._add_camera)
        layout.addWidget(title)
        layout.addWidget(text)
        layout.addWidget(button, 0, Qt.AlignmentFlag.AlignCenter)
        return card

    # ------------------------------------------------------------------ data
    def sync_cameras(self, cameras: list[CameraConfig], stats: dict[str, CameraStats]) -> None:
        self._stats = dict(stats)
        new_ids = {camera.camera_id for camera in cameras}
        for camera_id in set(self._cards) - new_ids:
            card = self._cards.pop(camera_id)
            self.grid.removeWidget(card)
            card.deleteLater()
        for camera in cameras:
            card = self._cards.get(camera.camera_id)
            if card is None:
                card = CameraCard(camera)
                card.open_requested.connect(self.open_requested.emit)
                card.edit_requested.connect(self._edit_camera)
                card.remove_requested.connect(self.remove_requested.emit)
                card.reconnect_requested.connect(self.reconnect_requested.emit)
                card.ai_changed.connect(self.ai_changed.emit)
                self._cards[camera.camera_id] = card
            else:
                card.update_camera(camera)
            card.update_stats(stats.get(camera.camera_id, CameraStats()))
        self._order = [camera.camera_id for camera in cameras]
        self.empty_state.setVisible(not cameras)
        self._refresh_groups(cameras)
        self._apply_filter()
        self._update_summary()

    def update_camera_stats(self, camera_id: str, stats: CameraStats) -> None:
        self._stats[camera_id] = stats
        card = self._cards.get(camera_id)
        if card is not None:
            card.update_stats(stats)
        self._apply_filter()
        self._update_summary()

    def update_frame(self, camera_id: str, image) -> None:
        card = self._cards.get(camera_id)
        if card is not None:
            card.set_frame(image)

    def cameras(self) -> list[CameraConfig]:
        return [self._cards[i].camera for i in self._order if i in self._cards]

    def _refresh_groups(self, cameras: list[CameraConfig]) -> None:
        groups = sorted({c.group_name for c in cameras if c.group_name})
        current = str(self.group_filter.currentData() or "")
        existing = [str(self.group_filter.itemData(i) or "") for i in range(1, self.group_filter.count())]
        if existing == groups:
            return
        self.group_filter.blockSignals(True)
        while self.group_filter.count() > 1:
            self.group_filter.removeItem(1)
        for name in groups:
            self.group_filter.addItem(name, name)
        self.group_filter.setCurrentIndex(max(0, self.group_filter.findData(current)))
        self.group_filter.blockSignals(False)

    def _visible_ids(self) -> list[str]:
        group = str(self.group_filter.currentData() or "")
        attention = self.attention_filter.isChecked()
        ids = []
        for camera_id in self._order:
            card = self._cards.get(camera_id)
            if card is None:
                continue
            status = (self._stats.get(camera_id, CameraStats()).status or "").upper()
            if (not group or card.camera.group_name == group) and (not attention or status in BAD):
                ids.append(camera_id)
        return ids

    def _apply_filter(self, *_args) -> None:
        visible = set(self._visible_ids())
        for camera_id, card in self._cards.items():
            card.setVisible(camera_id in visible)
        self._columns = 0
        self._relayout()

    def _update_summary(self) -> None:
        total = len(self._order)
        online = sum(
            1 for i in self._order if (self._stats.get(i, CameraStats()).status or "").upper() in ONLINE
        )
        if total:
            self.summary_label.setText(f"{total} camera{'s' if total != 1 else ''} · {online} online")
        else:
            self.summary_label.setText("No cameras yet")

    # ---------------------------------------------------------------- layout
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        width = max(self.scroll.viewport().width(), CARD_MIN_WIDTH)
        columns = max(1, (width + self.grid.spacing()) // (CARD_MIN_WIDTH + self.grid.spacing()))
        ids = self._visible_ids()
        signature = (columns, tuple(ids))
        if getattr(self, "_signature", None) == signature:
            return
        self._signature = signature
        for card in self._cards.values():
            self.grid.removeWidget(card)
        for column in range(self.grid.columnCount()):
            self.grid.setColumnStretch(column, 0)
        for index, camera_id in enumerate(ids):
            self.grid.addWidget(self._cards[camera_id], index // columns, index % columns)
            self._cards[camera_id].show()   # adding to a layout hides a re-parented widget
        for column in range(columns):
            self.grid.setColumnStretch(column, 1)

    # --------------------------------------------------------------- dialogs
    def _groups(self) -> list[str]:
        return sorted({c.camera.group_name for c in self._cards.values() if c.camera.group_name})

    def _add_camera(self) -> None:
        dialog = CameraFormDialog(self, groups=self._groups())
        if dialog.exec() == CameraFormDialog.DialogCode.Accepted and dialog.form_data:
            self.add_requested.emit(dialog.form_data)

    def _edit_camera(self, camera_id: str) -> None:
        card = self._cards.get(camera_id)
        if card is None:
            return
        credentials = self.credentials_provider(camera_id) if self.credentials_provider else None
        dialog = CameraFormDialog(self, camera=card.camera, credentials=credentials, groups=self._groups())
        if dialog.exec() == CameraFormDialog.DialogCode.Accepted and dialog.form_data:
            self.edit_requested.emit(camera_id, dialog.form_data)
