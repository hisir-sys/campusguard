from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
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
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

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
        self._paths: dict[str, QLineEdit] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(13)

        header = QHBoxLayout()
        header.setSpacing(16)

        header.addWidget(
            make_page_title(
                "System settings",
                "Configure detection, camera behavior, local model files, compute resources, and the CampusGuard appearance.",
            ),
            1,
        )

        self.status_pill = QLabel("LOCAL CONFIGURATION")
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
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(11)

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

        self.violence_model_input = QComboBox()
        self.violence_model_input.addItem("Current MC3-18", "mc3")
        self.violence_model_input.addItem("Spontim 1.0", "fdsc_mc3")
        self.violence_model_input.addItem("FDSC R3D-18 — Technical Issue", "r3d")
        self.violence_model_input.addItem("X3D-M", "x3d")
        self.violence_model_input.addItem("CampusGuard Enhanced — Coming Soon", "enhanced")

        # R3D remains documented in the model registry, but its original FDSC
        # checkpoint is currently unavailable. Keep the entry visible for
        # transparency while preventing operators from selecting it.
        r3d_index = self.violence_model_input.findData("r3d")
        r3d_item = self.violence_model_input.model().item(r3d_index)
        if r3d_item is not None:
            r3d_item.setEnabled(False)

        enhanced_index = self.violence_model_input.findData("enhanced")
        enhanced_item = self.violence_model_input.model().item(enhanced_index)
        if enhanced_item is not None:
            enhanced_item.setEnabled(False)

        selected_model = settings.violence_model if settings.violence_model not in {"enhanced", "r3d"} else "mc3"
        model_index = self.violence_model_input.findData(selected_model)
        self.violence_model_input.setCurrentIndex(max(0, model_index))

        self.violence_model_note = QLabel(
            "The selected violence model runs on each tracked person's temporal ROI. "
            "Three models are currently verified and operational: Current MC3-18, Spontim 1.0, and X3D-M. "
            "FDSC R3D-18 is temporarily unavailable because the original checkpoint could not be obtained; "
            "CampusGuard Enhanced is reserved for a future multi-model ensemble."
        )
        self.violence_model_note.setWordWrap(True)
        self.violence_model_note.setProperty("muted", True)

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
        form.addRow("Violence model", self.violence_model_input)
        form.addRow("", self.violence_model_note)
        form.addRow("", self.device_status)

        ai_section.body.addLayout(form)
        content_layout.addWidget(ai_section)

        # ------------------------------------------------------------------
        # MODEL FILES
        # ------------------------------------------------------------------
        models_section = SettingsSection(
            "MODEL FILES",
            "Point CampusGuard to local model weights. Missing files remain unloaded and no artificial model output is generated.",
        )

        models_form = QFormLayout()
        models_form.setHorizontalSpacing(18)
        models_form.setVerticalSpacing(11)

        self._add_model_path(
            models_form,
            "Person detector (YOLO)",
            "detector_model_path",
            settings.detector_model_path,
            "*.pt",
        )
        self._add_model_path(
            models_form,
            "Pose estimator (YOLO Pose)",
            "pose_model_path",
            settings.pose_model_path,
            "*.pt",
        )
        self._add_model_path(
            models_form,
            "Fight classifier (MC3-18)",
            "fight_model_path",
            settings.fight_model_path,
            "*.pth",
        )
        self._add_model_path(
            models_form,
            "Spontim 1.0",
            "fdsc_mc3_model_path",
            settings.fdsc_mc3_model_path,
            "*.pth",
        )
        self._add_model_path(
            models_form,
            "FDSC R3D-18 (unavailable)",
            "r3d_model_path",
            settings.r3d_model_path,
            "*.pth",
        )
        self._add_model_path(
            models_form,
            "X3D-M",
            "x3d_model_path",
            settings.x3d_model_path,
            "*.pt",
        )

        self.positive_class_input = QComboBox()
        self.positive_class_input.addItem("Output 1 is fight", 1)
        self.positive_class_input.addItem("Output 0 is fight", 0)

        positive_index = self.positive_class_input.findData(settings.fight_positive_class)
        self.positive_class_input.setCurrentIndex(max(0, positive_index))

        models_form.addRow("Two-class MC3-18 mapping", self.positive_class_input)
        models_section.body.addLayout(models_form)

        model_note = QLabel(
            "Recommended: keep model files in the project's models directory so the configuration remains portable."
        )
        model_note.setWordWrap(True)
        model_note.setProperty("muted", True)
        models_section.body.addWidget(model_note)

        content_layout.addWidget(models_section)

        # ------------------------------------------------------------------
        # APPEARANCE
        # ------------------------------------------------------------------
        appearance_section = SettingsSection(
            "APPEARANCE",
            "Choose the visual theme used across the CampusGuard desktop interface.",
        )

        theme_row = QHBoxLayout()
        theme_row.setSpacing(10)

        theme_label = QLabel("Interface theme")
        theme_label.setMinimumWidth(130)

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
        self.violence_model_input.currentIndexChanged.connect(self._emit_settings)
        self.positive_class_input.currentIndexChanged.connect(self._emit_settings)
        self.theme_input.currentIndexChanged.connect(self._emit_settings)

        self._refresh_status_cards()

    def _mini_card(self, title: str, description: str) -> QWidget:
        frame = QFrame()
        frame.setProperty("card", True)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(13, 12, 13, 12)
        layout.setSpacing(7)

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
        layout.setContentsMargins(12, 11, 12, 11)
        layout.setSpacing(5)

        title_label = QLabel(title)
        title_label.setProperty("muted", True)
        title_label.setStyleSheet("font-size: 9px; font-weight: 800; letter-spacing: 0.7px;")

        value_label = QLabel(value)
        value_label.setStyleSheet("font-size: 12px; font-weight: 800;")

        layout.addWidget(title_label)
        layout.addWidget(value_label)

        frame.value_label = value_label  # type: ignore[attr-defined]
        return frame

    def _add_model_path(
        self,
        form: QFormLayout,
        label: str,
        key: str,
        value: str,
        extension: str,
    ) -> None:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        line = QLineEdit(value)
        line.setPlaceholderText("Select local model file...")

        button = QPushButton("Browse")
        button.setMinimumWidth(82)

        row.addWidget(line, 1)
        row.addWidget(button)

        button.clicked.connect(
            lambda checked=False, field=line, title=label, ext=extension:
            self._browse_model(field, title, ext)
        )
        line.editingFinished.connect(self._emit_settings)

        self._paths[key] = line
        form.addRow(label, container)

    def _browse_model(
        self,
        field: QLineEdit,
        title: str,
        extension: str,
    ) -> None:
        start = field.text() or str(Path.cwd())

        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {title}",
            start,
            f"Model files ({extension});;All files (*.*)",
        )

        if path:
            field.setText(path)
            self._emit_settings()

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
            detector_model_path=self._paths["detector_model_path"].text().strip(),
            pose_model_path=self._paths["pose_model_path"].text().strip(),
            fight_model_path=self._paths["fight_model_path"].text().strip(),
            fdsc_mc3_model_path=self._paths["fdsc_mc3_model_path"].text().strip(),
            r3d_model_path=self._paths["r3d_model_path"].text().strip(),
            x3d_model_path=self._paths["x3d_model_path"].text().strip(),
            violence_model=str(self.violence_model_input.currentData()),
            device=str(self.device_input.currentData()),
            fight_positive_class=int(self.positive_class_input.currentData()),
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
