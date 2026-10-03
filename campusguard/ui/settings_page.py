from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from campusguard.settings import AppSettings
from campusguard.ui.common import make_card, make_page_title


class SettingsPage(QWidget):
    settings_changed = Signal(object)

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._updating = False
        self._paths: dict[str, QLineEdit] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(13)
        root.addWidget(make_page_title(
            "System settings",
            "Settings are stored in the local SQLite database and applied to camera workers without blocking the interface.",
        ))

        ai_frame, ai_layout = make_card("AI ENGINE")
        form = QFormLayout()
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
        self.device_status.setProperty("muted", True)
        form.addRow("Minimum confidence", self.threshold_input)
        form.addRow("Person detection", self.detection_toggle)
        form.addRow("Tracking", self.tracking_toggle)
        form.addRow("Pose overlay", self.pose_toggle)
        form.addRow("Alert cooldown", self.cooldown_input)
        form.addRow("Camera reconnect", self.reconnect_toggle)
        form.addRow("Compute device", self.device_input)
        form.addRow("", self.device_status)
        ai_layout.addLayout(form)
        root.addWidget(ai_frame)

        models_frame, models_layout = make_card("MODEL FILES")
        models_intro = QLabel(
            "Select local weights. Missing files stay unloaded; this app never fabricates model output."
        )
        models_intro.setWordWrap(True)
        models_intro.setProperty("muted", True)
        models_layout.addWidget(models_intro)
        models_form = QFormLayout()
        self._add_model_path(models_form, "Person detector (YOLO)", "detector_model_path", settings.detector_model_path, "*.pt")
        self._add_model_path(models_form, "Pose estimator (YOLO Pose)", "pose_model_path", settings.pose_model_path, "*.pt")
        self._add_model_path(models_form, "Fight classifier (MC3-18)", "fight_model_path", settings.fight_model_path, "*.pth")
        self.positive_class_input = QComboBox()
        self.positive_class_input.addItem("Output 1 is fight", 1)
        self.positive_class_input.addItem("Output 0 is fight", 0)
        positive_index = self.positive_class_input.findData(settings.fight_positive_class)
        self.positive_class_input.setCurrentIndex(max(0, positive_index))
        models_form.addRow("Two-class MC3-18 mapping", self.positive_class_input)
        models_layout.addLayout(models_form)
        root.addWidget(models_frame)

        theme_frame, theme_layout = make_card("APPEARANCE")
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme"))
        self.theme_input = QComboBox()
        self.theme_input.addItem("Dark", "dark")
        self.theme_input.addItem("Light", "light")
        self.theme_input.setCurrentIndex(
            max(0, self.theme_input.findData(settings.theme))
        )
        theme_row.addWidget(self.theme_input)
        theme_row.addStretch(1)
        self.save_label = QLabel("Changes save locally as they are applied.")
        self.save_label.setProperty("muted", True)
        theme_row.addWidget(self.save_label)
        theme_layout.addLayout(theme_row)
        root.addWidget(theme_frame)
        root.addStretch(1)

        self.threshold_input.valueChanged.connect(self._emit_settings)
        self.detection_toggle.toggled.connect(self._emit_settings)
        self.tracking_toggle.toggled.connect(self._emit_settings)
        self.pose_toggle.toggled.connect(self._emit_settings)
        self.cooldown_input.valueChanged.connect(self._emit_settings)
        self.reconnect_toggle.toggled.connect(self._emit_settings)
        self.device_input.currentIndexChanged.connect(self._emit_settings)
        self.positive_class_input.currentIndexChanged.connect(self._emit_settings)
        self.theme_input.currentIndexChanged.connect(self._emit_settings)

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
        line = QLineEdit(value)
        button = QPushButton("Browse")
        row.addWidget(line, 1)
        row.addWidget(button)
        button.clicked.connect(
            lambda checked=False, field=line, title=label, ext=extension:
            self._browse_model(field, title, ext)
        )
        line.editingFinished.connect(self._emit_settings)
        self._paths[key] = line
        form.addRow(label, container)

    def _browse_model(self, field: QLineEdit, title: str, extension: str) -> None:
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
            device=str(self.device_input.currentData()),
            fight_positive_class=int(self.positive_class_input.currentData()),
        )
        self.settings_changed.emit(settings)

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