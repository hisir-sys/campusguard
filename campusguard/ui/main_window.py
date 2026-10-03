from __future__ import annotations

from dataclasses import replace

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from campusguard.camera_runtime import CameraManager
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

        # Pick the icon/palette theme before any widget is built so nothing flashes.
        set_icon_theme(self.settings.theme)

        self.camera_manager = CameraManager(self.vault, self)
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
        self.info_pages = {
            "services": self._make_info_page(
                "Services",
                "Local camera monitoring, object detection, pose estimation, incident recording, and alert review.",
                "server",
                [
                    "External camera capture through OpenCV",
                    "Local YOLO person detection and ByteTrack tracking",
                    "Optional YOLO Pose skeleton overlays",
                    "Optional MC3-18 temporal action classification",
                    "SQLite incident and alert history",
                ],
            ),
            "about": self._make_info_page(
                "About CampusGuard",
                "CampusGuard is a local-first security operations tool for monitoring configured campus camera sources. "
                "It does not perform facial recognition or identify people.",
                "shield",
                [
                    "Camera credentials are stored through the operating system credential vault.",
                    "Incidents and settings are stored in a local SQLite database.",
                    "Video processing runs locally in background worker threads.",
                    "No feeds, detections, or confidence scores are generated when a model is missing.",
                ],
            ),
            "tools": self._make_info_page(
                "Tools",
                "Review model availability and manage camera connections from their dedicated pages.",
                "cpu",
                [
                    "Camera connection test: Cameras → Add camera → Test Connection",
                    "Model paths and compute device: Settings → Model Files",
                    "Persistent people IDs: enable tracking and provide YOLO weights.",
                    "The detector, pose model, and action classifier each report their own load status.",
                ],
            ),
            "how-it-works": self._make_info_page(
                "How It Works",
                "Every stage uses frames from a configured camera and outputs from loaded local models.",
                "activity",
                [
                    "Camera → OpenCV capture",
                    "Frame → YOLO person detection",
                    "Detections → ByteTrack persistent IDs",
                    "Frame → YOLO Pose keypoints and skeleton overlay",
                    "16-frame clip → MC3-18 action score",
                    "Stable model result → cooldown-checked SQLite incident → alert",
                ],
            ),
        }
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

    @staticmethod
    def _make_info_page(title: str, description: str, icon: str, bullets: list[str]) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        layout.addWidget(make_page_title(title, description))
        card, body = make_card("Highlights", icon=icon)
        for text in bullets:
            label = QLabel(f"•  {text}")
            label.setWordWrap(True)
            label.setStyleSheet("padding: 4px 0;")
            body.addWidget(label)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

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
        self.incidents_page.status_change_requested.connect(self._set_incident_status)
        self.alerts_page.acknowledge_requested.connect(self._acknowledge_alert)
        self.settings_page.settings_changed.connect(self._save_settings)

    def _connect_camera_manager(self) -> None:
        self.camera_manager.camera_status_changed.connect(self._on_camera_status)
        self.camera_manager.camera_stats_changed.connect(self._on_camera_stats)
        self.camera_manager.frame_ready.connect(self._on_frame)
        self.camera_manager.model_status_changed.connect(self._on_model_status)
        self.camera_manager.event_detected.connect(self._on_event)

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
        self.dashboard.update_model_configuration(self.settings)
        self.settings_page.set_theme(self.settings.theme)
        self.settings_page.set_saved()
        self.statusBar().showMessage("Settings saved and applied to camera workers.", 3000)

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
    def _set_incident_status(self, public_id: str, status: str) -> None:
        self.repository.update_incident_status(public_id, status)
        self.incidents_page.refresh()

    def _acknowledge_alert(self, alert_id: int) -> None:
        self.repository.acknowledge_alert(alert_id)
        self.alerts_page.refresh()
        self.dashboard.refresh_summary()
        self._update_alert_badge()

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
