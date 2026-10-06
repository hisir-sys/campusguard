from __future__ import annotations

from dataclasses import replace

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QScrollArea,
    QMessageBox,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from campusguard.camera_runtime import CameraManager
from campusguard.footage import clear_footage
from campusguard.credentials import CredentialVault
from campusguard.settings import (
    AppSettings,
    CameraConfig,
    CameraCredentials,
    CameraStats,
)
from campusguard.storage import Repository
from campusguard.ui.camera_page import CamerasPage
from campusguard.ui.common import (
    EnlargedCameraDialog,
    apply_theme,
    make_card,
    make_page_title,
)
from campusguard.ui.dashboard_page import DashboardPage
from campusguard.ui.glass_nav import BackdropWidget, BottomBar, TopBar
from campusguard.ui.history_pages import AlertsPage, IncidentsPage
from campusguard.ui.icons import set_icon_theme
from campusguard.ui.settings_page import SettingsPage
from campusguard.ui.theme import get_palette


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
        self._camera_dialogs: dict[str, EnlargedCameraDialog] = {}
        self.operator_name: str | None = None
        self._pending_footage_incidents: dict[str, str] = {}

        # Pick the icon/palette theme before any widget is built so nothing flashes.
        set_icon_theme(self.settings.theme)

        self.camera_manager = CameraManager(self.vault, self.repository.footage_dir, self)
        self.camera_manager.set_settings(self.settings)
        self._connect_camera_manager()
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

        for camera in self.cameras.values():
            try:
                self.camera_manager.start_camera(camera)
            except Exception as error:
                self._set_camera_status(
                    camera.camera_id,
                    "ERROR",
                    f"Camera could not start: {error}",
                )

        self._add_shortcut("Ctrl+1", lambda: self.navigate("dashboard"))
        self._add_shortcut("Ctrl+2", lambda: self.navigate("cameras"))
        self._add_shortcut("Ctrl+3", lambda: self.navigate("incidents"))
        self._add_shortcut("Ctrl+4", lambda: self.navigate("alerts"))
        self._add_shortcut("Ctrl+5", lambda: self.navigate("settings"))
        self._add_shortcut("Ctrl+K", self.top_bar.focus_search)

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
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.top_bar = TopBar()
        top_row = QHBoxLayout()
        top_row.setContentsMargins(18, 14, 18, 4)
        top_row.addWidget(self.top_bar)
        outer.addLayout(top_row)

        self.stack = QStackedWidget()
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
        outer.addWidget(self.stack, 1)

        self.bottom_bar = BottomBar()
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(18, 4, 18, 14)
        bottom_row.addWidget(self.bottom_bar)
        outer.addLayout(bottom_row)

        self.setCentralWidget(central)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().showMessage("Ready — no sample cameras or simulated detections are loaded.")
        self._connect_pages()


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
        scroll.setWidget(content)
        return scroll

    @staticmethod
    def _section_header(title: str, description: str) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(7)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 18pt; font-weight: 700;")
        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setStyleSheet("font-size: 10pt; color: palette(mid);")
        layout.addWidget(title_label)
        layout.addWidget(description_label)
        return box

    @staticmethod
    def _tech_card(title: str, subtitle: str, body: str, icon: str | None = None) -> QWidget:
        card, body_layout = make_card(title, icon=icon)
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
        layout.setContentsMargins(16, 14, 18, 14)
        layout.setSpacing(14)

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

        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text_column, 1)
        return node

    @staticmethod
    def _flow_arrow() -> QWidget:
        wrapper = QWidget()
        wrapper.setFixedHeight(26)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(34, 0, 0, 0)
        layout.setSpacing(0)

        line = QFrame()
        line.setFixedWidth(1)
        line.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")

        arrow = QLabel("↓")
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow.setStyleSheet(
            "font-size: 13pt; font-weight: 700; "
            "color: palette(mid); background: transparent; border: none;"
        )

        layout.addWidget(line, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(arrow, 0, Qt.AlignmentFlag.AlignCenter)
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
            "Camera acquisition, AI processing, incident persistence, alert review, and operator controls are separated into dedicated modules.",
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
            "Camera configuration, settings, notifications, incidents, and alert state are stored locally.",
        ), 1)
        row.addWidget(self._tech_card(
            "Camera security", "OS credential vault",
            "Configured camera credentials are handled through the operating-system credential vault.",
        ), 1)
        layout.addLayout(row)

        card, body = make_card("Technical boundaries", icon="activity")
        boundaries = (
            ("Camera layer", "Reads frames and reports connection state, FPS, resolution, and runtime errors."),
            ("AI layer", "Loads configured local models and reports component-level model status."),
            ("Event layer", "Converts stable model results into cooldown-controlled incidents and alerts."),
            ("Operations layer", "Presents cameras, incidents, alerts, and settings without replacing the processing pipeline."),
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
            ("01", "External Camera Service", "USB / RTSP / HTTP / IP",
             "Accepts configured external camera sources and exposes a consistent runtime interface."),
            ("02", "Frame Processing", "CameraRuntime",
             "Reads frames, maintains connection state, measures stream statistics, and forwards frames for optional AI processing."),
            ("03", "Person Detection", "YOLO",
             "Finds people in individual frames and supplies bounding boxes and confidence values."),
            ("04", "Object Tracking", "Persistent IDs",
             "Associates detections across consecutive frames so movement can be analyzed over time."),
            ("05", "Pose Analysis", "Keypoints / skeleton",
             "Uses configured pose-model output to expose body keypoints and movement structure."),
            ("06", "Temporal Classification", "MC3-18",
             "Evaluates a short frame sequence so motion-based events can be represented as temporal model results."),
            ("07", "Incident Service", "SQLite repository",
             "Creates an incident from a stable event with camera, event, confidence, severity, and status."),
            ("08", "Alert Service", "Operator review",
             "Surfaces active events, applies configured cooldown behavior, and provides acknowledgement controls."),
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
            ("Camera Manager", "Connection and lifecycle",
             "Add, test, reconnect, remove, and monitor configured external camera sources."),
            ("AI Model Configuration", "Model availability",
             "Review detector, pose, temporal classifier, model paths, and compute-device status."),
            ("Person Detection", "Frame-level analysis",
             "Produces person bounding boxes and confidence information when the detector is available."),
            ("Tracking", "Cross-frame association",
             "Associates detections across frames so movement can be analyzed as a continuous track."),
            ("Pose / Skeleton", "Body keypoints",
             "Represents pose information as keypoints and skeleton data when configured."),
            ("Temporal Action Analysis", "Sequence-level analysis",
             "Uses a frame clip to classify motion patterns with the configured temporal model."),
            ("Incident History", "Evidence index",
             "Search and review stored incidents, severity, confidence, status, and camera source."),
            ("Alert Console", "Active response",
             "Review active alerts and acknowledge them from the Alerts page."),
            ("System Settings", "Runtime control",
             "Configure model locations, compute settings, thresholds, and alert cooldown behavior."),
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
            ("01", "External Camera", "USB / RTSP / HTTP / IP",
             "A configured external camera becomes the source of frames."),
            ("02", "Camera Runtime", "OpenCV capture",
             "The runtime opens the source, reads frames, reports LIVE/OFFLINE/ERROR, and measures FPS and resolution."),
            ("03", "Frame Preparation", "Runtime handoff",
             "Frames enter the AI path only when AI processing is enabled and the relevant model configuration is available."),
            ("04", "Person Detection", "YOLO bounding boxes",
             "The detector identifies people and provides bounding boxes and confidence values."),
            ("05", "Tracking", "Persistent person IDs",
             "Detections are associated across frames so movement can be analyzed continuously."),
            ("06", "Pose Estimation", "Keypoints / skeleton",
             "A configured pose model can produce body keypoints describing posture and movement structure."),
            ("07", "Temporal Buffer", "Consecutive frames",
             "A short sequence is accumulated for temporal analysis; the current application describes the action classifier as using a 16-frame clip."),
            ("08", "Temporal Classification", "MC3-18 action score",
             "The temporal model produces an action score from the clip rather than a single image."),
            ("09", "Event Stability", "Confidence + cooldown",
             "The event result and configured cooldown behavior are applied before persistent incident creation."),
            ("10", "Incident Persistence", "SQLite",
             "A created incident records camera, event, confidence, severity, and operational status."),
            ("11", "Alert Surface", "Alerts + notifications",
             "The event is reflected in incident and alert views for operator inspection and acknowledgement."),
            ("12", "Operations UI", "Dashboard / Cameras / Incidents / Alerts",
             "The desktop interface presents live state, model state, incidents, alerts, and configuration."),
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
            "CampusGuard reports model availability component-by-component. If a model is missing, "
            "the application should report that status rather than inventing detections or confidence "
            "scores. AI behavior therefore depends on the model files configured in Settings."
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
        self.camera_page.add_requested.connect(self._add_camera)
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
        dialog = self._camera_dialogs.get(camera_id)
        if dialog is None:
            dialog = EnlargedCameraDialog(camera, self)
            self._camera_dialogs[camera_id] = dialog
            dialog.finished.connect(
                lambda _result, identifier=camera_id:
                self._camera_dialogs.pop(identifier, None)
            )
            dialog.show()
        else:
            dialog.raise_()
            dialog.activateWindow()
        dialog.set_camera_stats(self.camera_stats.get(camera_id, CameraStats()))

    # ------------------------------------------------------------------
    # Cameras
    # ------------------------------------------------------------------
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
        dialog = self._camera_dialogs.pop(camera_id, None)
        if dialog:
            dialog.close()
        self.repository.add_notification("camera_removed", f"{camera.name} ({camera_id}) removed.")
        self._sync_cameras()

    def _reconnect_camera(self, camera_id: str) -> None:
        camera = self.cameras.get(camera_id)
        if camera is None:
            return
        self.camera_stats[camera_id] = CameraStats(status="CONNECTING")
        self.camera_manager.reconnect(camera_id, camera)
        self._sync_cameras()

    def _set_camera_ai(self, camera_id: str, enabled: bool) -> None:
        camera = self.cameras.get(camera_id)
        if camera is None:
            return
        updated = replace(camera, ai_enabled=enabled)
        self.cameras[camera_id] = updated
        self.repository.set_camera_ai(camera_id, enabled)
        self.camera_manager.set_camera_ai(camera_id, enabled)
        self._sync_cameras()

    # ------------------------------------------------------------------
    # Settings, theme, operator, search
    # ------------------------------------------------------------------
    def _save_settings(self, settings: AppSettings) -> None:
        self.settings = AppSettings.from_dict(settings.to_dict())
        self.repository.save_settings(self.settings)
        self.camera_manager.set_settings(self.settings)
        apply_theme(self, self.settings.theme)
        self.top_bar.set_theme(self.settings.theme)
        self._rebuild_information_pages()
        self.dashboard.update_model_configuration(self.settings)
        self.settings_page.set_theme(self.settings.theme)
        self.settings_page.set_saved()
        self.statusBar().showMessage("Settings saved and applied to camera workers.", 3000)

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
        dialog = self._camera_dialogs.get(camera_id)
        if dialog:
            dialog.set_camera_stats(self.camera_stats[camera_id])
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
        dialog = self._camera_dialogs.get(camera_id)
        if dialog:
            dialog.set_camera_stats(stats)

    def _on_frame(self, camera_id: str, image, state: str, confidence) -> None:
        self.dashboard.update_frame(camera_id, image, state, confidence)
        dialog = self._camera_dialogs.get(camera_id)
        if dialog:
            dialog.set_frame(image, state, confidence)

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
        answer = QMessageBox.question(
            self,
            "Clear dashboard notifications?",
            "This will clear the notification list shown on the Dashboard. "
            "Incidents and alerts will not be removed.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.repository.clear_notifications()
        self.dashboard.refresh_summary()
        self.statusBar().showMessage(
            "Dashboard notifications cleared.",
            4000,
        )

    def _clear_footage_storage(self) -> None:
        answer = QMessageBox.warning(
            self,
            "Clear saved footage?",
            "This will permanently delete all saved fight MP4 footage. "
            "Incident and alert records will remain.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        removed = clear_footage(self.repository.footage_dir)
        self.repository.clear_incident_footage_paths()
        self.incidents_page.refresh()
        self.alerts_page.refresh()
        self.statusBar().showMessage(
            f"Saved footage cleared ({removed} video{'s' if removed != 1 else ''}).",
            5000,
        )

    def _clear_all_history(self) -> None:
        answer = QMessageBox.warning(
            self,
            "Clear all history and alerts?",
            "This will permanently erase all stored incidents, alerts, and notifications. "
            "It will not remove cameras or model settings.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

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
        self.camera_manager.stop_all(timeout_ms=5000)
        event.accept()
