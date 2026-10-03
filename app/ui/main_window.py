from PySide6.QtCore import Qt, QStringListModel
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QPushButton,
    QLabel,
    QLineEdit,
    QCompleter,
    QFrame,
    QSizePolicy,
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


DARK_STYLE = """
QMainWindow {
    background: #080A0B;
}

QWidget {
    color: #E9EEED;
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
}

QFrame#TopBar {
    background: #111617;
    border: 1px solid #242D2F;
    border-radius: 22px;
}

QFrame#BottomDock {
    background: #111617;
    border: 1px solid #242D2F;
    border-radius: 24px;
}

QLabel#Logo {
    color: #F1F5F4;
    font-size: 17px;
    font-weight: 700;
}

QLabel#LogoDot {
    background: #78A9A2;
    border-radius: 5px;
}

QPushButton#TopButton {
    background: transparent;
    color: #8D9A9A;
    border: none;
    border-radius: 12px;
    padding: 9px 13px;
    font-size: 13px;
}

QPushButton#TopButton:hover {
    background: #1B2224;
    color: #F1F5F4;
}

QPushButton#ThemeButton,
QPushButton#LoginButton {
    background: #1A2224;
    color: #DDE5E3;
    border: 1px solid #2B3739;
    border-radius: 12px;
    padding: 9px 13px;
}

QPushButton#ThemeButton:hover,
QPushButton#LoginButton:hover {
    background: #222C2E;
}

QLineEdit#SearchBox {
    background: #0C1011;
    color: #E9EEED;
    border: 1px solid #293436;
    border-radius: 13px;
    padding: 9px 14px;
    selection-background-color: #426965;
}

QPushButton#DockButton {
    background: transparent;
    color: #7F8C8C;
    border: none;
    border-radius: 15px;
    padding: 10px 15px;
    min-width: 78px;
}

QPushButton#DockButton:hover {
    background: #1A2224;
    color: #EAF0EF;
}

QPushButton#DockButton[active="true"] {
    background: #253133;
    color: #F5F8F7;
    border: 1px solid #354547;
}

QFrame#ContentArea {
    background: transparent;
}
"""


LIGHT_STYLE = """
QMainWindow {
    background: #EEF2F0;
}

QWidget {
    color: #17201F;
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
}

QFrame#TopBar {
    background: #FFFFFF;
    border: 1px solid #D6DEDC;
    border-radius: 22px;
}

QFrame#BottomDock {
    background: #FFFFFF;
    border: 1px solid #D6DEDC;
    border-radius: 24px;
}

QLabel#Logo {
    color: #17201F;
    font-size: 17px;
    font-weight: 700;
}

QLabel#LogoDot {
    background: #527F79;
    border-radius: 5px;
}

QPushButton#TopButton {
    background: transparent;
    color: #687573;
    border: none;
    border-radius: 12px;
    padding: 9px 13px;
    font-size: 13px;
}

QPushButton#TopButton:hover {
    background: #EDF2F0;
    color: #17201F;
}

QPushButton#ThemeButton,
QPushButton#LoginButton {
    background: #F1F5F3;
    color: #26312F;
    border: 1px solid #D3DDDA;
    border-radius: 12px;
    padding: 9px 13px;
}

QPushButton#ThemeButton:hover,
QPushButton#LoginButton:hover {
    background: #E6ECE9;
}

QLineEdit#SearchBox {
    background: #F6F8F7;
    color: #17201F;
    border: 1px solid #D1DAD7;
    border-radius: 13px;
    padding: 9px 14px;
    selection-background-color: #AFC8C3;
}

QPushButton#DockButton {
    background: transparent;
    color: #71807D;
    border: none;
    border-radius: 15px;
    padding: 10px 15px;
    min-width: 78px;
}

QPushButton#DockButton:hover {
    background: #EEF3F1;
    color: #17201F;
}

QPushButton#DockButton[active="true"] {
    background: #E0E9E6;
    color: #17201F;
    border: 1px solid #CBD8D4;
}

QFrame#ContentArea {
    background: transparent;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("CampusGuard")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 720)

        self.dark_mode = True

        self.settings = load()
        self.incidents = IncidentManager()

        self.detector = Detector(
            self.settings["model_path"],
            self.settings["confidence"],
        )

        self.cameras = CameraManager()

        self._build_ui()

        self.cameras.frame_ready.connect(self.camera_page.on_frame)
        self.cameras.error.connect(self.camera_page.on_error)

        self.apply_theme()

    # ---------------------------------------------------------
    # UI
    # ---------------------------------------------------------

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(22, 18, 22, 18)
        root_layout.setSpacing(14)

        # -----------------------------------------------------
        # TOP FLOATING BAR
        # -----------------------------------------------------

        self.top_bar = QFrame()
        self.top_bar.setObjectName("TopBar")
        self.top_bar.setFixedHeight(66)

        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(16, 9, 16, 9)
        top_layout.setSpacing(8)

        # Logo
        logo_wrap = QWidget()
        logo_layout = QHBoxLayout(logo_wrap)
        logo_layout.setContentsMargins(4, 0, 12, 0)
        logo_layout.setSpacing(9)

        self.logo_dot = QLabel()
        self.logo_dot.setObjectName("LogoDot")
        self.logo_dot.setFixedSize(10, 10)

        self.logo = QPushButton("CampusGuard")
        self.logo.setObjectName("TopButton")
        self.logo.setCursor(Qt.PointingHandCursor)
        self.logo.setFont(QFont("Segoe UI Variable", 700))
        self.logo.clicked.connect(lambda: self.show_page(0))

        logo_layout.addWidget(self.logo_dot)
        logo_layout.addWidget(self.logo)

        top_layout.addWidget(logo_wrap)

        # Top links
        self.about_button = QPushButton("About")
        self.about_button.setObjectName("TopButton")
        self.about_button.clicked.connect(self.open_about)

        self.how_button = QPushButton("How It Works")
        self.how_button.setObjectName("TopButton")
        self.how_button.clicked.connect(self.open_how)

        top_layout.addWidget(self.about_button)
        top_layout.addWidget(self.how_button)

        # Spacer
        top_layout.addStretch(1)

        # Search
        self.search = QLineEdit()
        self.search.setObjectName("SearchBox")
        self.search.setPlaceholderText("Search CampusGuard...")
        self.search.setFixedWidth(250)
        self.search.setClearButtonEnabled(True)

        search_items = [
            "Dashboard",
            "Cameras",
            "Incidents",
            "Alerts",
            "Settings",
            "About",
            "How It Works",
        ]

        self.search_model = QStringListModel(search_items)

        completer = QCompleter(self.search_model, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)

        self.search.setCompleter(completer)

        completer.activated.connect(self.handle_search)
        self.search.returnPressed.connect(self.handle_search)

        top_layout.addWidget(self.search)

        # Theme
        self.theme_button = QPushButton("☾")
        self.theme_button.setObjectName("ThemeButton")
        self.theme_button.setCursor(Qt.PointingHandCursor)
        self.theme_button.setFixedWidth(42)
        self.theme_button.clicked.connect(self.toggle_theme)

        top_layout.addWidget(self.theme_button)

        # Login
        self.login_button = QPushButton("Login")
        self.login_button.setObjectName("LoginButton")
        self.login_button.setCursor(Qt.PointingHandCursor)
        self.login_button.clicked.connect(self.toggle_login)

        top_layout.addWidget(self.login_button)

        root_layout.addWidget(self.top_bar)

        # -----------------------------------------------------
        # CONTENT
        # -----------------------------------------------------

        self.content_area = QFrame()
        self.content_area.setObjectName("ContentArea")

        content_layout = QVBoxLayout(self.content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)

        root_layout.addWidget(self.content_area, 1)

        # -----------------------------------------------------
        # PAGES
        # -----------------------------------------------------

        self.dashboard = DashboardPage(self)
        self.camera_page = CamerasPage(self)
        self.incident_page = IncidentsPage(self)
        self.alert_page = AlertsPage(self)
        self.settings_page = SettingsPage(self)

        self.pages = [
            self.dashboard,
            self.camera_page,
            self.incident_page,
            self.alert_page,
            self.settings_page,
        ]

        for page in self.pages:
            self.stack.addWidget(page)

        # About / How pages
        self.about_page = self.create_info_page(
            "About CampusGuard",
            "A focused campus safety monitoring platform designed to bring "
            "camera monitoring, AI-assisted detection, incidents and alerts "
            "into one operational workspace.",
            [
                ("LIVE MONITORING", "View connected campus camera feeds from one workspace."),
                ("AI-ASSISTED DETECTION", "Analyze camera frames and surface relevant safety events."),
                ("INCIDENT MANAGEMENT", "Keep detected incidents organized with time, camera and severity."),
                ("ALERTS", "Turn important detection events into an actionable notification feed."),
            ],
        )

        self.how_page = self.create_info_page(
            "How It Works",
            "CampusGuard connects camera sources to a local monitoring interface "
            "where frames can be processed by the detection engine.",
            [
                ("01  CONNECT", "Connect a webcam or supported video source."),
                ("02  ANALYZE", "The detection engine processes incoming frames."),
                ("03  DETECT", "Relevant events are identified from the video stream."),
                ("04  RESPOND", "Incidents and alerts are surfaced inside CampusGuard."),
            ],
        )

        self.about_index = self.stack.addWidget(self.about_page)
        self.how_index = self.stack.addWidget(self.how_page)

        # -----------------------------------------------------
        # BOTTOM FLOATING DOCK
        # -----------------------------------------------------

        self.bottom_dock = QFrame()
        self.bottom_dock.setObjectName("BottomDock")
        self.bottom_dock.setFixedHeight(70)

        dock_layout = QHBoxLayout(self.bottom_dock)
        dock_layout.setContentsMargins(12, 8, 12, 8)
        dock_layout.setSpacing(5)

        self.nav_buttons = []

        nav_items = [
            ("⌂", "Dashboard"),
            ("▣", "Cameras"),
            ("◫", "Incidents"),
            ("!", "Alerts"),
            ("⚙", "Settings"),
        ]

        for index, (icon, label) in enumerate(nav_items):
            button = QPushButton(f"{icon}   {label}")
            button.setObjectName("DockButton")
            button.setCursor(Qt.PointingHandCursor)
            button.setProperty("active", index == 0)

            button.clicked.connect(
                lambda checked=False, i=index: self.show_page(i)
            )

            dock_layout.addWidget(button)
            self.nav_buttons.append(button)

        root_layout.addWidget(self.bottom_dock, 0, Qt.AlignHCenter)

    # ---------------------------------------------------------
    # INFORMATION PAGES
    # ---------------------------------------------------------

    def create_info_page(self, title, description, features):
        page = QFrame()
        page.setObjectName("InfoPage")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 36, 40, 36)
        layout.setSpacing(20)

        title_label = QLabel(title)
        title_label.setObjectName("InfoTitle")

        description_label = QLabel(description)
        description_label.setObjectName("InfoDescription")
        description_label.setWordWrap(True)
        description_label.setMaximumWidth(850)

        layout.addWidget(title_label)
        layout.addWidget(description_label)

        feature_layout = QHBoxLayout()
        feature_layout.setSpacing(14)

        for heading, body in features:
            card = QFrame()
            card.setObjectName("InfoCard")

            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(20, 20, 20, 20)
            card_layout.setSpacing(10)

            heading_label = QLabel(heading)
            heading_label.setObjectName("InfoCardHeading")

            body_label = QLabel(body)
            body_label.setObjectName("InfoCardBody")
            body_label.setWordWrap(True)

            card_layout.addWidget(heading_label)
            card_layout.addWidget(body_label)
            card_layout.addStretch()

            feature_layout.addWidget(card, 1)

        layout.addLayout(feature_layout)
        layout.addStretch()

        return page

    def style_info_pages(self):
        if self.dark_mode:
            style = """
            QFrame#InfoPage {
                background: #080A0B;
            }

            QLabel#InfoTitle {
                color: #F0F5F3;
                font-size: 34px;
                font-weight: 700;
            }

            QLabel#InfoDescription {
                color: #929E9D;
                font-size: 15px;
                line-height: 1.5;
            }

            QFrame#InfoCard {
                background: #111719;
                border: 1px solid #263133;
                border-radius: 20px;
                min-height: 145px;
            }

            QLabel#InfoCardHeading {
                color: #DCE5E2;
                font-size: 13px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            QLabel#InfoCardBody {
                color: #859391;
                font-size: 13px;
            }
            """
        else:
            style = """
            QFrame#InfoPage {
                background: #EEF2F0;
            }

            QLabel#InfoTitle {
                color: #18211F;
                font-size: 34px;
                font-weight: 700;
            }

            QLabel#InfoDescription {
                color: #687573;
                font-size: 15px;
            }

            QFrame#InfoCard {
                background: #FFFFFF;
                border: 1px solid #D5DEDB;
                border-radius: 20px;
                min-height: 145px;
            }

            QLabel#InfoCardHeading {
                color: #26312F;
                font-size: 13px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            QLabel#InfoCardBody {
                color: #71807D;
                font-size: 13px;
            }
            """

        self.about_page.setStyleSheet(style)
        self.how_page.setStyleSheet(style)

    # ---------------------------------------------------------
    # NAVIGATION
    # ---------------------------------------------------------

    def show_page(self, index):
        if index < 0 or index >= len(self.pages):
            return

        self.stack.setCurrentIndex(index)

        for i, button in enumerate(self.nav_buttons):
            button.setProperty("active", i == index)
            button.style().unpolish(button)
            button.style().polish(button)

    def open_about(self):
        self.stack.setCurrentIndex(self.about_index)

        for button in self.nav_buttons:
            button.setProperty("active", False)
            button.style().unpolish(button)
            button.style().polish(button)

    def open_how(self):
        self.stack.setCurrentIndex(self.how_index)

        for button in self.nav_buttons:
            button.setProperty("active", False)
            button.style().unpolish(button)
            button.style().polish(button)

    def handle_search(self, text=None):
        value = (text or self.search.text()).strip().lower()

        if not value:
            return

        routes = {
            "dashboard": 0,
            "home": 0,
            "cameras": 1,
            "camera": 1,
            "incidents": 2,
            "incident": 2,
            "alerts": 3,
            "alert": 3,
            "settings": 4,
            "setting": 4,
        }

        if value in routes:
            self.show_page(routes[value])
            return

        if "about" in value:
            self.open_about()
            return

        if "how" in value or "works" in value:
            self.open_how()

    # ---------------------------------------------------------
    # THEME
    # ---------------------------------------------------------

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()

    def apply_theme(self):
        self.setStyleSheet(
            DARK_STYLE if self.dark_mode else LIGHT_STYLE
        )

        self.theme_button.setText("☀" if self.dark_mode else "☾")

        self.style_info_pages()

        for page in self.pages:
            if hasattr(page, "set_theme"):
                try:
                    page.set_theme(self.dark_mode)
                except Exception:
                    pass

    # ---------------------------------------------------------
    # LOGIN
    # ---------------------------------------------------------

    def toggle_login(self):
        if self.login_button.text() == "Login":
            self.login_button.setText("Logout")
        else:
            self.login_button.setText("Login")

    # ---------------------------------------------------------
    # INCIDENTS
    # ---------------------------------------------------------

    def add_incident(self, camera, detection):
        self.incidents.add(
            camera,
            detection["event"],
            detection["confidence"],
            detection["severity"],
        )

        self.incident_page.refresh()
        self.alert_page.refresh()
        self.dashboard.refresh()

    # ---------------------------------------------------------
    # CLOSE
    # ---------------------------------------------------------

    def closeEvent(self, event):
        self.cameras.stop_all()
        event.accept()