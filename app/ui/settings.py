from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFormLayout, QLineEdit,
    QDoubleSpinBox, QSpinBox, QPushButton, QMessageBox
)
from app.services.settings import save

class SettingsPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main

        layout = QVBoxLayout(self)
        title = QLabel("Settings")
        title.setStyleSheet("font-size:28px;font-weight:800;")
        layout.addWidget(title)

        form = QFormLayout()

        self.model = QLineEdit(main.settings["model_path"])

        self.confidence = QDoubleSpinBox()
        self.confidence.setRange(0.05, 0.99)
        self.confidence.setSingleStep(0.05)
        self.confidence.setValue(main.settings["confidence"])

        self.cooldown = QSpinBox()
        self.cooldown.setRange(1, 60)
        self.cooldown.setValue(main.settings["alert_cooldown"])

        form.addRow("YOLO model path", self.model)
        form.addRow("Confidence", self.confidence)
        form.addRow("Alert cooldown", self.cooldown)

        layout.addLayout(form)

        button = QPushButton("Save Settings")
        button.clicked.connect(self.save_settings)
        layout.addWidget(button)
        layout.addStretch()

    def save_settings(self):
        self.main.settings["model_path"] = self.model.text().strip()
        self.main.settings["confidence"] = self.confidence.value()
        self.main.settings["alert_cooldown"] = self.cooldown.value()

        save(self.main.settings)

        self.main.detector.confidence = self.confidence.value()
        self.main.detector.model_path = __import__("pathlib").Path(
            self.model.text().strip()
        )
        self.main.detector.load()

        QMessageBox.information(
            self, "CampusGuard", "Settings saved."
        )
