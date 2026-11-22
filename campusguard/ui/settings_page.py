# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
from __future__ import annotations

import dataclasses
import threading


from PySide6.QtCore import QEvent, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QLineEdit,
    QPlainTextEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from campusguard import auth_config
from campusguard.settings import START_PAGES, AppSettings
from campusguard.ui.common import make_page_title
from campusguard.ui.v3widgets import Segmented


class SettingsSection(QFrame):
    """Small visual wrapper used only by the settings page."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        heading = QLabel(title)
        heading.setStyleSheet("font-size: 13px; font-weight: 600; letter-spacing: 0px;")
        layout.addWidget(heading)

        if subtitle:
            description = QLabel(subtitle)
            description.setWordWrap(True)
            description.setProperty("muted", True)
            layout.addWidget(description)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        layout.addLayout(self.body)


class SettingsPage(QWidget):
    settings_changed = Signal(object)
    server_connection_test_requested = Signal(str, str)
    server_token_changed = Signal(str)
    update_check_requested = Signal()
    export_report_requested = Signal()
    whatsapp_token_changed = Signal(str)
    trend_report_requested = Signal()
    set_pin_requested = Signal(str, str)
    test_alert_requested = Signal()
    silent_report_requested = Signal()
    _profile_loaded = Signal(object, str)  # (profile dict or None, message)

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._updating = False
        self._initial_settings = settings

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 28)
        root.setSpacing(24)

        header = QHBoxLayout()
        header.setSpacing(16)

        header.addWidget(
            make_page_title(
                "System settings",
                "Configure detection, camera behavior, compute resources, and the CampusGuard appearance.",
            ),
            1,
        )

        self.status_pill = QLabel("System controls")
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_pill.setMinimumHeight(30)
        self.status_pill.setStyleSheet(
            """
            QLabel {
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 15px;
                padding: 0 12px;
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 0px;
            }
            """
        )
        header.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)
        self.status_pill.hide()
        self.tabs = Segmented(["General", "Appearance", "Detection", "Alerts", "Storage", "Connection", "Help"], "General")
        self.tabs.changed.connect(self._show_tab)
        tab_row = QHBoxLayout()
        tab_row.addWidget(self.tabs)
        tab_row.addStretch(1)
        root.addLayout(tab_row)

        scroll = self.scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 2, 4, 16)
        content_layout.setSpacing(12)

        # ------------------------------------------------------------------
        # AI ENGINE
        # ------------------------------------------------------------------
        ai_section = SettingsSection(
            "AI engine",
            "Control the live detection pipeline and how aggressively CampusGuard reacts to detected activity.",
        )

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(16)

        self.threshold_input = QDoubleSpinBox()
        self.threshold_input.setRange(0.05, 0.99)
        self.threshold_input.setSingleStep(0.01)
        self.threshold_input.setDecimals(2)
        self.threshold_input.setSuffix(" confidence")
        self.threshold_input.setValue(settings.confidence_threshold)

        self.detection_toggle = QCheckBox("Run person detection")
        self.detection_toggle.setChecked(settings.detection_enabled)

        self.tracking_toggle = QCheckBox("Assign persistent ByteTrack IDs")
        self.tracking_toggle.setChecked(settings.tracking_enabled)

        self.pose_toggle = QCheckBox("Run pose estimation and draw skeleton")
        self.pose_toggle.setChecked(settings.pose_enabled)

        self.cooldown_input = QSpinBox()
        self.cooldown_input.setRange(0, 3600)
        self.cooldown_input.setSuffix(" seconds")
        self.cooldown_input.setValue(settings.alert_cooldown_seconds)

        self.reconnect_toggle = QCheckBox("Reconnect camera sources automatically")
        self.reconnect_toggle.setChecked(settings.auto_reconnect)

        self.device_input = QComboBox()
        self.device_input.addItem("Auto", "auto")
        self.device_input.addItem("CPU", "cpu")
        self.device_input.addItem("CUDA", "cuda")
        index = self.device_input.findData(settings.device)
        self.device_input.setCurrentIndex(max(0, index))

        self.device_status = QLabel("CUDA availability will be reported by the AI worker.")
        self.device_status.setWordWrap(True)
        self.device_status.setProperty("muted", True)

        self.model_label = QLabel("Spontim 1.0 (MC3-18 fight classifier)")
        self.model_label.setProperty("muted", True)
        form.addRow("Detection model", self.model_label)
        form.addRow("Minimum confidence", self.threshold_input)
        form.addRow("Person detection", self.detection_toggle)
        form.addRow("Tracking", self.tracking_toggle)
        form.addRow("Pose overlay", self.pose_toggle)
        form.addRow("Alert cooldown", self.cooldown_input)
        form.addRow("Camera reconnect", self.reconnect_toggle)
        form.addRow("Compute device", self.device_input)
        form.addRow("", self.device_status)

        for row in range(form.rowCount()):
            label_item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            label_widget = label_item.widget() if label_item is not None else None
            if label_widget is not None:
                label_widget.setMinimumWidth(168)
                label_widget.setProperty("settingsLabel", True)
                label_widget.style().unpolish(label_widget)
                label_widget.style().polish(label_widget)

        ai_section.body.addLayout(form)
        content_layout.addWidget(ai_section)

        # ------------------------------------------------------------------
        # APPEARANCE
        # ------------------------------------------------------------------
        appearance_section = SettingsSection(
            "Appearance",
            "Choose the visual theme used across the CampusGuard desktop interface.",
        )

        theme_row = QHBoxLayout()
        theme_row.setSpacing(16)

        theme_label = QLabel("Interface theme")
        theme_label.setMinimumWidth(168)

        self.theme_input = QComboBox()
        self.theme_input.addItem("Dark", "dark")
        self.theme_input.addItem("Light", "light")
        self.theme_input.setCurrentIndex(
            max(0, self.theme_input.findData(settings.theme))
        )

        theme_row.addWidget(theme_label)
        theme_row.addWidget(self.theme_input, 0)
        theme_row.addStretch(1)

        self.save_label = QLabel("Changes save locally as they are applied.")
        self.save_label.setProperty("muted", True)
        theme_row.addWidget(self.save_label)

        appearance_section.body.addLayout(theme_row)
        content_layout.addWidget(appearance_section)

        # ------------------------------------------------------------------
        # ALERTS & WORKSPACE
        # ------------------------------------------------------------------
        workspace_section = SettingsSection(
            "Alerts and workspace",
            "Sound, start-up page and navigation behaviour.",
        )
        workspace_form = QFormLayout()
        workspace_form.setHorizontalSpacing(24)
        workspace_form.setVerticalSpacing(14)
        self.alert_sound_toggle = QCheckBox("Play an alarm sound when an incident is raised")
        self.alert_sound_toggle.setChecked(settings.alert_sound_enabled)
        self.start_page_input = QComboBox()
        for page in START_PAGES:
            self.start_page_input.addItem(page.title(), page)
        self.start_page_input.setCurrentIndex(max(0, self.start_page_input.findData(settings.start_page)))
        self.sidebar_hover_toggle = QCheckBox("Open the navigation panel when hovering Home")
        self.sidebar_hover_toggle.setChecked(settings.sidebar_hover_open)
        self.confirm_input = QComboBox()
        for label, value in (("Fast: 2 readings (about 1 second)", 2), ("Balanced: 3 readings", 3), ("Careful: 4 readings", 4), ("Very careful: 6 readings", 6)):
            self.confirm_input.addItem(label, value)
        self.confirm_input.setCurrentIndex(max(0, self.confirm_input.findData(settings.alert_confirm_predictions)))
        self.confirm_input.currentIndexChanged.connect(self._emit_settings)
        self.gpu_decode_toggle = QCheckBox("Decode camera video on the GPU (NVIDIA; falls back if unavailable)")
        self.gpu_decode_toggle.setChecked(settings.gpu_video_decode)
        self.gpu_decode_toggle.toggled.connect(self._emit_settings)
        self.reset_button = QPushButton("Reset all settings to defaults")
        workspace_form.addRow("Alarm sound", self.alert_sound_toggle)
        workspace_form.addRow("Open on start", self.start_page_input)
        workspace_form.addRow("Alert confirmation", self.confirm_input)
        workspace_form.addRow("Performance", self.gpu_decode_toggle)
        workspace_form.addRow("Navigation", self.sidebar_hover_toggle)
        workspace_form.addRow("", self.reset_button)
        workspace_section.body.addLayout(workspace_form)
        content_layout.addWidget(workspace_section)
        self.alert_sound_toggle.toggled.connect(self._emit_settings)
        self.start_page_input.currentIndexChanged.connect(self._emit_settings)
        self.sidebar_hover_toggle.toggled.connect(self._emit_settings)
        self.reset_button.clicked.connect(self._reset_defaults)

        # ------------------------------------------------------------------
        # PHONE ALERTS
        # ------------------------------------------------------------------
        phone_section = SettingsSection(
            "Phone alerts",
            "Send the camera, time, place and confidence of an incident to phones. WhatsApp can be free (you tap Send) or automatic (needs a Meta Business account).",
        )
        phone_form = QFormLayout()
        phone_form.setHorizontalSpacing(24)
        phone_form.setVerticalSpacing(12)
        self.alert_numbers_input = QLineEdit(settings.alert_numbers)
        self.alert_numbers_input.setPlaceholderText("98765 43210, 98765 00000  (up to 10 numbers)")
        self.escalation_numbers_input = QLineEdit(settings.escalation_numbers)
        self.escalation_numbers_input.setPlaceholderText("Backup people, alerted only if nobody responds")
        self.building_numbers_input = QPlainTextEdit(settings.building_numbers)
        self.building_numbers_input.setPlaceholderText(
            "One building per line, matching the camera's Group:\nScience Block: 98765 43210\nJunior Wing: 98765 00000, 98765 11111"
        )
        self.building_numbers_input.setFixedHeight(84)
        self.health_numbers_input = QLineEdit(settings.health_numbers)
        self.health_numbers_input.setPlaceholderText("IT / admin people told when cameras go offline or the disk is nearly full")
        self.health_offline_input = QSpinBox()
        self.health_offline_input.setRange(1, 120)
        self.health_offline_input.setSuffix(" min offline")
        self.health_offline_input.setValue(settings.health_offline_minutes)
        self.escalate_input = QSpinBox()
        self.escalate_input.setRange(0, 60)
        self.escalate_input.setSuffix(" min  (0 = never)")
        self.escalate_input.setValue(settings.escalate_minutes)
        self.min_severity_input = QComboBox()
        for label, value in (("Low and above", "LOW"), ("Alert and above", "MEDIUM"), ("Critical alert and above", "HIGH"), ("Danger only", "CRITICAL")):
            self.min_severity_input.addItem(label, value)
        self.min_severity_input.setCurrentIndex(max(0, self.min_severity_input.findData(settings.alert_min_severity)))
        self.whatsapp_mode_input = QComboBox()
        self.whatsapp_mode_input.addItem("Off", "off")
        self.whatsapp_mode_input.addItem("Free: open WhatsApp with the message ready (tap Send)", "link")
        self.whatsapp_mode_input.addItem("Automatic: WhatsApp Business Cloud API (Meta account needed)", "cloud")
        self.whatsapp_mode_input.setCurrentIndex(max(0, self.whatsapp_mode_input.findData(settings.whatsapp_mode)))
        self.auto_open_whatsapp_toggle = QCheckBox("Open WhatsApp automatically when a Critical or Danger alert is raised")
        self.auto_open_whatsapp_toggle.setChecked(settings.auto_open_whatsapp)
        self.country_code_input = QLineEdit(settings.country_code)
        self.country_code_input.setMaximumWidth(80)
        self.country_code_input.setPlaceholderText("91")
        self.whatsapp_phone_id_input = QLineEdit(settings.whatsapp_phone_id)
        self.whatsapp_phone_id_input.setPlaceholderText("Cloud API phone number ID")
        self.whatsapp_template_input = QLineEdit(settings.whatsapp_template)
        self.whatsapp_template_input.setPlaceholderText("Approved template name with 4 text parameters (optional)")
        self.whatsapp_token_input = QLineEdit()
        self.whatsapp_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.whatsapp_token_input.setPlaceholderText("Access token (stored in Windows Credential Manager)")
        self.ntfy_topic_input = QLineEdit(settings.ntfy_topic)
        self.ntfy_topic_input.setPlaceholderText("Free push alerts: choose a hard-to-guess topic, install the ntfy app")
        self.ntfy_attach_toggle = QCheckBox("Attach the video clip to push alerts (leave off on public ntfy.sh)")
        self.ntfy_attach_toggle.setChecked(settings.ntfy_attach_clip)
        self.test_alert_button = QPushButton("Send a test alert")
        self.silent_mode_toggle = QCheckBox(
            "Silent test mode: detect and record, but send no pop-up, sound, phone alert or push"
        )
        self.silent_mode_toggle.setChecked(settings.silent_mode)
        self.silent_report_button = QPushButton("What did silent mode catch?")
        self.keep_awake_toggle = QCheckBox("Keep this PC awake while CampusGuard runs (a sleeping PC watches nothing)")
        self.keep_awake_toggle.setChecked(settings.keep_awake)
        for label, widget in (
            ("Silent mode", self.silent_mode_toggle),
            ("", self.silent_report_button),
            ("Stay awake", self.keep_awake_toggle),
            ("Alert numbers", self.alert_numbers_input),
            ("Building numbers", self.building_numbers_input),
            ("IT / health numbers", self.health_numbers_input),
            ("Camera offline after", self.health_offline_input),
            ("Backup numbers", self.escalation_numbers_input),
            ("Escalate after", self.escalate_input),
            ("Send alerts for", self.min_severity_input),
            ("WhatsApp", self.whatsapp_mode_input),
            ("", self.auto_open_whatsapp_toggle),
            ("Country code", self.country_code_input),
            ("Cloud phone ID", self.whatsapp_phone_id_input),
            ("Cloud template", self.whatsapp_template_input),
            ("Cloud token", self.whatsapp_token_input),
            ("Push (ntfy)", self.ntfy_topic_input),
            ("", self.ntfy_attach_toggle),
            ("", self.test_alert_button),
        ):
            phone_form.addRow(label, widget)
        phone_section.body.addLayout(phone_form)
        content_layout.addWidget(phone_section)
        self.silent_mode_toggle.toggled.connect(self._emit_settings)
        self.keep_awake_toggle.toggled.connect(self._emit_settings)
        self.silent_report_button.clicked.connect(self.silent_report_requested.emit)
        for line in (self.alert_numbers_input, self.escalation_numbers_input, self.country_code_input,
                     self.whatsapp_phone_id_input, self.whatsapp_template_input, self.ntfy_topic_input,
                     self.health_numbers_input):
            line.editingFinished.connect(self._emit_settings)
        self.building_numbers_input.installEventFilter(self)
        self.escalate_input.editingFinished.connect(self._emit_settings)
        self.health_offline_input.editingFinished.connect(self._emit_settings)
        for combo in (self.min_severity_input, self.whatsapp_mode_input):
            combo.currentIndexChanged.connect(self._emit_settings)
        for box in (self.auto_open_whatsapp_toggle, self.ntfy_attach_toggle):
            box.toggled.connect(self._emit_settings)
        self.whatsapp_token_input.editingFinished.connect(self._token_entered)
        self.test_alert_button.clicked.connect(self.test_alert_requested.emit)

        # ------------------------------------------------------------------
        # SYSTEM HEALTH & REPORTS
        # ------------------------------------------------------------------
        health_section = SettingsSection(
            "System health and reports",
            "Storage and GPU status, and an export of incidents for review.",
        )
        health_form = QFormLayout()
        health_form.setHorizontalSpacing(24)
        health_form.setVerticalSpacing(12)
        self.health_status_label = QLabel("Checking...")
        self.health_disk_label = QLabel("-")
        self.health_footage_label = QLabel("-")
        self.health_gpu_label = QLabel("-")
        for label in (self.health_status_label, self.health_disk_label, self.health_footage_label, self.health_gpu_label):
            label.setWordWrap(True)
        self.export_report_button = QPushButton("Export incident report (CSV)")
        health_form.addRow("Status", self.health_status_label)
        health_form.addRow("Footage drive", self.health_disk_label)
        health_form.addRow("Saved clips", self.health_footage_label)
        health_form.addRow("GPU", self.health_gpu_label)
        self.pin_current_input = QLineEdit()
        self.pin_current_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_current_input.setPlaceholderText("Current supervisor PIN (if one is set)")
        self.pin_new_input = QLineEdit()
        self.pin_new_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_new_input.setPlaceholderText("New supervisor PIN (4+ characters, empty removes it)")
        self.pin_button = QPushButton("Save supervisor PIN")
        self.pin_button.clicked.connect(
            lambda: self.set_pin_requested.emit(self.pin_current_input.text(), self.pin_new_input.text())
        )
        self.pin_status = QLabel("")
        self.pin_status.setProperty("muted", True)
        health_form.addRow("Evidence approval", self.pin_new_input)
        health_form.addRow("", self.pin_current_input)
        health_form.addRow("", self.pin_button)
        health_form.addRow("", self.pin_status)
        self.trend_report_button = QPushButton("Export trend report (HTML)")
        health_form.addRow("", self.export_report_button)
        health_form.addRow("", self.trend_report_button)
        health_section.body.addLayout(health_form)
        content_layout.addWidget(health_section)
        self.export_report_button.clicked.connect(self.export_report_requested.emit)
        self.trend_report_button.clicked.connect(self.trend_report_requested.emit)

        # ------------------------------------------------------------------
        # CONNECTION MODE
        # ------------------------------------------------------------------
        connection_section = SettingsSection(
            "Connection mode",
            "Local mode keeps using this PC. Server mode connects to a school server over HTTP or HTTPS. Prefer HTTPS or a trusted school LAN/VPN.",
        )
        connection_form = QFormLayout()
        connection_form.setHorizontalSpacing(24)
        connection_form.setVerticalSpacing(12)
        self.connection_mode_input = QComboBox()
        self.connection_mode_input.addItem("Local PC", "local")
        self.connection_mode_input.addItem("School server", "server")
        self.connection_mode_input.setCurrentIndex(max(0, self.connection_mode_input.findData(settings.connection_mode)))
        self.server_address_input = QLineEdit(settings.server_address)
        self.server_address_input.setPlaceholderText("https://school-server:8765")
        self.server_token_input = QLineEdit()
        self.server_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.server_token_input.setPlaceholderText("Stored securely in Windows Credential Manager")
        self.test_server_button = QPushButton("Test connection")
        self.connection_test_status = QLabel("Local mode does not contact a server.")
        self.connection_test_status.setWordWrap(True)
        self.connection_test_status.setProperty("muted", True)
        connection_form.addRow("Connection mode", self.connection_mode_input)
        connection_form.addRow("Server address", self.server_address_input)
        connection_form.addRow("Server token", self.server_token_input)
        connection_form.addRow("", self.test_server_button)
        connection_section.body.addLayout(connection_form)
        connection_section.body.addWidget(self.connection_test_status)
        content_layout.addWidget(connection_section)
        self.connection_mode_input.currentIndexChanged.connect(self._emit_settings)
        self.server_address_input.editingFinished.connect(self._emit_settings)
        self.server_token_input.textEdited.connect(self.server_token_changed.emit)
        self.test_server_button.clicked.connect(
            lambda: self.server_connection_test_requested.emit(
                self.server_address_input.text().strip(), self.server_token_input.text()
            )
        )

        # ------------------------------------------------------------------
        # SYSTEM STATUS
        # ------------------------------------------------------------------
        status_section = SettingsSection(
            "System status",
            "Current runtime information is reported by the application and AI worker.",
        )

        status_grid = QHBoxLayout()
        status_grid.setSpacing(10)

        self.detection_status = self._status_card(
            "DETECTION",
            "ENABLED" if settings.detection_enabled else "DISABLED",
        )
        self.tracking_status = self._status_card(
            "TRACKING",
            "ENABLED" if settings.tracking_enabled else "DISABLED",
        )
        self.pose_status = self._status_card(
            "POSE",
            "ENABLED" if settings.pose_enabled else "DISABLED",
        )
        self.compute_status = self._status_card(
            "COMPUTE",
            str(settings.device).upper(),
        )

        for card in (
            self.detection_status,
            self.tracking_status,
            self.pose_status,
            self.compute_status,
        ):
            status_grid.addWidget(card, 1)

        status_section.body.addLayout(status_grid)
        content_layout.addWidget(status_section)

        from campusguard.build_info import BUILD_VERSION

        update_section = SettingsSection(
            "Updates",
            "CampusGuard checks for a new version every time it starts and asks before installing.",
        )
        update_row = QHBoxLayout()
        self.update_status_label = QLabel(
            "Development build" if BUILD_VERSION == "dev" else f"Installed build: {BUILD_VERSION}"
        )
        self.update_status_label.setWordWrap(True)
        update_row.addWidget(self.update_status_label, 1)
        self.check_updates_button = QPushButton("Check for updates")
        self.check_updates_button.clicked.connect(self._request_update_check)
        update_row.addWidget(self.check_updates_button)
        update_section.body.addLayout(update_row)
        content_layout.addWidget(update_section)

        privacy_section = SettingsSection(
            "Privacy and data",
            "Choose what this PC shares with your website account and how long it keeps incident clips and records.",
        )
        privacy_form = QFormLayout()
        privacy_form.setHorizontalSpacing(24)
        privacy_form.setVerticalSpacing(14)
        self._cloud_sync_value = settings.cloud_sync
        self.cloud_sync_toggle = QCheckBox("Show this PC's summary on my CampusGuard website account")
        self.cloud_sync_toggle.setChecked(settings.cloud_sync == "on")
        self.cloud_sync_toggle.toggled.connect(self._cloud_sync_toggled)
        self.cloud_sync_note = QLabel(
            "Sends the PC name, camera counts and incident details (camera, time, label, confidence, "
            "severity, status). Never video, images, file locations or anyone's identity."
        )
        self.cloud_sync_note.setProperty("muted", True)
        self.cloud_sync_note.setWordWrap(True)
        self.footage_retention_input = self._retention_combo(
            settings.footage_retention_days,
            ((0, "Until I delete them"), (7, "7 days"), (30, "30 days"), (60, "60 days"), (90, "90 days"),
             (180, "180 days"), (365, "1 year")),
            "incident clips",
        )
        self.incident_retention_input = self._retention_combo(
            settings.incident_retention_days,
            ((0, "Until I delete them"), (90, "90 days"), (180, "180 days"), (365, "1 year"), (730, "2 years")),
            "incident records",
        )
        self.retention_note = QLabel(
            "Older items are removed automatically, checked at start-up and every few hours. "
            "Keep them only as long as your school needs them."
        )
        self.retention_note.setProperty("muted", True)
        self.retention_note.setWordWrap(True)
        self.privacy_policy_button = QPushButton("Read the Privacy Policy ↗")
        self.privacy_policy_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(auth_config.WEBSITE_URL + "/privacy"))
        )
        privacy_form.addRow("Account sync", self.cloud_sync_toggle)
        privacy_form.addRow("", self.cloud_sync_note)
        privacy_form.addRow("Keep incident clips", self.footage_retention_input)
        privacy_form.addRow("Keep incident records", self.incident_retention_input)
        privacy_form.addRow("", self.retention_note)
        privacy_form.addRow("", self.privacy_policy_button)
        privacy_section.body.addLayout(privacy_form)
        content_layout.addWidget(privacy_section)

        account_section = SettingsSection(
            "Your account",
            "Shared with the CampusGuard website and phone app: change it in any of them and it updates everywhere.",
        )
        account_form = QFormLayout()
        account_form.setHorizontalSpacing(24)
        account_form.setVerticalSpacing(14)
        self.profile_email = QLabel("Loading your details…")
        self.profile_email.setProperty("muted", True)
        self.profile_name = QLineEdit()
        self.profile_name.setMaxLength(80)
        self.profile_name.setPlaceholderText("Your name")
        self.profile_school = QLineEdit()
        self.profile_school.setMaxLength(120)
        self.profile_school.setPlaceholderText("School or college name")
        self.profile_phone = QLineEdit()
        self.profile_phone.setMaxLength(20)
        self.profile_phone.setPlaceholderText("+91 70000 00000")
        self.profile_alerts = QPlainTextEdit()
        self.profile_alerts.setPlaceholderText("One number per line, up to 5")
        self.profile_alerts.setFixedHeight(96)
        self.profile_status = QLabel("")
        self.profile_status.setProperty("muted", True)
        self.profile_status.setWordWrap(True)
        self.profile_save = QPushButton("Save my details")
        self.profile_save.setEnabled(False)
        self.profile_save.clicked.connect(self._save_profile)
        account_form.addRow("Signed in as", self.profile_email)
        account_form.addRow("Your name", self.profile_name)
        account_form.addRow("School", self.profile_school)
        account_form.addRow("Your phone", self.profile_phone)
        account_form.addRow("Alert numbers", self.profile_alerts)
        account_form.addRow("", self.profile_save)
        account_form.addRow("", self.profile_status)
        account_section.body.addLayout(account_form)
        content_layout.addWidget(account_section)
        self._profile_loaded.connect(self._apply_profile)
        threading.Thread(target=self._load_profile, daemon=True).start()

        content_layout.addStretch(1)
        self._tab_sections = {
            "General": [account_section, workspace_section],
            "Appearance": [appearance_section],
            "Detection": [ai_section, status_section],
            "Alerts": [phone_section],
            "Storage": [health_section, privacy_section],
            "Connection": [connection_section],
            "Help": [update_section],
        }
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        # ------------------------------------------------------------------
        # SIGNALS
        # ------------------------------------------------------------------
        self.threshold_input.valueChanged.connect(self._emit_settings)
        self.detection_toggle.toggled.connect(self._emit_settings)
        self.tracking_toggle.toggled.connect(self._emit_settings)
        self.pose_toggle.toggled.connect(self._emit_settings)
        self.cooldown_input.valueChanged.connect(self._emit_settings)
        self.reconnect_toggle.toggled.connect(self._emit_settings)
        self.device_input.currentIndexChanged.connect(self._emit_settings)
        self.theme_input.currentIndexChanged.connect(self._emit_settings)

        self._refresh_status_cards()
        self._show_tab("General")

    def _show_tab(self, name: str) -> None:
        for tab, sections in self._tab_sections.items():
            for section in sections:
                section.setVisible(tab == name)
        self.scroll.verticalScrollBar().setValue(0)


    def _request_update_check(self) -> None:
        self.check_updates_button.setEnabled(False)
        self.update_status_label.setText("Checking for updates…")
        self.update_check_requested.emit()

    def set_update_status(self, text: str) -> None:
        self.update_status_label.setText(text)
        self.check_updates_button.setEnabled(True)

    def _status_card(self, title: str, value: str) -> QFrame:
        frame = QFrame()
        frame.setProperty("card", True)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setProperty("muted", True)
        title_label.setStyleSheet("font-size: 9px; font-weight: 600; letter-spacing: 0px;")

        value_label = QLabel(value)
        value_label.setStyleSheet("font-size: 12px; font-weight: 600;")

        layout.addWidget(title_label)
        layout.addWidget(value_label)

        frame.value_label = value_label  # type: ignore[attr-defined]
        return frame

    def set_health(self, report, extra_problems=()) -> None:
        """Show a system_health.HealthReport (plus camera problems) in the health section."""
        gb = 1024 ** 3
        self.health_disk_label.setText(
            f"{report.disk_free / gb:.1f} GB free of {report.disk_total / gb:.0f} GB ({report.disk_free_percent:.0f}% free)"
            if report.disk_total else "Unknown"
        )
        self.health_footage_label.setText(f"{report.footage_clips} clips, {report.footage_bytes / gb:.2f} GB")
        self.health_gpu_label.setText(
            f"{report.gpu_name} - {report.gpu_free_mb} of {report.gpu_total_mb} MB free"
            if report.gpu_name else "No GPU in use (running on CPU)"
        )
        problems = list(report.problems) + list(extra_problems)
        self.health_status_label.setText(
            "All systems normal." if not problems else "\n".join(message for _level, message in problems)
        )

    def _token_entered(self) -> None:
        token = self.whatsapp_token_input.text().strip()
        if token:
            self.whatsapp_token_changed.emit(token)
            self.whatsapp_token_input.clear()
            self.whatsapp_token_input.setPlaceholderText("Token saved. Type a new one to replace it.")

    def focus_setting(self, name: str) -> None:
        """Scroll to and focus a named control (used by whole-app search)."""
        widget = getattr(self, name, None)
        if widget is not None:
            for tab, sections in self._tab_sections.items():
                if any(section.isAncestorOf(widget) for section in sections):
                    self.tabs.set_current(tab)
                    self._show_tab(tab)
                    break
            self.scroll.ensureWidgetVisible(widget, 40, 80)
            widget.setFocus()

    def _retention_combo(self, current: int, options: tuple, what: str) -> QComboBox:
        combo = QComboBox()
        for days, label in options:
            combo.addItem(label, days)
        if combo.findData(int(current)) < 0:  # a value set outside the usual list stays visible
            combo.addItem(f"{int(current)} days", int(current))
        combo.setCurrentIndex(max(0, combo.findData(int(current))))
        combo.setProperty("applied", int(current))
        combo.currentIndexChanged.connect(lambda _i, c=combo, w=what: self._retention_changed(c, w))
        return combo

    def _retention_changed(self, combo: QComboBox, what: str) -> None:
        if self._updating:
            return
        new = int(combo.currentData())
        old = int(combo.property("applied") or 0)
        if new > 0 and (old == 0 or new < old):
            answer = QMessageBox.question(
                self,
                "Delete older items?",
                f"CampusGuard will permanently delete {what} older than {combo.currentText().lower()}. "
                "This cannot be undone.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self._updating = True
                try:
                    combo.setCurrentIndex(max(0, combo.findData(old)))
                finally:
                    self._updating = False
                return
        combo.setProperty("applied", new)
        self._emit_settings()


    # ------------------------------------------------------------------ account details
    def _load_profile(self) -> None:
        from campusguard import profile
        try:
            self._profile_loaded.emit(profile.fetch_profile(), "")
        except profile.ProfileError as error:
            self._profile_loaded.emit(None, str(error))

    def _apply_profile(self, data, message: str) -> None:
        if data is None:
            self.profile_email.setText("Not available right now")
            self.profile_status.setText(message)
            return
        self.profile_email.setText(str(data.get("email", "")))
        self.profile_name.setText(str(data.get("full_name", "")))
        self.profile_school.setText(str(data.get("school_name", "")))
        self.profile_phone.setText(str(data.get("phone", "")))
        phones = [str(number) for number in data.get("alert_phones", [])]
        self.profile_alerts.setPlainText("\n".join(phones))
        self.profile_save.setEnabled(True)
        self.profile_status.setText(message)
        # The account's alert numbers are the school's list of who gets alerts. Adopt them on this
        # PC when it has none of its own, and keep them in step after the user saves a change.
        saved = message.startswith("Saved")
        if phones and (saved or (not message and not self.alert_numbers_input.text().strip())):
            self.alert_numbers_input.setText(", ".join(phones))
            self._emit_settings()

    def _save_profile(self) -> None:
        from campusguard import profile
        self.profile_save.setEnabled(False)
        self.profile_status.setText("Saving…")
        values = (self.profile_name.text(), self.profile_school.text(), self.profile_phone.text(),
                  self.profile_alerts.toPlainText().splitlines())

        def work() -> None:
            try:
                self._profile_loaded.emit(profile.save_profile(*values), "Saved. The website and phone app show the same details.")
            except profile.ProfileError as error:
                self._profile_loaded.emit({"email": self.profile_email.text(), "full_name": values[0], "school_name": values[1],
                                           "phone": values[2], "alert_phones": values[3]}, str(error))
        threading.Thread(target=work, daemon=True).start()

    def _cloud_sync_toggled(self, checked: bool) -> None:
        if self._updating:
            return
        self._cloud_sync_value = "on" if checked else "off"
        self._emit_settings()

    def set_cloud_sync_choice(self, value: str) -> None:
        """Record the answer to the first-run notice, so saving stays in one place."""
        self._cloud_sync_value = "on" if value == "on" else "off"
        self.cloud_sync_toggle.blockSignals(True)
        self.cloud_sync_toggle.setChecked(self._cloud_sync_value == "on")
        self.cloud_sync_toggle.blockSignals(False)
        self._emit_settings()

    def _reset_defaults(self) -> None:
        defaults = AppSettings(theme=self.theme_input.currentData())
        self._updating = True
        try:
            self.threshold_input.setValue(defaults.confidence_threshold)
            self.detection_toggle.setChecked(defaults.detection_enabled)
            self.tracking_toggle.setChecked(defaults.tracking_enabled)
            self.pose_toggle.setChecked(defaults.pose_enabled)
            self.cooldown_input.setValue(defaults.alert_cooldown_seconds)
            self.reconnect_toggle.setChecked(defaults.auto_reconnect)
            self.device_input.setCurrentIndex(max(0, self.device_input.findData(defaults.device)))
            self.alert_sound_toggle.setChecked(defaults.alert_sound_enabled)
            self.start_page_input.setCurrentIndex(max(0, self.start_page_input.findData(defaults.start_page)))
            self.sidebar_hover_toggle.setChecked(defaults.sidebar_hover_open)
        finally:
            self._updating = False
        self._emit_settings()

    def eventFilter(self, watched, event):  # noqa: N802 (Qt API)
        # A multi-line box has no editingFinished: save when the user leaves it.
        if watched is getattr(self, "building_numbers_input", None) and event.type() == QEvent.Type.FocusOut:
            self._emit_settings()
        return super().eventFilter(watched, event)

    def _emit_settings(self, *_args) -> None:
        if self._updating:
            return

        settings = dataclasses.replace(
            self._initial_settings,
            confidence_threshold=self.threshold_input.value(),
            detection_enabled=self.detection_toggle.isChecked(),
            tracking_enabled=self.tracking_toggle.isChecked(),
            pose_enabled=self.pose_toggle.isChecked(),
            alert_cooldown_seconds=self.cooldown_input.value(),
            auto_reconnect=self.reconnect_toggle.isChecked(),
            theme=str(self.theme_input.currentData()),
            detector_model_path=self._initial_settings.detector_model_path,
            pose_model_path=self._initial_settings.pose_model_path,
            fdsc_mc3_model_path=self._initial_settings.fdsc_mc3_model_path,
            violence_model="fdsc_mc3",
            device=str(self.device_input.currentData()),
            fight_positive_class=self._initial_settings.fight_positive_class,
            connection_mode=str(self.connection_mode_input.currentData()),
            server_address=self.server_address_input.text().strip(),
            alert_sound_enabled=self.alert_sound_toggle.isChecked(),
            start_page=str(self.start_page_input.currentData()),
            sidebar_hover_open=self.sidebar_hover_toggle.isChecked(),
            alert_numbers=self.alert_numbers_input.text().strip(),
            building_numbers=self.building_numbers_input.toPlainText().strip(),
            health_numbers=self.health_numbers_input.text().strip(),
            health_offline_minutes=self.health_offline_input.value(),
            escalation_numbers=self.escalation_numbers_input.text().strip(),
            escalate_minutes=self.escalate_input.value(),
            alert_min_severity=str(self.min_severity_input.currentData()),
            whatsapp_mode=str(self.whatsapp_mode_input.currentData()),
            whatsapp_phone_id=self.whatsapp_phone_id_input.text().strip(),
            whatsapp_template=self.whatsapp_template_input.text().strip(),
            country_code=self.country_code_input.text().strip(),
            ntfy_topic=self.ntfy_topic_input.text().strip(),
            ntfy_server=self._initial_settings.ntfy_server,
            ntfy_attach_clip=self.ntfy_attach_toggle.isChecked(),
            auto_open_whatsapp=self.auto_open_whatsapp_toggle.isChecked(),
            alert_confirm_predictions=int(self.confirm_input.currentData()),
            gpu_video_decode=self.gpu_decode_toggle.isChecked(),
            cloud_sync=self._cloud_sync_value,
            footage_retention_days=int(self.footage_retention_input.currentData()),
            incident_retention_days=int(self.incident_retention_input.currentData()),
            silent_mode=self.silent_mode_toggle.isChecked(),
            keep_awake=self.keep_awake_toggle.isChecked(),
        )

        self._initial_settings = settings
        self._refresh_status_cards()
        self.settings_changed.emit(settings)

    def _refresh_status_cards(self) -> None:
        self.detection_status.value_label.setText(
            "ENABLED" if self.detection_toggle.isChecked() else "DISABLED"
        )
        self.tracking_status.value_label.setText(
            "ENABLED" if self.tracking_toggle.isChecked() else "DISABLED"
        )
        self.pose_status.value_label.setText(
            "ENABLED" if self.pose_toggle.isChecked() else "DISABLED"
        )
        self.compute_status.value_label.setText(
            str(self.device_input.currentData()).upper()
        )

    def set_device_status(self, message: str) -> None:
        self.device_status.setText(message)

    def set_theme(self, theme: str) -> None:
        index = self.theme_input.findData(theme)

        if index >= 0:
            self.theme_input.blockSignals(True)
            self.theme_input.setCurrentIndex(index)
            self.theme_input.blockSignals(False)

    def set_server_token(self, token: str) -> None:
        self.server_token_input.setText(token)

    def set_connection_test_result(self, message: str, success: bool = False) -> None:
        self.connection_test_status.setText(message)
        self.connection_test_status.setProperty("connectionOk", bool(success))
        self.connection_test_status.style().unpolish(self.connection_test_status)
        self.connection_test_status.style().polish(self.connection_test_status)

    def set_saved(self) -> None:
        self.save_label.setText("Changes saved locally.")
