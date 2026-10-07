from __future__ import annotations

from dataclasses import replace

from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QScrollArea,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from campusguard.footage import clear_footage
from campusguard.credentials import CredentialVault
from campusguard.settings import (
    AppSettings,
    CameraConfig,
    CameraCredentials,
    CameraStats,
)
from campusguard.storage import Repository
from campusguard.ui.camera_page import CamerasPage, LocalVideoTestDialog
from campusguard.ui.common import apply_theme, make_card, make_page_title
from campusguard.ui.dashboard_page import DashboardPage
from campusguard.ui.glass_nav import BackdropWidget, BottomBar, TopBar
from campusguard.ui.history_pages import AlertsPage, IncidentsPage
from campusguard.ui.icons import set_icon_theme
from campusguard.ui.settings_page import SettingsPage
from campusguard.ui.theme import get_palette, rgba


class InAppOverlay(QFrame):
    confirmed = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("inAppOverlay")
        palette = get_palette()

        self.setStyleSheet(
            f"""
            QFrame#inAppOverlay {{
                background: rgba(0, 0, 0, 115);
                border: none;
            }}
            QFrame#inAppPanel {{
                background: {rgba(palette.glass, palette.glass_alpha)};
                border: 1px solid {rgba(palette.line, min(255, int(palette.line_alpha * 1.6)))};
                border-radius: 26px;
            }}
            QLabel#overlayTitle {{
                font-size: 16pt;
                font-weight: 800;
                background: transparent;
            }}
            QLabel#overlayBody {{
                font-size: 10pt;
                line-height: 1.4;
                background: transparent;
            }}
            QLabel#overlayClose {{
                background: {rgba(palette.veil, min(255, palette.veil_alpha * 2))};
                border: 1px solid {rgba(palette.line, palette.line_alpha)};
                border-radius: 15px;
                font-size: 14pt;
            }}
            QLabel#overlayClose:hover {{
                background: {rgba(palette.veil, min(255, palette.veil_alpha * 3))};
            }}
            QLabel#cameraViewport {{
                background: {rgba(palette.bg0, 245)};
                border: 1px solid {rgba(palette.line, palette.line_alpha)};
                border-radius: 18px;
            }}
            """        )
        self._panel = QFrame(self)
        self._panel.setObjectName("inAppPanel")
        self._panel.setFixedSize(820, 560)

        self._title = QLabel()
        self._title.setObjectName("overlayTitle")

        self._body = QLabel()
        self._body.setObjectName("overlayBody")
        self._body.setWordWrap(True)

        self._close = QPushButton("×")
        self._close.setObjectName("overlayClose")
        self._close.setFixedSize(32, 32)
        self._close.clicked.connect(self.hide)

        self._content = QVBoxLayout(self._panel)
        self._content.setContentsMargins(24, 20, 24, 22)
        self._content.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(self._title, 1)
        header.addWidget(self._close)
        self._content.addLayout(header)

        self._body_widget = QWidget()
        self._body_layout = QVBoxLayout(self._body_widget)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(12)
        self._content.addWidget(self._body_widget, 1)

        self._confirm_callback = None
        self.hide()

    def _clear_body(self) -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                if widget is self._body:
                    self._body.setVisible(False)
                else:
                    widget.deleteLater()

            child_layout = item.layout()
            if child_layout is not None:
                while child_layout.count():
                    child_item = child_layout.takeAt(0)
                    child_widget = child_item.widget()
                    if child_widget is not None:
                        child_widget.deleteLater()

    def _center(self) -> None:
        self._panel.adjustSize()
        self._panel.move(
            max(18, (self.width() - self._panel.width()) // 2),
            max(18, (self.height() - self._panel.height()) // 2),
        )

    def show_confirmation(self, title: str, message: str, callback) -> None:
        self._confirm_callback = callback
        self._clear_body()
        self._title.setText(title)
        self._body.setText(message)
        self._body.setVisible(True)
        self._body_layout.addWidget(self._body)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setProperty("secondaryButton", True)
        cancel.clicked.connect(self.hide)
        confirm = QPushButton("Confirm")
        confirm.setProperty("danger", True)
        confirm.clicked.connect(self._confirm)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        self._body_layout.addLayout(buttons)

        self._panel.setFixedSize(640, 290)
        self.show()
        self.raise_()
        self._center()

    def _confirm(self) -> None:
        callback = self._confirm_callback
        self._confirm_callback = None
        self.hide()
        if callback is not None:
            callback()
        self.confirmed.emit()

    def show_camera(self, camera: CameraConfig, image=None, stats: CameraStats | None = None) -> None:
        self._clear_body()
        self._title.setText(camera.name)
        self._body.setVisible(False)

        viewport = QLabel("Waiting for camera frames")
        viewport.setObjectName("cameraViewport")
        viewport.setAlignment(Qt.AlignmentFlag.AlignCenter)
        viewport.setMinimumHeight(390)
        viewport.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._body_layout.addWidget(viewport, 1)

        info = QLabel()
        info.setProperty("muted", True)
        self._body_layout.addWidget(info)

        close = QPushButton("Close")
        close.setProperty("secondaryButton", True)
        close.clicked.connect(self.hide)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        self._body_layout.addLayout(row)

        self._panel.setFixedSize(1000, 660)
        self._camera_viewport = viewport
        self._camera_info = info
        self._camera = camera
        self._camera_stats = stats or CameraStats()
        if image is not None:
            self.set_camera_frame(image, "LIVE", None)
        else:
            self._render_camera_info()
        self.show()
        self.raise_()
        self._center()

    def set_camera_frame(self, image, state: str, confidence: float | None) -> None:
        if not hasattr(self, "_camera_viewport") or not self.isVisible():
            return
        pixmap = QPixmap.fromImage(image)
        self._camera_viewport.setPixmap(
            pixmap.scaled(
                self._camera_viewport.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        suffix = f"   Confidence: {confidence:.0%}" if confidence is not None else ""
        fps = f"{self._camera_stats.fps:.1f}" if self._camera_stats.fps is not None else "N/A"
        resolution = self._camera_stats.resolution or "N/A"
        self._camera_info.setText(f"{state}   ·   FPS: {fps}   ·   Resolution: {resolution}{suffix}")

    def set_camera_stats(self, stats: CameraStats) -> None:
        if not hasattr(self, "_camera_info") or not self.isVisible():
            return
        self._camera_stats = stats
        self._render_camera_info()

    def _render_camera_info(self) -> None:
        status = self._camera_stats.status or "CONNECTING"
        if status != "LIVE":
            self._camera_viewport.clear()
            self._camera_viewport.setText(self._camera_stats.message or "Waiting for camera frames")
        fps = f"{self._camera_stats.fps:.1f}" if self._camera_stats.fps is not None else "N/A"
        resolution = self._camera_stats.resolution or "N/A"
        self._camera_info.setText(f"{status}   ·   FPS: {fps}   ·   Resolution: {resolution}")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.isVisible():
            self._center()

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CampusGuard — Security Operations")
        self.resize(1500, 940)
        self.setMinimumSize(1080, 700)

        self.repository = Repository()
        self.vault = CredentialVault()
        self.settings = self.repository.get_settings()
        self.cameras: dict[str, CameraConfig] = {
            camera.camera_id: camera for camera in self.repository.list_cameras()
        }
        self.camera_stats: dict[str, CameraStats] = {
            camera_id: CameraStats() for camera_id in self.cameras
        }
        self.model_statuses: dict[str, dict[str, str]] = {}
        self._previous_camera_status: dict[str, str] = {}
        self._camera_view_camera_id: str | None = None
        self.operator_name: str | None = None
        self._pending_footage_incidents: dict[str, str] = {}

        # Pick the icon/palette theme before any widget is built so nothing flashes.
        set_icon_theme(self.settings.theme)

        # CameraManager imports PyTorch/Ultralytics. Keep that heavy AI stack out
        # of initial window construction so the desktop UI appears immediately.
        self.camera_manager = None
        self._build_ui()
        apply_theme(self, self.settings.theme)
        self.top_bar.set_theme(self.settings.theme)

        self._sync_cameras()
        self.dashboard.update_model_configuration(self.settings)
        self._update_operator_button()
        self.navigate("dashboard")
        self._update_alert_badge()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1500)
        self._refresh_timer.timeout.connect(self._refresh_pages)
        self._refresh_timer.start()

        # Do not start camera/model workers inside the window constructor.
        # Starting them after the event loop begins guarantees the Dashboard
        # can render immediately, even when a camera or AI model takes time
        # to initialize.
        QTimer.singleShot(0, self._initialize_camera_engine)

        self._add_shortcut("Ctrl+1", lambda: self.navigate("dashboard"))
        self._add_shortcut("Ctrl+2", lambda: self.navigate("cameras"))
        self._add_shortcut("Ctrl+3", lambda: self.navigate("incidents"))
        self._add_shortcut("Ctrl+4", lambda: self.navigate("alerts"))
        self._add_shortcut("Ctrl+5", lambda: self.navigate("settings"))
        self._add_shortcut("Ctrl+K", self.top_bar.focus_search)

    def _initialize_camera_engine(self) -> None:
        try:
            from campusguard.camera_runtime import CameraManager

            self.camera_manager = CameraManager(self.vault, self.repository.footage_dir, self)
            self.camera_manager.set_settings(self.settings)
            self._connect_camera_manager()
            self._start_cameras()
        except Exception as error:
            self.statusBar().showMessage(f"AI engine initialization failed: {error}", 12000)
            for camera in self.cameras.values():
                self._set_camera_status(camera.camera_id, "ERROR", f"AI engine unavailable: {error}")

    def _start_cameras(self) -> None:
        if self.camera_manager is None:
            return
        for camera in self.cameras.values():
            try:
                self.camera_manager.start_camera(camera)
            except Exception as error:
                self._set_camera_status(
                    camera.camera_id,
                    "ERROR",
                    f"Camera could not start: {error}",
                )

    def _add_shortcut(self, sequence: str, callback) -> None:
        action = QAction(self)
        action.setShortcut(QKeySequence(sequence))
        action.triggered.connect(lambda _checked=False: callback())
        self.addAction(action)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = BackdropWidget()
        central.setObjectName("centralContent")

        outer = QHBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(12)

        # Left operations rail. It stays visually quiet when collapsed and
        # expands on hover so the workspace remains the hero.
        self.top_bar = TopBar()
        outer.addWidget(self.top_bar, 0)

        workspace = QVBoxLayout()
        workspace.setContentsMargins(0, 0, 0, 0)
        workspace.setSpacing(10)

        self.stack = QStackedWidget()
        self.stack.setObjectName("workspaceStack")
        self.stack.setMaximumWidth(1240)

        self.dashboard = DashboardPage(self.repository)
        self.camera_page = CamerasPage()
        self.incidents_page = IncidentsPage(self.repository)
        self.alerts_page = AlertsPage(self.repository)
        self.settings_page = SettingsPage(self.settings)
        self.info_pages = self._build_information_pages()

        self._pages = {
            "dashboard": self.dashboard,
            "cameras": self.camera_page,
            "incidents": self.incidents_page,
            "alerts": self.alerts_page,
            "settings": self.settings_page,
            **self.info_pages,
        }

        for page in self._pages.values():
            self.stack.addWidget(page)

        workspace.addWidget(self.stack, 1)

        dock_row = QHBoxLayout()
        dock_row.setContentsMargins(0, 0, 0, 2)
        dock_row.setSpacing(0)
        dock_row.addStretch(1)
        self.bottom_bar = BottomBar()
        dock_row.addWidget(self.bottom_bar, 0, Qt.AlignmentFlag.AlignCenter)
        dock_row.addStretch(1)
        workspace.addLayout(dock_row, 0)

        outer.addLayout(workspace, 1)

        self.setCentralWidget(central)
        self._in_app_overlay = InAppOverlay(central)
        self._in_app_overlay.hide()
        self.statusBar().setSizeGripEnabled(False)
        self._connect_pages()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_in_app_overlay"):
            self._in_app_overlay.setGeometry(self.centralWidget().rect())

    # ------------------------------------------------------------------
    # Long-form technical information pages
    # ------------------------------------------------------------------
    def _build_information_pages(self) -> dict[str, QWidget]:
        return {
            "services": self._make_services_page(),
            "about": self._make_about_page(),
            "tools": self._make_tools_page(),
            "how-it-works": self._make_how_it_works_page(),
        }

    @staticmethod
    def _info_scroll(content: QWidget) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.viewport().setAutoFillBackground(False)
        content.setMinimumWidth(0)
        content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        scroll.setWidget(content)
        return scroll

    @staticmethod
    def _section_header(title: str, description: str) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 21pt; font-weight: 700; letter-spacing: -0.15px;")
        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setStyleSheet("font-size: 10pt; color: palette(mid);")
        layout.addWidget(title_label)
        layout.addWidget(description_label)
        return box

    @staticmethod
    def _tech_card(title: str, subtitle: str, body: str, icon: str | None = None) -> QWidget:
        card, body_layout = make_card(title, icon=icon)
        card.setMinimumHeight(188)
        card.setMinimumWidth(0)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        subtitle_label = QLabel(subtitle)
        subtitle_label.setStyleSheet("font-size: 9pt; color: palette(mid); font-weight: 600;")
        subtitle_label.setWordWrap(True)
        body_label = QLabel(body)
        body_label.setWordWrap(True)
        body_layout.addWidget(subtitle_label)
        body_layout.addWidget(body_label)
        return card

    @staticmethod
    def _flow_node(number: str, title: str, detail: str) -> QWidget:
        pal = get_palette()
        node = QFrame()
        node.setObjectName("technicalFlowNode")
        # Keep the flowchart integrated with the glass UI: no bright white
        # outlines and no hard panel edge that fights the surrounding theme.
        node.setStyleSheet(
            f"QFrame#technicalFlowNode {{ "
            f"background: {pal.glass}; "
            f"border: 1px solid rgba(255,255,255,0.07); "
            f"border-radius: 16px; }}"
        )
        layout = QHBoxLayout(node)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        badge = QFrame()
        badge.setFixedSize(38, 38)
        badge.setObjectName("flowStepBadge")
        badge.setStyleSheet(
            f"QFrame#flowStepBadge {{ "
            f"background: {pal.accent}; "
            f"border: none; border-radius: 19px; }}"
        )
        badge_layout = QVBoxLayout(badge)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        step = QLabel(number)
        step.setAlignment(Qt.AlignmentFlag.AlignCenter)
        step.setStyleSheet(
            "font-size: 8pt; font-weight: 800; color: white; "
            "background: transparent; border: none;"
        )
        badge_layout.addWidget(step)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(4)

        heading = QLabel(title)
        heading.setStyleSheet("font-size: 11pt; font-weight: 700; border: none;")
        text = QLabel(detail)
        text.setWordWrap(True)
        text.setStyleSheet(
            "font-size: 9pt; color: palette(mid); border: none;"
        )

        text_column.addWidget(heading)
        text_column.addWidget(text)

        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(text_column, 1)
        return node

    @staticmethod
    def _flow_arrow() -> QWidget:
        wrapper = QWidget()
        wrapper.setFixedHeight(26)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(20, 0, 0, 0)
        layout.setSpacing(0)

        line = QFrame()
        line.setFixedHeight(2)
        line.setStyleSheet(
            "background: rgba(91,124,250,0.20); border: none;"
        )
        layout.addWidget(line, 1, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)
        return wrapper

    def _make_about_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 36)
        layout.setSpacing(18)
        layout.addWidget(self._section_header(
            "About CampusGuard",
            "A local-first campus security operations application built around configured camera sources, local processing, incident review, and operator alerts.",
        ))

        card, body = make_card("System purpose", icon="shield")
        points = (
            "CampusGuard connects external USB, RTSP, HTTP/MJPEG, and IP camera sources to one desktop operations interface.",
            "Camera acquisition, AI processing, temporal event gating, evidence recording, incident persistence, alert review, and operator controls are separated into dedicated modules.",
            "It does not perform facial recognition or identify people. Detection results are represented as camera events and tracked objects.",
        )
        for text in points:
            label = QLabel("•  " + text)
            label.setWordWrap(True)
            label.setStyleSheet("padding: 4px 0;")
            body.addWidget(label)
        layout.addWidget(card)

        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(self._tech_card(
            "Desktop architecture", "PySide6 UI",
            "Navigation, camera monitoring, history, alerts, settings, notifications, and the live operations workspace.",
        ), 1)
        row.addWidget(self._tech_card(
            "Local persistence", "SQLite repository",
            "Camera configuration, settings, notifications, incidents, alerts, and saved detection footage are stored locally.",
        ), 1)
        row.addWidget(self._tech_card(
            "Camera security", "OS credential vault",
            "Configured camera credentials are handled through the operating-system credential vault.",
        ), 1)
        layout.addLayout(row)

        card, body = make_card("Technical boundaries", icon="activity")
        boundaries = (
            ("Camera layer", "Reads frames and reports connection state, FPS, resolution, and runtime errors."),
            ("AI layer", "Runs the configured Spontim 1.0 pipeline and reports runtime model status without exposing model-file administration to operators."),
            ("Event layer", "Converts stable temporal results into one continuous incident and alert, with linked MP4 evidence."),
            ("Operations layer", "Presents live cameras, incidents, alerts, AI status, system stats, settings, and in-app evidence viewing."),
        )
        for title, detail in boundaries:
            label = QLabel(f"<b>{title}</b><br>{detail}")
            label.setWordWrap(True)
            label.setStyleSheet("padding: 5px 0;")
            body.addWidget(label)
        layout.addWidget(card)
        layout.addStretch(1)
        return self._info_scroll(content)

    def _make_services_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 36)
        layout.setSpacing(18)
        layout.addWidget(self._section_header(
            "Services",
            "The technical service chain from external camera acquisition through AI analysis, incident persistence, and operator alerts.",
        ))

        services = (
            ("01", "Camera Runtime", "USB / RTSP / HTTP / IP",
             "Maintains the live camera stream, frame mailbox, connection state, FPS, and resolution."),
            ("02", "Person Detection", "YOLO",
             "Detects people in each frame and provides the regions used by downstream analysis."),
            ("03", "Tracking", "ByteTrack",
             "Maintains stable operator-facing person identities across consecutive frames."),
            ("04", "Pose Analysis", "YOLO Pose",
             "Associates pose keypoints with detected people for contextual movement analysis."),
            ("05", "Spontim 1.0", "MC3-18 · 16 frames",
             "Analyzes a temporal sequence rather than making a decision from one isolated frame."),
            ("06", "Event Stability", "Temporal gate",
             "Requires consecutive fight predictions and sustained confidence before creating one persistent event."),
            ("07", "Footage Recorder", "MP4 evidence",
             "Stores one complete detection clip in CampusGuard storage and links it to the incident."),
            ("08", "Incident & Alert Service", "SQLite",
             "Persists incidents, alerts, notifications, confidence, severity, status, and saved footage references."),
            ("09", "Operator UI", "Glass workspace",
             "Presents live cameras, incidents, alerts, system status, AI status, and in-app evidence viewing."),
        )
        for i, (number, title, subtitle, detail) in enumerate(services):
            layout.addWidget(self._flow_node(number, title, f"{subtitle} — {detail}"))
            if i != len(services) - 1:
                layout.addWidget(self._flow_arrow())

        card, body = make_card("Service contract", icon="server")
        body.addWidget(QLabel(
            "Capture produces frames, models produce analysis, the repository persists state, "
            "and the UI presents that state to the operator."
        ))
        layout.addWidget(card)
        layout.addStretch(1)
        return self._info_scroll(content)

    def _make_tools_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 36)
        layout.setSpacing(18)
        layout.addWidget(self._section_header(
            "Tools",
            "Technical tools for camera operations, AI configuration, diagnostics, incident review, alerts, and administration.",
        ))

        tools = (
            ("Camera Manager", "Live operations",
             "Add, test, reconnect, remove, and monitor configured external camera sources."),
            ("Spontim 1.0", "Temporal detection",
             "Runs the configured fight-classification pipeline on short frame sequences."),
            ("Tracking + Pose", "Context",
             "Combines person tracking and pose information to improve attribution and operator context."),
            ("Incident History", "Evidence index",
             "Review persistent incidents with camera, confidence, severity, status, and linked footage."),
            ("Alert Console", "Response",
             "Review active alerts and open the associated saved detection footage."),
            ("Footage Storage", "MP4 evidence",
             "Keep detection clips locally and clear stored footage without deleting incident history."),
            ("System Stats", "Runtime overview",
             "View camera health, incident totals, alert state, and monitoring status in the glass dashboard panel."),
            ("AI Engine", "Inference overview",
             "View active model, pipeline stages, runtime state, confidence threshold, and compute device."),
            ("Glass Operations UI", "In-app workflow",
             "Camera viewing and confirmation actions stay inside the CampusGuard window."),
        )

        for i in range(0, len(tools), 3):
            row = QHBoxLayout()
            row.setSpacing(14)
            for title, subtitle, detail in tools[i:i + 3]:
                row.addWidget(self._tech_card(title, subtitle, detail), 1)
            while row.count() < 3:
                spacer = QWidget()
                spacer.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Preferred,
                )
                row.addWidget(spacer, 1)
            layout.addLayout(row)

        card, body = make_card("Operator workflow", icon="settings")
        body.addWidget(QLabel(
            "1. Configure an external camera → 2. Test the connection → "
            "3. Confirm model availability → 4. Enable AI → 5. Monitor live state → "
            "6. Review incidents and alerts."
        ))
        layout.addWidget(card)
        layout.addStretch(1)
        return self._info_scroll(content)

    def _make_how_it_works_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 40)
        layout.setSpacing(18)
        layout.addWidget(self._section_header(
            "How It Works",
            "A detailed view of the CampusGuard frame and sequence processing pipeline.",
        ))

        pipeline = (
            ("01", "Camera Source", "USB / RTSP / HTTP / IP",
             "A configured external camera supplies the live frames used by CampusGuard."),
            ("02", "Frame Runtime", "OpenCV + latest-frame mailbox",
             "The runtime keeps the newest frame available so stale frames do not build an unnecessary queue."),
            ("03", "Person Detection", "YOLO",
             "People are detected and passed into tracking and contextual analysis."),
            ("04", "Tracking", "ByteTrack + stable display IDs",
             "Cross-frame association keeps the operator view coherent even when internal tracker IDs change."),
            ("05", "Pose", "YOLO Pose",
             "Pose keypoints are matched to people and drawn only when their confidence is sufficient."),
            ("06", "Temporal Clip", "16-frame sequence",
             "Spontim 1.0 evaluates motion over a short sequence instead of treating every frame as a separate event."),
            ("07", "Fight Gate", "4 trigger / 6 release",
             "The temporal gate suppresses isolated predictions and latches one continuous detection."),
            ("08", "Incident", "SQLite",
             "One stable event becomes one incident and one alert rather than a frame-by-frame stream of records."),
            ("09", "Footage", "Single MP4 clip",
             "The detection is recorded as one continuous video clip and linked to the incident."),
            ("10", "Operator Review", "View inside CampusGuard",
             "The incident or alert provides a View action that opens the saved footage inside the application."),
        )
        for i, (number, title, subtitle, detail) in enumerate(pipeline):
            layout.addWidget(self._flow_node(number, title, f"{subtitle} — {detail}"))
            if i != len(pipeline) - 1:
                layout.addWidget(self._flow_arrow())

        card, body = make_card("End-to-end data flow", icon="activity")
        flow = QLabel(
            "CAMERA SOURCE  →  FRAME  →  PERSON DETECTION  →  TRACKING  →  "
            "POSE  →  TEMPORAL CLIP  →  ACTION SCORE  →  STABLE EVENT  →  "
            "INCIDENT  →  ALERT  →  OPERATOR"
        )
        flow.setWordWrap(True)
        flow.setStyleSheet("font-size: 10pt; font-weight: 700; padding: 6px 0;")
        body.addWidget(flow)
        layout.addWidget(card)

        card, body = make_card("Model behavior", icon="cpu")
        note = QLabel(
            "Spontim 1.0 evaluates a 16-frame temporal sequence. Stable event gating prevents isolated "
            "predictions from becoming persistent incidents. Confirmed detections are recorded as one MP4 "
            "clip and linked to the incident for operator review."
        )
        note.setWordWrap(True)
        body.addWidget(note)
        layout.addWidget(card)
        layout.addStretch(1)
        return self._info_scroll(content)

    def _connect_pages(self) -> None:
        self.top_bar.page_requested.connect(self.navigate)
        self.top_bar.theme_toggle_requested.connect(self._toggle_theme)
        self.top_bar.login_requested.connect(self._toggle_operator)
        self.top_bar.search_submitted.connect(self._run_global_search)
        self.bottom_bar.page_requested.connect(self.navigate)

        self.dashboard.camera_selected.connect(self.open_camera)
        self.dashboard.view_alerts_requested.connect(lambda: self.navigate("alerts"))
        self.dashboard.model_switch_requested.connect(self._switch_violence_model)
        self.camera_page.add_requested.connect(self._add_camera)
        self.camera_page.local_test_requested.connect(self._open_local_file_test)
        self.camera_page.remove_requested.connect(self._remove_camera)
        self.camera_page.reconnect_requested.connect(self._reconnect_camera)
        self.camera_page.ai_changed.connect(self._set_camera_ai)
        self.dashboard.clear_notifications_requested.connect(self._clear_dashboard_notifications)
        self.incidents_page.status_change_requested.connect(self._set_incident_status)
        self.incidents_page.clear_all_requested.connect(self._clear_all_history)
        self.incidents_page.clear_footage_requested.connect(self._clear_footage_storage)
        self.alerts_page.clear_all_requested.connect(self._clear_all_history)
        self.settings_page.settings_changed.connect(self._save_settings)

    def _connect_camera_manager(self) -> None:
        self.camera_manager.camera_status_changed.connect(self._on_camera_status)
        self.camera_manager.camera_stats_changed.connect(self._on_camera_stats)
        self.camera_manager.frame_ready.connect(self._on_frame)
        self.camera_manager.model_status_changed.connect(self._on_model_status)
        self.camera_manager.event_detected.connect(self._on_event)
        self.camera_manager.footage_saved.connect(self._on_footage_saved)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def navigate(self, page: str) -> None:
        if page not in self._pages:
            return
        self.stack.setCurrentWidget(self._pages[page])
        self.top_bar.set_active(page)
        self.bottom_bar.set_active(page)
        if page == "incidents":
            self.incidents_page.refresh()
        elif page == "alerts":
            self.alerts_page.refresh()
        elif page == "cameras":
            self._sync_cameras()

    def open_camera(self, camera_id: str) -> None:
        camera = self.cameras.get(camera_id)
        if camera is None:
            return
        self._camera_view_camera_id = camera_id
        self._in_app_overlay.show_camera(
            camera,
            stats=self.camera_stats.get(camera_id, CameraStats()),
        )

    # ------------------------------------------------------------------
    # Cameras
    # ------------------------------------------------------------------
    def _open_local_file_test(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select local test video",
            "",
            "Video files (*.mp4 *.avi *.mov *.mkv *.wmv *.m4v);;All files (*.*)",
        )
        if not path:
            return
        dialog = LocalVideoTestDialog(path, self.settings, self)
        dialog.exec()

    def _add_camera(self, values: dict) -> None:
        camera = self.repository.add_camera(
            values["name"],
            values["source_type"],
            values["source_address"],
        )
        credentials = CameraCredentials(values["username"], values["password"])
        try:
            self.vault.save(camera.camera_id, credentials)
        except Exception:
            self.repository.remove_camera(camera.camera_id)
            QMessageBox.critical(
                self,
                "Credential vault unavailable",
                "CampusGuard could not store the camera credentials securely, so the camera was not saved.\n\n"
                "Check that the Windows credential service is available and try again.",
            )
            return

        self.cameras[camera.camera_id] = camera
        self.camera_stats[camera.camera_id] = CameraStats()
        self._previous_camera_status[camera.camera_id] = "CONNECTING"
        if self.camera_manager is None:
            self.statusBar().showMessage("Camera engine is still initializing; please try again in a moment.", 3000)
            return
        try:
            self.camera_manager.start_camera(camera)
        except Exception as error:
            self._set_camera_status(camera.camera_id, "ERROR", str(error))
        self.repository.add_notification(
            "camera_added",
            f"{camera.name} ({camera.camera_id}) added; connecting to external source.",
        )
        self._sync_cameras()
        self.statusBar().showMessage(f"Added {camera.name}; connecting to the configured source.", 6000)

    def _remove_camera(self, camera_id: str) -> None:
        camera = self.cameras.get(camera_id)
        if camera is None:
            return
        self._in_app_overlay.show_confirmation(
            "Remove camera?",
            f"Remove {camera.name} ({camera.camera_id}) and its saved connection credentials?",
            lambda identifier=camera_id: self._confirm_remove_camera(identifier),
        )

    def _confirm_remove_camera(self, camera_id: str) -> None:
        camera = self.cameras.get(camera_id)
        if camera is None:
            return
        if self.camera_manager is not None:
            self.camera_manager.stop_camera(camera_id)
        self.repository.remove_camera(camera_id)
        try:
            self.vault.delete(camera_id)
        except Exception:
            self.statusBar().showMessage(
                "Camera removed, but its saved credentials could not be deleted from the OS vault.",
                10000,
            )
        self.cameras.pop(camera_id, None)
        self.camera_stats.pop(camera_id, None)
        self._previous_camera_status.pop(camera_id, None)
        self.model_statuses.pop(camera_id, None)
        if self._camera_view_camera_id == camera_id:
            self._camera_view_camera_id = None
            self._in_app_overlay.hide()
        self.repository.add_notification("camera_removed", f"{camera.name} ({camera_id}) removed.")
        self._sync_cameras()

    def _reconnect_camera(self, camera_id: str) -> None:
        camera = self.cameras.get(camera_id)
        if camera is None:
            return
        self.camera_stats[camera_id] = CameraStats(status="CONNECTING")
        if self.camera_manager is None:
            self.statusBar().showMessage("Camera engine is still initializing; please try again in a moment.", 3000)
            return
        self.camera_manager.reconnect(camera_id, camera)
        self._sync_cameras()

    def _set_camera_ai(self, camera_id: str, enabled: bool) -> None:
        camera = self.cameras.get(camera_id)
        if camera is None:
            return
        updated = replace(camera, ai_enabled=enabled)
        self.cameras[camera_id] = updated
        self.repository.set_camera_ai(camera_id, enabled)
        if self.camera_manager is not None:
            self.camera_manager.set_camera_ai(camera_id, enabled)
        self._sync_cameras()

    # ------------------------------------------------------------------
    # Settings, theme, operator, search
    # ------------------------------------------------------------------
    def _save_settings(self, settings: AppSettings) -> None:
        # Apply settings in-place. Rebuilding the information pages on every
        # checkbox/dropdown click was causing the settings UI to feel laggy.
        self.settings = AppSettings.from_dict(settings.to_dict())
        self.repository.save_settings(self.settings)
        if self.camera_manager is not None:
            self.camera_manager.set_settings(self.settings)
        apply_theme(self, self.settings.theme)
        self.top_bar.set_theme(self.settings.theme)
        self.dashboard.update_model_configuration(self.settings)
        self.settings_page.set_theme(self.settings.theme)
        self.settings_page.set_saved()
        self.statusBar().showMessage("Settings saved and applied to camera workers.", 1800)

    def _switch_violence_model(self, model_key: str) -> None:
        allowed = {"fdsc_mc3", "mc3", "x3d"}
        if model_key not in allowed:
            return
        values = self.settings.to_dict()
        values["violence_model"] = model_key
        updated = AppSettings.from_dict(values)
        self.settings = updated
        self.repository.save_settings(updated)
        if self.camera_manager is not None:
            self.camera_manager.set_settings(updated)
        self.dashboard.update_model_configuration(updated)
        self.settings_page.set_saved()
        self.statusBar().showMessage(
            f"AI engine switched to {self._model_display_name(model_key)}.",
            3000,
        )

    @staticmethod
    def _model_display_name(model_key: str) -> str:
        return {
            "fdsc_mc3": "Spontim 1.0",
            "mc3": "CampusGuard MC3-18",
            "x3d": "X3D-M",
        }.get(model_key, model_key)

    def _rebuild_information_pages(self) -> None:
        current_key = None
        for key, page in self.info_pages.items():
            if self.stack.currentWidget() is page:
                current_key = key
            self.stack.removeWidget(page)
            page.deleteLater()

        self.info_pages = self._build_information_pages()
        for key, page in self.info_pages.items():
            self.stack.addWidget(page)
            self._pages[key] = page

        if current_key:
            self.navigate(current_key)

    def _toggle_theme(self) -> None:
        theme = "light" if self.settings.theme == "dark" else "dark"
        values = self.settings.to_dict()
        values["theme"] = theme
        self._save_settings(AppSettings.from_dict(values))

    def _toggle_operator(self) -> None:
        if self.operator_name:
            self.operator_name = None
            self._update_operator_button()
            return
        name, accepted = QInputDialog.getText(
            self,
            "Local operator session",
            "Operator display name:",
        )
        if accepted and name.strip():
            self.operator_name = name.strip()
            self._update_operator_button()

    def _update_operator_button(self) -> None:
        self.top_bar.set_operator(self.operator_name)

    def _run_global_search(self, query: str) -> None:
        self.incidents_page.search_input.setText(query.strip())
        self.navigate("incidents")

    # ------------------------------------------------------------------
    # Camera runtime callbacks
    # ------------------------------------------------------------------
    def _on_camera_status(self, camera_id: str, status: str, message: str) -> None:
        self._set_camera_status(camera_id, status, message)

    def _set_camera_status(self, camera_id: str, status: str, message: str) -> None:
        if camera_id not in self.cameras:
            return
        previous = self._previous_camera_status.get(camera_id)
        self.camera_stats[camera_id] = replace(
            self.camera_stats.get(camera_id, CameraStats()),
            status=status,
            message=message,
        )
        self._previous_camera_status[camera_id] = status

        camera = self.cameras.get(camera_id)
        if camera and status == "LIVE" and previous != "LIVE":
            self.repository.add_notification(
                "camera_connected",
                f"{camera.name} ({camera_id}) is live.",
            )
        elif camera and status in {"OFFLINE", "ERROR"} and previous == "LIVE":
            self.repository.add_notification(
                "camera_disconnected",
                f"{camera.name} ({camera_id}) disconnected.",
            )

        self.camera_page.update_camera_stats(
            camera_id,
            self.camera_stats[camera_id],
        )
        self.dashboard.update_camera_stats(
            camera_id,
            self.camera_stats[camera_id],
        )
        if self._camera_view_camera_id == camera_id:
            self._in_app_overlay.set_camera_stats(self.camera_stats[camera_id])
        if message:
            self.statusBar().showMessage(f"{camera_id}: {message}", 8000)

    def _on_camera_stats(self, camera_id: str, fps: float, resolution: str) -> None:
        if camera_id not in self.cameras:
            return
        stats = replace(
            self.camera_stats.get(camera_id, CameraStats()),
            fps=fps,
            resolution=resolution,
        )
        self.camera_stats[camera_id] = stats
        self.camera_page.update_camera_stats(camera_id, stats)
        self.dashboard.update_camera_stats(camera_id, stats)
        if self._camera_view_camera_id == camera_id:
            self._in_app_overlay.set_camera_stats(stats)

    def _on_frame(self, camera_id: str, image, state: str, confidence) -> None:
        self.dashboard.update_frame(camera_id, image, state, confidence)
        if self._camera_view_camera_id == camera_id:
            self._in_app_overlay.set_camera_frame(image, state, confidence)

    def _on_model_status(self, camera_id: str, component: str, message: str) -> None:
        if camera_id not in self.cameras:
            return
        self.model_statuses.setdefault(camera_id, {})[component] = message
        self.dashboard.update_model_status(camera_id, component, message)
        if component == "device":
            self.settings_page.set_device_status(message)

    def _on_event(
        self,
        camera_id: str,
        event: str,
        confidence: float,
        severity: str,
    ) -> None:
        camera = self.cameras.get(camera_id)
        if camera is None:
            return
        incident = self.repository.create_incident(
            camera,
            event,
            confidence,
            severity,
            self.settings.alert_cooldown_seconds,
        )
        if incident is None:
            return
        self._pending_footage_incidents[camera_id] = str(
            incident["public_id"]
        )
        self.statusBar().showMessage(
            f"{severity} alert: {event} on {camera.name} ({confidence:.0%}).",
            12000,
        )
        self.incidents_page.refresh()
        self.alerts_page.refresh()
        self.dashboard.refresh_summary()
        self._update_alert_badge()

    # ------------------------------------------------------------------
    # Incidents / alerts
    # ------------------------------------------------------------------
    def _on_footage_saved(self, camera_id: str, footage_path: str) -> None:
        public_id = self._pending_footage_incidents.pop(camera_id, None)
        if public_id is None:
            return
        self.repository.attach_incident_footage(public_id, footage_path)
        self.incidents_page.refresh()
        self.alerts_page.refresh()
        self.statusBar().showMessage(
            f"Fight footage saved for {public_id}.",
            6000,
        )

    def _set_incident_status(self, public_id: str, status: str) -> None:
        self.repository.update_incident_status(public_id, status)
        self.incidents_page.refresh()

    def _clear_dashboard_notifications(self) -> None:
        self._in_app_overlay.show_confirmation(
            "Clear dashboard notifications?",
            "This will clear the notification list shown on the Dashboard. Incidents and alerts will not be removed.",
            self._confirm_clear_dashboard_notifications,
        )

    def _confirm_clear_dashboard_notifications(self) -> None:
        self.repository.clear_notifications()
        self.dashboard.refresh_summary()
        self.statusBar().showMessage(
            "Dashboard notifications cleared.",
            4000,
        )

    def _clear_footage_storage(self) -> None:
        self._in_app_overlay.show_confirmation(
            "Clear saved footage?",
            "This permanently deletes saved fight MP4 footage. Incident and alert records will remain.",
            self._confirm_clear_footage,
        )

    def _confirm_clear_footage(self) -> None:
        removed = clear_footage(self.repository.footage_dir)
        self.repository.clear_incident_footage_paths()
        self.incidents_page.refresh()
        self.alerts_page.refresh()
        self.statusBar().showMessage(
            f"Saved footage cleared ({removed} video{'s' if removed != 1 else ''}).",
            5000,
        )

    def _clear_all_history(self) -> None:
        self._in_app_overlay.show_confirmation(
            "Clear all history and alerts?",
            "This permanently erases stored incidents, alerts, and notifications. Cameras and AI configuration will remain.",
            self._confirm_clear_all_history,
        )

    def _confirm_clear_all_history(self) -> None:
        self.repository.clear_all_incidents_alerts_notifications()
        self._pending_footage_incidents.clear()
        self.incidents_page.refresh()
        self.alerts_page.refresh()
        self.dashboard.refresh_summary()
        self._update_alert_badge()
        self.statusBar().showMessage(
            "All incidents, alerts, and notifications were cleared.",
            5000,
        )

    def _update_alert_badge(self) -> None:
        self.bottom_bar.set_badge("alerts", self.repository.active_alert_count())

    def _sync_cameras(self) -> None:
        cameras = list(self.cameras.values())
        self.dashboard.sync_cameras(cameras)
        self.camera_page.sync_cameras(cameras, self.camera_stats)
        self.dashboard.refresh_summary()

    def _refresh_pages(self) -> None:
        self.dashboard.refresh_summary()
        self._update_alert_badge()

    def closeEvent(self, event) -> None:
        if self.camera_manager is not None:
            self.camera_manager.stop_all(timeout_ms=5000)
        event.accept()
