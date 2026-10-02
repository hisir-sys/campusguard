from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QListWidget, QStackedWidget
)

from app.services.settings import load
from app.core.detector import Detector
from app.core.camera_manager import CameraManager
from app.core.incident_manager import IncidentManager

from app.ui.dashboard import DashboardPage
from app.ui.cameras import CamerasPage
from app.ui.incidents import IncidentsPage
from app.ui.alerts import AlertsPage
from app.ui.settings import SettingsPage

STYLE = '''
QMainWindow, QWidget { background:#05090e; color:#e8f0f7; }
QListWidget { background:#081018; border:1px solid #182a39; border-radius:12px; padding:8px; }
QListWidget::item { padding:14px; color:#8ea5ba; }
QListWidget::item:selected { background:#102638; color:white; }
QPushButton { background:#10202d; color:#e8f0f7; border:1px solid #294256; border-radius:8px; padding:10px 16px; }
QLineEdit, QDoubleSpinBox, QSpinBox { background:#071019; color:#e8f0f7; border:1px solid #263b4d; border-radius:8px; padding:9px; }
'''

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CampusGuard")
        self.resize(1280, 800)
        self.setStyleSheet(STYLE)

        self.settings = load()
        self.incidents = IncidentManager()
        self.detector = Detector(
            self.settings["model_path"],
            self.settings["confidence"]
        )
        self.cameras = CameraManager()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        self.nav = QListWidget()
        self.nav.setFixedWidth(180)
        self.nav.addItems([
            "Dashboard", "Cameras", "Incidents", "Alerts", "Settings"
        ])

        self.stack = QStackedWidget()
        layout.addWidget(self.nav)
        layout.addWidget(self.stack, 1)

        self.dashboard = DashboardPage(self)
        self.camera_page = CamerasPage(self)
        self.incident_page = IncidentsPage(self)
        self.alert_page = AlertsPage(self)
        self.settings_page = SettingsPage(self)

        for page in [
            self.dashboard, self.camera_page, self.incident_page,
            self.alert_page, self.settings_page
        ]:
            self.stack.addWidget(page)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        self.cameras.frame_ready.connect(self.camera_page.on_frame)
        self.cameras.error.connect(self.camera_page.on_error)

    def add_incident(self, camera, detection):
        self.incidents.add(
            camera,
            detection["event"],
            detection["confidence"],
            detection["severity"]
        )
        self.incident_page.refresh()
        self.alert_page.refresh()
        self.dashboard.refresh()

    def closeEvent(self, event):
        self.cameras.stop_all()
        event.accept()
