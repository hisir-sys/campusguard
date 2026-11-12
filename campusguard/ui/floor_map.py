"""Floor map: import a floor plan, drag cameras onto it, see at a glance which one is alerting."""
from __future__ import annotations

import math
import shutil
import uuid
from pathlib import Path

from PySide6.QtCore import QMimeData, QPointF, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from campusguard.settings import CameraConfig, CameraStats
from campusguard.ui.cameras_v3 import card_status
from campusguard.ui.theme import get_palette, qcolor
from campusguard.ui.v3widgets import GhostButton, GlassCard, Segmented, card_title, clear_layout, hairline, mono, mono_label

MIME = "application/x-campusguard-camera"
PIN_RADIUS = 9.0
IMAGE_TYPES = "Images (*.png *.jpg *.jpeg *.bmp *.webp)"


def pin_tone(camera: CameraConfig, stats: CameraStats) -> str:
    """'good' (live), 'bad' (offline / error), 'muted' (AI off) or 'warn' (connecting)."""
    _text, tone = card_status(camera, stats)
    if not camera.ai_enabled:
        return "muted"
    return {"up": "good", "new": "bad"}.get(tone, "warn")


class MapCanvas(QWidget):
    """Paints the plan and its pins; pins are dragged with the mouse or dropped from the tray."""

    pin_placed = Signal(str, float, float)      # camera_id, x, y (0..1 across the plan)
    pin_removed = Signal(str)
    camera_opened = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(360, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.pixmap: QPixmap | None = None
        self.pins: dict[str, tuple[float, float]] = {}
        self.labels: dict[str, tuple[str, str]] = {}        # camera_id -> (name, tone)
        self.hot: set[str] = set()
        self.armed: str | None = None
        self._drag: str | None = None
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

    # ----- data -----------------------------------------------------------
    def set_plan(self, pixmap: QPixmap | None) -> None:
        self.pixmap = pixmap
        self.update()

    def set_state(self, pins, labels, hot) -> None:
        self.pins, self.labels, self.hot = dict(pins), dict(labels), set(hot)
        if self.hot and self.isVisible():
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.hot:
            self._timer.start()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self) -> None:
        self._phase = (self._phase + 0.025) % 1.0
        self.update()

    # ----- geometry -------------------------------------------------------
    def image_rect(self) -> QRectF:
        area = QRectF(self.rect()).adjusted(16, 16, -16, -16)
        if self.pixmap is None or self.pixmap.isNull():
            return area
        scale = min(area.width() / self.pixmap.width(), area.height() / self.pixmap.height())
        w, h = self.pixmap.width() * scale, self.pixmap.height() * scale
        return QRectF(area.center().x() - w / 2, area.center().y() - h / 2, w, h)

    def _to_point(self, x: float, y: float) -> QPointF:
        r = self.image_rect()
        return QPointF(r.left() + x * r.width(), r.top() + y * r.height())

    def _to_unit(self, point: QPointF) -> tuple[float, float]:
        r = self.image_rect()
        return (
            min(1.0, max(0.0, (point.x() - r.left()) / max(1.0, r.width()))),
            min(1.0, max(0.0, (point.y() - r.top()) / max(1.0, r.height()))),
        )

    def _pin_at(self, point: QPointF) -> str | None:
        for camera_id in reversed(list(self.pins)):
            centre = self._to_point(*self.pins[camera_id])
            if math.hypot(point.x() - centre.x(), point.y() - centre.y()) <= PIN_RADIUS + 5:
                return camera_id
        return None

    # ----- painting -------------------------------------------------------
    def paintEvent(self, event) -> None:
        del event
        pal = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        card = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(hairline(), 1))
        painter.setBrush(qcolor(pal.glass, 120))
        painter.drawRoundedRect(card, 24, 24)
        rect = self.image_rect()
        if self.pixmap is not None and not self.pixmap.isNull():
            clip = QPainterPath()
            clip.addRoundedRect(rect, 12, 12)
            painter.save()
            painter.setClipPath(clip)
            painter.drawPixmap(rect, self.pixmap, QRectF(self.pixmap.rect()))
            painter.restore()
            painter.setPen(QPen(hairline(), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 12, 12)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(pal.muted, 70))
            for gx in range(int(rect.left()), int(rect.right()), 28):
                for gy in range(int(rect.top()), int(rect.bottom()), 28):
                    painter.drawEllipse(QPointF(gx, gy), 1.2, 1.2)
        label_font = mono(8)
        painter.setFont(label_font)
        metrics = QFontMetricsF(label_font)
        for camera_id, (x, y) in self.pins.items():
            name, tone = self.labels.get(camera_id, (camera_id, "muted"))
            centre = self._to_point(x, y)
            color = QColor(getattr(pal, "bad" if camera_id in self.hot else tone))
            if camera_id in self.hot:
                for offset in (0.0, 0.5):
                    t = (self._phase + offset) % 1.0
                    painter.setPen(QPen(qcolor(pal.bad, int(170 * (1.0 - t))), 2))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(centre, PIN_RADIUS + 4 + 20 * t, PIN_RADIUS + 4 + 20 * t)
            painter.setPen(QPen(QColor(pal.bg0), 2.5))
            painter.setBrush(color)
            lift = 2.0 if camera_id == self._drag else 0.0
            painter.drawEllipse(centre - QPointF(0, lift), PIN_RADIUS, PIN_RADIUS)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(pal.bg0))
            painter.drawEllipse(centre - QPointF(0, lift), 2.6, 2.6)
            text_w = metrics.horizontalAdvance(name) + 14
            chip = QRectF(centre.x() - text_w / 2, centre.y() + PIN_RADIUS + 5, text_w, 18)
            painter.setBrush(qcolor(pal.bg0, 225))
            painter.setPen(QPen(hairline(), 1))
            painter.drawRoundedRect(chip, 9, 9)
            painter.setPen(QColor(pal.text))
            painter.drawText(chip, int(Qt.AlignmentFlag.AlignCenter), name)
        if self.armed and not self.pins.get(self.armed):
            painter.setPen(QColor(pal.muted))
            painter.setFont(QFont(self.font()))
            painter.drawText(
                QRectF(self.rect()).adjusted(0, 0, 0, -12), int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom),
                f"Click the plan to place {self.labels.get(self.armed, (self.armed,))[0]}",
            )
        painter.end()

    # ----- mouse ----------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        point = event.position()
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._pin_at(point)
            if hit:
                self._drag = hit
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            elif self.armed and self.image_rect().contains(point):
                x, y = self._to_unit(point)
                camera_id, self.armed = self.armed, None
                self.unsetCursor()
                self.pin_placed.emit(camera_id, x, y)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        point = event.position()
        if self._drag:
            self.pins[self._drag] = self._to_unit(point)
            self.update()
        elif self.armed:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor if self._pin_at(point) else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag:
            camera_id, self._drag = self._drag, None
            x, y = self.pins[camera_id]
            self.pin_placed.emit(camera_id, x, y)
            self.unsetCursor()
            self.update()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        hit = self._pin_at(event.position())
        if hit:
            self.camera_opened.emit(hit)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        hit = self._pin_at(QPointF(event.pos()))
        if not hit:
            return
        menu = QMenu(self)
        open_action = menu.addAction("Open camera")
        remove_action = menu.addAction("Remove from map")
        chosen = menu.exec(event.globalPos())
        if chosen is open_action:
            self.camera_opened.emit(hit)
        elif chosen is remove_action:
            self.pin_removed.emit(hit)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self.armed:
            self.armed = None
            self.unsetCursor()
            self.update()
            return
        super().keyPressEvent(event)

    # ----- drops from the tray --------------------------------------------
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(MIME):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasFormat(MIME) or not self.image_rect().contains(event.position()):
            return
        camera_id = bytes(event.mimeData().data(MIME)).decode("utf-8")
        x, y = self._to_unit(event.position())
        event.acceptProposedAction()
        self.pin_placed.emit(camera_id, x, y)


class _TrayChip(QWidget):
    """One unplaced camera: click to arm it, or drag it onto the plan."""

    armed = Signal(str)

    def __init__(self, camera_id: str, name: str, tone: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.camera_id, self.name, self.tone = camera_id, name, tone
        self.selected = False
        self._press: QPointF | None = None
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(f"Place {name} on the map")

    def paintEvent(self, event) -> None:
        del event
        pal = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        painter.setPen(QPen(qcolor(pal.text, 120) if self.selected else hairline(), 1))
        painter.setBrush(qcolor(pal.text, 22) if self.selected else Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(body, 12, 12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(getattr(pal, self.tone)))
        painter.drawEllipse(QPointF(18, body.center().y()), 4, 4)
        painter.setPen(QColor(pal.text))
        painter.drawText(
            QRectF(32, 0, self.width() - 44, self.height()), int(Qt.AlignmentFlag.AlignVCenter),
            QFontMetricsF(self.font()).elidedText(self.name, Qt.TextElideMode.ElideRight, self.width() - 44),
        )

    def mousePressEvent(self, event) -> None:
        self._press = event.position()

    def mouseMoveEvent(self, event) -> None:
        if self._press is None or (event.position() - self._press).manhattanLength() < 8:
            return
        self._press = None
        mime = QMimeData()
        mime.setData(MIME, self.camera_id.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.exec(Qt.DropAction.CopyAction)

    def mouseReleaseEvent(self, event) -> None:
        if self._press is not None:
            self._press = None
            self.armed.emit(self.camera_id)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.armed.emit(self.camera_id)
            return
        super().keyPressEvent(event)


class FloorMapPage(QWidget):
    camera_requested = Signal(str)

    def __init__(self, repository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self._cameras: dict[str, CameraConfig] = {}
        self._stats: dict[str, CameraStats] = {}
        self._plans: list[dict] = []
        self._plan_id: int | None = None
        self._plan_names: dict[str, int] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 8, 12)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.plan_switch_holder = QHBoxLayout()
        header.addLayout(self.plan_switch_holder)
        self.summary = mono_label("", point=9.5)
        header.addWidget(self.summary, 1)
        self.remove_button = GhostButton("Remove plan")
        self.remove_button.clicked.connect(self._remove_plan)
        header.addWidget(self.remove_button)
        self.import_button = GhostButton("Import floor plan", primary=True)
        self.import_button.clicked.connect(self._import_plan)
        header.addWidget(self.import_button)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(16)
        self.canvas = MapCanvas()
        self.canvas.pin_placed.connect(self._place)
        self.canvas.pin_removed.connect(self._unpin)
        self.canvas.camera_opened.connect(self.camera_requested.emit)
        body.addWidget(self.canvas, 1)

        side = GlassCard()
        side.setFixedWidth(250)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(20, 20, 20, 20)
        side_layout.setSpacing(10)
        side_layout.addWidget(card_title("Not on the map"))
        self.tray_hint = QLabel("Drag a camera onto the plan, or click it and then click the plan.")
        self.tray_hint.setProperty("muted", True)
        self.tray_hint.setWordWrap(True)
        side_layout.addWidget(self.tray_hint)
        self.tray = QVBoxLayout()
        self.tray.setSpacing(6)
        scroll_body = QWidget()
        scroll_body.setLayout(self.tray)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setWidget(scroll_body)
        side_layout.addWidget(scroll, 1)
        legend = QLabel("Green live · Amber connecting · Grey AI off · Coral offline or alerting")
        legend.setProperty("muted", True)
        legend.setWordWrap(True)
        side_layout.addWidget(legend)
        body.addWidget(side)
        root.addLayout(body, 1)

        self.empty_hint = QLabel("Import a floor plan (PNG or JPG) to start placing cameras.")
        self.empty_hint.setProperty("muted", True)
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setParent(self.canvas)
        self.empty_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._poll = QTimer(self)           # picks up new incidents while the page is open
        self._poll.setInterval(2500)
        self._poll.timeout.connect(self.refresh)
        self.reload()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()
        self._poll.start()

    def hideEvent(self, event) -> None:
        self._poll.stop()
        super().hideEvent(event)

    # ----- data in --------------------------------------------------------
    def sync_cameras(self, cameras: list[CameraConfig], stats: dict[str, CameraStats]) -> None:
        self._cameras = {camera.camera_id: camera for camera in cameras}
        self._stats = dict(stats)
        self.refresh()

    def update_camera_stats(self, camera_id: str, stats: CameraStats) -> None:
        self._stats[camera_id] = stats
        self.refresh()

    def reload(self) -> None:
        """Re-read the plans from the database and rebuild the plan switch."""
        self._plans = self.repository.list_floor_plans()
        self._plan_names = {}
        for plan in self._plans:
            name = plan["name"]
            while name in self._plan_names:
                name += " 2"
            self._plan_names[name] = plan["plan_id"]
        if self._plan_id not in {plan["plan_id"] for plan in self._plans}:
            self._plan_id = self._plans[0]["plan_id"] if self._plans else None
        clear_layout(self.plan_switch_holder)
        self.plan_switch = None
        if len(self._plans) > 1:
            current = next(n for n, i in self._plan_names.items() if i == self._plan_id)
            self.plan_switch = Segmented(list(self._plan_names), current)
            self.plan_switch.changed.connect(self._switch_plan)
            self.plan_switch_holder.addWidget(self.plan_switch)
        self.remove_button.setVisible(bool(self._plans))
        self.refresh()

    def _switch_plan(self, name: str) -> None:
        self._plan_id = self._plan_names.get(name, self._plan_id)
        self.refresh()

    def refresh(self) -> None:
        plan = next((p for p in self._plans if p["plan_id"] == self._plan_id), None)
        pixmap = QPixmap(plan["image_path"]) if plan else None
        self.canvas.set_plan(pixmap if pixmap is not None and not pixmap.isNull() else None)
        all_pins = self.repository.list_camera_pins()
        here = {cid: (x, y) for cid, (pid, x, y) in all_pins.items() if pid == self._plan_id and cid in self._cameras}
        labels = {
            cid: (camera.name, pin_tone(camera, self._stats.get(cid, CameraStats())))
            for cid, camera in self._cameras.items()
        }
        hot = {
            str(row.get("camera_id")) for row in self.repository.list_incidents(200) if str(row.get("status")) == "NEW"
        } & set(here)
        self.canvas.set_state(here, labels, hot)
        self.empty_hint.setVisible(plan is None)
        self.empty_hint.setGeometry(self.canvas.rect())
        free = [cid for cid in self._cameras if cid not in here]
        self._fill_tray(free, labels, enabled=plan is not None)
        total = len(self._cameras)
        if plan is None:
            self.summary.setText("No floor plan yet")
        else:
            self.summary.setText(
                f"{plan['name']} · {len(here)} of {total} cameras placed" + (f" · {len(hot)} alerting" if hot else "")
            )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.empty_hint.setGeometry(self.canvas.rect())

    def _fill_tray(self, free: list[str], labels, enabled: bool) -> None:
        clear_layout(self.tray)
        for cid in free:
            name, tone = labels[cid]
            chip = _TrayChip(cid, name, tone)
            chip.setEnabled(enabled)
            chip.selected = self.canvas.armed == cid
            chip.armed.connect(self._arm)
            self.tray.addWidget(chip)
        self.tray.addStretch(1)
        self.tray_hint.setText(
            "Every camera is on the map." if self._cameras and not free
            else "Add a camera first." if not self._cameras
            else "Import a floor plan first." if not enabled
            else "Drag a camera onto the plan, or click it and then click the plan."
        )

    # ----- actions --------------------------------------------------------
    def _arm(self, camera_id: str) -> None:
        self.canvas.armed = None if self.canvas.armed == camera_id else camera_id
        self.canvas.setFocus()
        self.refresh()

    def _place(self, camera_id: str, x: float, y: float) -> None:
        if self._plan_id is None or camera_id not in self._cameras:
            return
        self.repository.set_camera_pin(camera_id, self._plan_id, x, y)
        self.canvas.armed = None
        self.refresh()

    def _unpin(self, camera_id: str) -> None:
        self.repository.remove_camera_pin(camera_id)
        self.refresh()

    def _import_plan(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import floor plan", "", IMAGE_TYPES)
        if path:
            self.import_plan(path)

    def import_plan(self, path: str) -> int | None:
        source = Path(path)
        if QPixmap(str(source)).isNull():
            QMessageBox.warning(self, "Floor plan", "That file could not be read as an image.")
            return None
        folder = Path(self.repository.data_dir) / "floor_plans"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{uuid.uuid4().hex[:10]}{source.suffix.lower()}"
        shutil.copyfile(source, target)
        self._plan_id = self.repository.add_floor_plan(source.stem.replace("_", " ").replace("-", " ").title(), str(target))
        self.reload()
        return self._plan_id

    def _remove_plan(self) -> None:
        plan = next((p for p in self._plans if p["plan_id"] == self._plan_id), None)
        if plan is None:
            return
        answer = QMessageBox.question(
            self, "Remove floor plan",
            f"Remove “{plan['name']}” and the camera positions on it? The cameras themselves are not touched.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.repository.remove_floor_plan(plan["plan_id"])
        try:
            Path(plan["image_path"]).unlink(missing_ok=True)
        except OSError:
            pass
        self._plan_id = None
        self.reload()
