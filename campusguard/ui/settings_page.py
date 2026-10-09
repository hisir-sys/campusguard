from __future__ import annotations


from PySide6.QtCore import Qt, Signal
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
    QVBoxLayout,
    QWidget,
)

from campusguard.settings import AppSettings
from campusguard.ui.common import make_card, make_page_title


class SettingsSection(QFrame):
    """Small visual wrapper used only by the settings page."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        heading = QLabel(title)
        heading.setStyleSheet("font-size: 13px; font-weight: 800; letter-spacing: 0.5px;")
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

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._updating = False
        self._initial_settings = settings

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 112)
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

        self.status_pill = QLabel("SYSTEM CONTROLS")
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_pill.setMinimumHeight(30)
        self.status_pill.setStyleSheet(
            """
            QLabel {
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 15px;
                padding: 0 12px;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.8px;
            }
            """
        )
        header.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        scroll = QScrollArea()
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
            "AI ENGINE",
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
            "APPEARANCE",
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
        # SYSTEM STATUS
        # ------------------------------------------------------------------
        status_section = SettingsSection(
            "SYSTEM STATUS",
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

        content_layout.addStretch(1)
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

    def _mini_card(self, title: str, description: str) -> QWidget:
        frame = QFrame()
        frame.setProperty("card", True)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 10px; font-weight: 800; letter-spacing: 0.7px;")
        layout.addWidget(title_label)

        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setProperty("muted", True)
        layout.addWidget(description_label)

        body = QVBoxLayout()
        body.setSpacing(7)
        layout.addLayout(body)

        frame.body = body  # type: ignore[attr-defined]
        return frame

    def _status_card(self, title: str, value: str) -> QFrame:
        frame = QFrame()
        frame.setProperty("card", True)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setProperty("muted", True)
        title_label.setStyleSheet("font-size: 9px; font-weight: 800; letter-spacing: 0.7px;")

        value_label = QLabel(value)
        value_label.setStyleSheet("font-size: 12px; font-weight: 800;")

        layout.addWidget(title_label)
        layout.addWidget(value_label)

        frame.value_label = value_label  # type: ignore[attr-defined]
        return frame

    def _emit_settings(self, *_args) -> None:
        if self._updating:
            return

        settings = AppSettings(
            confidence_threshold=self.threshold_input.value(),
            detection_enabled=self.detection_toggle.isChecked(),
            tracking_enabled=self.tracking_toggle.isChecked(),
            pose_enabled=self.pose_toggle.isChecked(),
            alert_cooldown_seconds=self.cooldown_input.value(),
            auto_reconnect=self.reconnect_toggle.isChecked(),
            theme=str(self.theme_input.currentData()),
            detector_model_path=self._initial_settings.detector_model_path,
            pose_model_path=self._initial_settings.pose_model_path,
            fight_model_path=self._initial_settings.fight_model_path,
            fdsc_mc3_model_path=self._initial_settings.fdsc_mc3_model_path,
            r3d_model_path=self._initial_settings.r3d_model_path,
            x3d_model_path=self._initial_settings.x3d_model_path,
            violence_model="fdsc_mc3",
            device=str(self.device_input.currentData()),
            fight_positive_class=self._initial_settings.fight_positive_class,
        )

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

    def set_saved(self) -> None:
        self.save_label.setText("Saved to the local database.")
