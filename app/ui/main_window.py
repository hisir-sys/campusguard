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
    QScrollArea,
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


# ============================================================
# GLASS UI — DARK
# ============================================================

DARK_STYLE = """
QMainWindow {
    background: #080A0B;
}

QWidget {
    color: #E9EEED;
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
}

/* ==========================================================
   GLASS NAVBAR
   ========================================================== */

QFrame#TopBar {
    background: rgba(20, 25, 26, 235);
    border: 1px solid rgba(255, 255, 255, 24);
    border-radius: 22px;
}

QLabel#LogoDot {
    background: #78A9A2;
    border-radius: 5px;
}

QPushButton#LogoButton {
    background: transparent;
    color: #F3F7F6;
    border: none;
    border-radius: 12px;
    padding: 8px 10px;
    font-size: 17px;
    font-weight: 700;
}

QPushButton#LogoButton:hover {
    background: rgba(255, 255, 255, 10);
}

/* ==========================================================
   NAV LINKS
   ========================================================== */

QPushButton#TopButton {
    background: transparent;
    color: #879391;
    border: none;
    border-radius: 12px;
    padding: 9px 13px;
    font-size: 13px;
    font-weight: 500;
}

QPushButton#TopButton:hover {
    background: rgba(255, 255, 255, 12);
    color: #F2F6F5;
}

QPushButton#TopButton:pressed {
    background: rgba(255, 255, 255, 17);
}

/* ==========================================================
   SEARCH
   ========================================================== */

QLineEdit#SearchBox {
    background: rgba(8, 12, 13, 180);
    color: #E9EEED;
    border: 1px solid rgba(255, 255, 255, 22);
    border-radius: 13px;
    padding: 9px 14px;
    selection-background-color: #426965;
    font-size: 12px;
}

QLineEdit#SearchBox:focus {
    border: 1px solid rgba(120, 169, 162, 90);
    background: rgba(8, 12, 13, 220);
}

QLineEdit#SearchBox::placeholder {
    color: #657270;
}

/* ==========================================================
   NAVBAR ACTIONS
   ========================================================== */

QPushButton#ThemeButton {
    background: rgba(255, 255, 255, 9);
    color: #DDE5E3;
    border: 1px solid rgba(255, 255, 255, 22);
    border-radius: 12px;
    padding: 9px;
    font-size: 14px;
}

QPushButton#ThemeButton:hover {
    background: rgba(255, 255, 255, 16);
    border: 1px solid rgba(255, 255, 255, 35);
}

QPushButton#LoginButton {
    background: #E8EFED;
    color: #17201F;
    border: none;
    border-radius: 12px;
    padding: 9px 17px;
    font-size: 12px;
    font-weight: 700;
}

QPushButton#LoginButton:hover {
    background: #FFFFFF;
}

/* ==========================================================
   BOTTOM GLASS DOCK
   ========================================================== */

QFrame#BottomDock {
    background: rgba(20, 25, 26, 235);
    border: 1px solid rgba(255, 255, 255, 24);
    border-radius: 24px;
}

QPushButton#DockButton {
    background: transparent;
    color: #778482;
    border: 1px solid transparent;
    border-radius: 15px;
    padding: 10px 15px;
    min-width: 82px;
    font-size: 12px;
}

QPushButton#DockButton:hover {
    background: rgba(255, 255, 255, 10);
    color: #EAF0EF;
}

QPushButton#DockButton[active="true"] {
    background: rgba(120, 169, 162, 28);
    color: #F5F8F7;
    border: 1px solid rgba(120, 169, 162, 55);
}

/* ==========================================================
   CONTENT
   ========================================================== */

QFrame#ContentArea {
    background: transparent;
}

/* ==========================================================
   SEARCH COMPLETER
   ========================================================== */

QListView {
    background: #141A1B;
    color: #DCE5E2;
    border: 1px solid #2C3838;
    border-radius: 12px;
    padding: 5px;
}

QListView::item {
    padding: 8px 10px;
    border-radius: 8px;
}

QListView::item:hover {
    background: #202A2B;
}

QListView::item:selected {
    background: #293938;
    color: #FFFFFF;
}
"""


# ============================================================
# GLASS UI — LIGHT
# ============================================================

LIGHT_STYLE = """
QMainWindow {
    background: #EEF2F0;
}

QWidget {
    color: #17201F;
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
}

/* ==========================================================
   GLASS NAVBAR
   ========================================================== */

QFrame#TopBar {
    background: rgba(255, 255, 255, 238);
    border: 1px solid rgba(25, 45, 40, 28);
    border-radius: 22px;
}

QLabel#LogoDot {
    background: #527F79;
    border-radius: 5px;
}

QPushButton#LogoButton {
    background: transparent;
    color: #17201F;
    border: none;
    border-radius: 12px;
    padding: 8px 10px;
    font-size: 17px;
    font-weight: 700;
}

QPushButton#LogoButton:hover {
    background: rgba(30, 60, 55, 8);
}

/* ==========================================================
   NAV LINKS
   ========================================================== */

QPushButton#TopButton {
    background: transparent;
    color: #687573;
    border: none;
    border-radius: 12px;
    padding: 9px 13px;
    font-size: 13px;
    font-weight: 500;
}

QPushButton#TopButton:hover {
    background: rgba(30, 60, 55, 9);
    color: #17201F;
}

QPushButton#TopButton:pressed {
    background: rgba(30, 60, 55, 14);
}

/* ==========================================================
   SEARCH
   ========================================================== */

QLineEdit#SearchBox {
    background: rgba(246, 248, 247, 220);
    color: #17201F;
    border: 1px solid rgba(30, 50, 46, 24);
    border-radius: 13px;
    padding: 9px 14px;
    selection-background-color: #AFC8C3;
    font-size: 12px;
}

QLineEdit#SearchBox:focus {
    border: 1px solid rgba(82, 127, 121, 100);
    background: #FFFFFF;
}

QLineEdit#SearchBox::placeholder {
    color: #84918E;
}

/* ==========================================================
   NAVBAR ACTIONS
   ========================================================== */

QPushButton#ThemeButton {
    background: rgba(240, 244, 242, 220);
    color: #52615E;
    border: 1px solid rgba(30, 50, 46, 22);
    border-radius: 12px;
    padding: 9px;
    font-size: 14px;
}

QPushButton#ThemeButton:hover {
    background: #E8EEEB;
}

QPushButton#LoginButton {
    background: #17201F;
    color: #F5F8F7;
    border: none;
    border-radius: 12px;
    padding: 9px 17px;
    font-size: 12px;
    font-weight: 700;
}

QPushButton#LoginButton:hover {
    background: #273532;
}

/* ==========================================================
   BOTTOM GLASS DOCK
   ========================================================== */

QFrame#BottomDock {
    background: rgba(255, 255, 255, 238);
    border: 1px solid rgba(25, 45, 40, 28);
    border-radius: 24px;
}

QPushButton#DockButton {
    background: transparent;
    color: #71807D;
    border: 1px solid transparent;
    border-radius: 15px;
    padding: 10px 15px;
    min-width: 82px;
    font-size: 12px;
}

QPushButton#DockButton:hover {
    background: rgba(30, 60, 55, 8);
    color: #17201F;
}

QPushButton#DockButton[active="true"] {
    background: rgba(82, 127, 121, 20);
    color: #17201F;
    border: 1px solid rgba(82, 127, 121, 45);
}

/* ==========================================================
   CONTENT
   ========================================================== */

QFrame#ContentArea {
    background: transparent;
}

/* ==========================================================
   SEARCH COMPLETER
   ========================================================== */

QListView {
    background: #FFFFFF;
    color: #26312F;
    border: 1px solid #D3DDDA;
    border-radius: 12px;
    padding: 5px;
}

QListView::item {
    padding: 8px 10px;
    border-radius: 8px;
}

QListView::item:hover {
    background: #EEF3F1;
}

QListView::item:selected {
    background: #E0E9E6;
    color: #17201F;
}
"""


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("CampusGuard")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 720)

        self.dark_mode = True

        # ====================================================
        # BACKEND
        # ====================================================

        self.settings = load()
        self.incidents = IncidentManager()

        self.detector = Detector(
            self.settings["model_path"],
            self.settings["confidence"],
        )

        self.cameras = CameraManager()

        # ====================================================
        # UI
        # ====================================================

        self._build_ui()

        self.cameras.frame_ready.connect(
            self.camera_page.on_frame
        )

        self.cameras.error.connect(
            self.camera_page.on_error
        )

        self.apply_theme()

    # ========================================================
    # MAIN UI
    # ========================================================

    def _build_ui(self):

        root = QWidget()
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)

        root_layout.setContentsMargins(
            22,
            18,
            22,
            18,
        )

        root_layout.setSpacing(14)

        # ====================================================
        # TOP GLASS NAVBAR
        # ====================================================

        self.top_bar = QFrame()
        self.top_bar.setObjectName("TopBar")
        self.top_bar.setFixedHeight(68)

        top_layout = QHBoxLayout(self.top_bar)

        top_layout.setContentsMargins(
            14,
            9,
            14,
            9,
        )

        top_layout.setSpacing(5)

        # ----------------------------------------------------
        # LOGO
        # ----------------------------------------------------

        logo_wrap = QWidget()

        logo_layout = QHBoxLayout(logo_wrap)

        logo_layout.setContentsMargins(
            3,
            0,
            16,
            0,
        )

        logo_layout.setSpacing(9)

        self.logo_dot = QLabel()

        self.logo_dot.setObjectName("LogoDot")

        self.logo_dot.setFixedSize(
            10,
            10,
        )

        self.logo = QPushButton(
            "CampusGuard"
        )

        self.logo.setObjectName(
            "LogoButton"
        )

        self.logo.setCursor(
            Qt.PointingHandCursor
        )

        self.logo.setFont(
            QFont(
                "Segoe UI Variable",
                700,
            )
        )

        self.logo.clicked.connect(
            lambda: self.show_page(0)
        )

        logo_layout.addWidget(
            self.logo_dot
        )

        logo_layout.addWidget(
            self.logo
        )

        top_layout.addWidget(
            logo_wrap
        )

        # ====================================================
        # NAVIGATION LINKS
        # ====================================================

        self.home_button = QPushButton(
            "Home"
        )

        self.home_button.setObjectName(
            "TopButton"
        )

        self.home_button.setCursor(
            Qt.PointingHandCursor
        )

        self.home_button.clicked.connect(
            lambda: self.show_page(0)
        )

        top_layout.addWidget(
            self.home_button
        )

        self.services_button = QPushButton(
            "Services"
        )

        self.services_button.setObjectName(
            "TopButton"
        )

        self.services_button.setCursor(
            Qt.PointingHandCursor
        )

        self.services_button.clicked.connect(
            lambda: self.show_page(1)
        )

        top_layout.addWidget(
            self.services_button
        )

        self.about_button = QPushButton(
            "About"
        )

        self.about_button.setObjectName(
            "TopButton"
        )

        self.about_button.setCursor(
            Qt.PointingHandCursor
        )

        self.about_button.clicked.connect(
            self.open_about
        )

        top_layout.addWidget(
            self.about_button
        )

        self.tools_button = QPushButton(
            "Tools"
        )

        self.tools_button.setObjectName(
            "TopButton"
        )

        self.tools_button.setCursor(
            Qt.PointingHandCursor
        )

        self.tools_button.clicked.connect(
            lambda: self.show_page(4)
        )

        top_layout.addWidget(
            self.tools_button
        )

        self.how_button = QPushButton(
            "How It Works"
        )

        self.how_button.setObjectName(
            "TopButton"
        )

        self.how_button.setCursor(
            Qt.PointingHandCursor
        )

        self.how_button.clicked.connect(
            self.open_how
        )

        top_layout.addWidget(
            self.how_button
        )

        # ====================================================
        # SPACER
        # ====================================================

        top_layout.addStretch(1)

        # ====================================================
        # SEARCH
        # ====================================================

        search_wrap = QWidget()

        search_layout = QHBoxLayout(
            search_wrap
        )

        search_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        search_layout.setSpacing(0)

        self.search = QLineEdit()

        self.search.setObjectName(
            "SearchBox"
        )

        self.search.setPlaceholderText(
            "⌕  Search CampusGuard..."
        )

        self.search.setFixedWidth(
            230
        )

        self.search.setClearButtonEnabled(
            True
        )

        search_items = [
            "Dashboard",
            "Home",
            "Cameras",
            "Camera",
            "Incidents",
            "Incident",
            "Alerts",
            "Alert",
            "Settings",
            "About",
            "How It Works",
            "Services",
            "Tools",
        ]

        self.search_model = QStringListModel(
            search_items
        )

        completer = QCompleter(
            self.search_model,
            self,
        )

        completer.setCaseSensitivity(
            Qt.CaseInsensitive
        )

        completer.setFilterMode(
            Qt.MatchContains
        )

        self.search.setCompleter(
            completer
        )

        completer.activated.connect(
            self.handle_search
        )

        self.search.returnPressed.connect(
            self.handle_search
        )

        search_layout.addWidget(
            self.search
        )

        top_layout.addWidget(
            search_wrap
        )

        # ====================================================
        # THEME BUTTON
        # ====================================================

        self.theme_button = QPushButton(
            "☾"
        )

        self.theme_button.setObjectName(
            "ThemeButton"
        )

        self.theme_button.setCursor(
            Qt.PointingHandCursor
        )

        self.theme_button.setFixedWidth(
            42
        )

        self.theme_button.clicked.connect(
            self.toggle_theme
        )

        top_layout.addWidget(
            self.theme_button
        )

        # ====================================================
        # LOGIN
        # ====================================================

        self.login_button = QPushButton(
            "Log in"
        )

        self.login_button.setObjectName(
            "LoginButton"
        )

        self.login_button.setCursor(
            Qt.PointingHandCursor
        )

        self.login_button.clicked.connect(
            self.toggle_login
        )

        top_layout.addWidget(
            self.login_button
        )

        root_layout.addWidget(
            self.top_bar
        )

        # ====================================================
        # CONTENT AREA
        # ====================================================

        self.content_area = QFrame()

        self.content_area.setObjectName(
            "ContentArea"
        )

        content_layout = QVBoxLayout(
            self.content_area
        )

        content_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self.stack = QStackedWidget()

        content_layout.addWidget(
            self.stack
        )

        root_layout.addWidget(
            self.content_area,
            1,
        )

        # ====================================================
        # APPLICATION PAGES
        # ====================================================

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

        # ====================================================
        # INFORMATION PAGES
        # ====================================================

        self.about_page = self.create_about_page()
        self.how_page = self.create_how_page()

        self.about_index = self.stack.addWidget(
            self.about_page
        )

        self.how_index = self.stack.addWidget(
            self.how_page
        )

        # ====================================================
        # BOTTOM GLASS DOCK
        # ====================================================

        self.bottom_dock = QFrame()

        self.bottom_dock.setObjectName(
            "BottomDock"
        )

        self.bottom_dock.setFixedHeight(
            70
        )

        dock_layout = QHBoxLayout(
            self.bottom_dock
        )

        dock_layout.setContentsMargins(
            12,
            8,
            12,
            8,
        )

        dock_layout.setSpacing(
            5
        )

        self.nav_buttons = []

        nav_items = [
            ("⌂", "Dashboard"),
            ("▣", "Cameras"),
            ("◫", "Incidents"),
            ("!", "Alerts"),
            ("⚙", "Settings"),
        ]

        for index, (icon, label) in enumerate(
            nav_items
        ):

            button = QPushButton(
                f"{icon}   {label}"
            )

            button.setObjectName(
                "DockButton"
            )

            button.setCursor(
                Qt.PointingHandCursor
            )

            button.setProperty(
                "active",
                index == 0,
            )

            button.clicked.connect(
                lambda checked=False, i=index:
                self.show_page(i)
            )

            dock_layout.addWidget(
                button
            )

            self.nav_buttons.append(
                button
            )

        root_layout.addWidget(
            self.bottom_dock,
            0,
            Qt.AlignHCenter,
        )

    # ========================================================
    # SCROLLABLE PAGE
    # ========================================================

    def create_scroll_page(self):

        scroll = QScrollArea()

        scroll.setWidgetResizable(
            True
        )

        scroll.setFrameShape(
            QFrame.NoFrame
        )

        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
        )

        content = QWidget()

        layout = QVBoxLayout(
            content
        )

        layout.setContentsMargins(
            42,
            34,
            42,
            50,
        )

        layout.setSpacing(
            22
        )

        scroll.setWidget(
            content
        )

        return (
            scroll,
            content,
            layout,
        )

    # ========================================================
    # ABOUT PAGE
    # ========================================================

    def create_about_page(self):

        scroll, content, layout = (
            self.create_scroll_page()
        )

        eyebrow = QLabel(
            "ABOUT CAMPUSGUARD"
        )

        eyebrow.setObjectName(
            "InfoEyebrow"
        )

        title = QLabel(
            "A clearer way to understand campus safety."
        )

        title.setObjectName(
            "InfoTitle"
        )

        title.setWordWrap(
            True
        )

        description = QLabel(
            "CampusGuard is an AI-assisted campus safety monitoring "
            "platform designed to bring camera monitoring, detection, "
            "incident management and alerts into one focused workspace."
        )

        description.setObjectName(
            "InfoDescription"
        )

        description.setWordWrap(
            True
        )

        description.setMaximumWidth(
            900
        )

        layout.addWidget(
            eyebrow
        )

        layout.addWidget(
            title
        )

        layout.addWidget(
            description
        )

        layout.addWidget(
            self.section_heading(
                "What is CampusGuard?",
                "A unified monitoring workspace",
            )
        )

        what_card = self.text_card(
            "CampusGuard brings the main parts of a safety monitoring "
            "workflow together. Instead of switching between separate "
            "camera views, incident records and alert systems, the "
            "platform provides a single operational interface.",
            [
                "Monitor connected camera sources.",
                "Process incoming frames through the detection engine.",
                "Record relevant incidents.",
                "Review important events through the alert system.",
                "Keep the monitoring workflow organized in one place.",
            ],
        )

        layout.addWidget(
            what_card
        )

        layout.addWidget(
            self.section_heading(
                "Core capabilities",
                "The main building blocks of the platform",
            )
        )

        capability_row = QHBoxLayout()

        capability_row.setSpacing(
            14
        )

        capabilities = [
            (
                "LIVE MONITORING",
                "Connect and observe camera sources from a centralized interface.",
            ),
            (
                "AI-ASSISTED DETECTION",
                "Analyze incoming frames and identify relevant safety events.",
            ),
            (
                "INCIDENT MANAGEMENT",
                "Keep detected events organized with useful operational information.",
            ),
            (
                "ALERT AWARENESS",
                "Surface important events through a dedicated notification workflow.",
            ),
        ]

        for heading, body in capabilities:

            capability_row.addWidget(
                self.feature_card(
                    heading,
                    body,
                ),
                1,
            )

        layout.addLayout(
            capability_row
        )

        layout.addWidget(
            self.section_heading(
                "The idea behind the project",
                "Designed around clarity and response",
            )
        )

        mission_card = self.text_card(
            "The goal is not simply to display camera feeds. The goal "
            "is to make a large amount of monitoring information easier "
            "to understand at a glance.",
            [
                "See what is happening.",
                "Understand which events matter.",
                "Keep incidents organized.",
                "Move from detection to response without unnecessary complexity.",
            ],
        )

        layout.addWidget(
            mission_card
        )

        layout.addWidget(
            self.section_heading(
                "CampusGuard at a glance",
                "From camera input to operational awareness",
            )
        )

        flow = self.create_flow(
            [
                (
                    "CAMERA",
                    "Connected video source",
                ),
                (
                    "PROCESS",
                    "Frames enter the detection pipeline",
                ),
                (
                    "DETECT",
                    "Relevant events are identified",
                ),
                (
                    "INCIDENT",
                    "Events are recorded",
                ),
                (
                    "ALERT",
                    "Important information reaches the operator",
                ),
            ]
        )

        layout.addWidget(
            flow
        )

        layout.addWidget(
            self.section_heading(
                "Designed for people",
                "Information should be understandable",
            )
        )

        user_card = self.text_card(
            "CampusGuard is designed with the operator in mind. The "
            "interface separates live monitoring from historical incidents "
            "and alerts, while keeping the navigation simple.",
            [
                "Clear visual hierarchy.",
                "Minimal navigation.",
                "Readable operational information.",
                "Dark and light workspace themes.",
                "Responsive camera monitoring layout.",
            ],
        )

        layout.addWidget(
            user_card
        )

        closing = QFrame()

        closing.setObjectName(
            "InfoClosing"
        )

        closing_layout = QVBoxLayout(
            closing
        )

        closing_layout.setContentsMargins(
            24,
            24,
            24,
            24,
        )

        closing_title = QLabel(
            "CampusGuard"
        )

        closing_title.setObjectName(
            "ClosingTitle"
        )

        closing_text = QLabel(
            "Monitor. Understand. Respond."
        )

        closing_text.setObjectName(
            "ClosingText"
        )

        closing_layout.addWidget(
            closing_title
        )

        closing_layout.addWidget(
            closing_text
        )

        layout.addWidget(
            closing
        )

        layout.addStretch()

        return scroll

    # ========================================================
    # HOW IT WORKS
    # ========================================================

    def create_how_page(self):

        scroll, content, layout = (
            self.create_scroll_page()
        )

        eyebrow = QLabel(
            "HOW IT WORKS"
        )

        eyebrow.setObjectName(
            "InfoEyebrow"
        )

        title = QLabel(
            "From camera feed to campus awareness."
        )

        title.setObjectName(
            "InfoTitle"
        )

        title.setWordWrap(
            True
        )

        description = QLabel(
            "CampusGuard follows a simple monitoring pipeline. Camera "
            "sources provide frames, the detection engine analyzes them, "
            "and relevant events become incidents and alerts."
        )

        description.setObjectName(
            "InfoDescription"
        )

        description.setWordWrap(
            True
        )

        description.setMaximumWidth(
            900
        )

        layout.addWidget(
            eyebrow
        )

        layout.addWidget(
            title
        )

        layout.addWidget(
            description
        )

        layout.addWidget(
            self.section_heading(
                "The monitoring pipeline",
                "Five simple stages",
            )
        )

        main_flow = self.create_flow(
            [
                ("01", "CAMERA INPUT"),
                ("02", "FRAME PROCESSING"),
                ("03", "AI DETECTION"),
                ("04", "INCIDENT"),
                ("05", "ALERT / REVIEW"),
            ]
        )

        layout.addWidget(
            main_flow
        )

        layout.addWidget(
            self.section_heading(
                "Step by step",
                "What happens at each stage",
            )
        )

        steps = [
            (
                "01",
                "Camera input",
                "A connected webcam or supported video source provides "
                "the frames used by the monitoring system.",
            ),
            (
                "02",
                "Frame processing",
                "Incoming frames are passed through the camera and "
                "detection pipeline for analysis.",
            ),
            (
                "03",
                "AI-assisted detection",
                "The detection engine examines the frame and can identify "
                "events relevant to the configured monitoring workflow.",
            ),
            (
                "04",
                "Incident creation",
                "When a relevant event is detected, CampusGuard can record "
                "information such as the camera, event, confidence and severity.",
            ),
            (
                "05",
                "Alert and review",
                "Recorded information becomes available through the "
                "incident and alert areas so the operator can review it.",
            ),
        ]

        for number, heading, body in steps:

            layout.addWidget(
                self.numbered_card(
                    number,
                    heading,
                    body,
                )
            )

        layout.addWidget(
            self.section_heading(
                "Operator workflow",
                "What the user sees",
            )
        )

        operator_flow = self.create_flow(
            [
                (
                    "VIEW",
                    "See connected cameras",
                ),
                (
                    "NOTICE",
                    "Detection surfaces an event",
                ),
                (
                    "REVIEW",
                    "Check incident information",
                ),
                (
                    "RESPOND",
                    "Take the appropriate action",
                ),
            ]
        )

        layout.addWidget(
            operator_flow
        )

        layout.addWidget(
            self.section_heading(
                "Information flow",
                "How information moves through CampusGuard",
            )
        )

        data_card = self.text_card(
            "The interface separates different types of operational "
            "information so that the operator can move between them "
            "without losing context.",
            [
                "Cameras → live visual information.",
                "Detection → identified events.",
                "Incidents → recorded event history.",
                "Alerts → important notifications.",
                "Dashboard → high-level operational overview.",
            ],
        )

        layout.addWidget(
            data_card
        )

        layout.addWidget(
            self.section_heading(
                "Application structure",
                "The major components working together",
            )
        )

        architecture_flow = self.create_flow(
            [
                (
                    "UI",
                    "CampusGuard desktop interface",
                ),
                (
                    "CAMERA",
                    "Camera manager",
                ),
                (
                    "ENGINE",
                    "Detection engine",
                ),
                (
                    "DATA",
                    "Incident manager",
                ),
                (
                    "OUTPUT",
                    "Alerts and dashboard",
                ),
            ]
        )

        layout.addWidget(
            architecture_flow
        )

        final_card = self.text_card(
            "The result is a single workspace where live monitoring, "
            "AI-assisted analysis and incident awareness are connected "
            "instead of being treated as separate systems."
        )

        layout.addWidget(
            final_card
        )

        layout.addStretch()

        return scroll

    # ========================================================
    # COMPONENT HELPERS
    # ========================================================

    def section_heading(
        self,
        title,
        subtitle,
    ):

        wrapper = QWidget()

        layout = QVBoxLayout(
            wrapper
        )

        layout.setContentsMargins(
            0,
            8,
            0,
            0,
        )

        layout.setSpacing(
            4
        )

        title_label = QLabel(
            title
        )

        title_label.setObjectName(
            "SectionTitle"
        )

        subtitle_label = QLabel(
            subtitle
        )

        subtitle_label.setObjectName(
            "SectionSubtitle"
        )

        layout.addWidget(
            title_label
        )

        layout.addWidget(
            subtitle_label
        )

        return wrapper

    # ========================================================

    def text_card(
        self,
        paragraph,
        bullets=None,
    ):

        card = QFrame()

        card.setObjectName(
            "InfoTextCard"
        )

        layout = QVBoxLayout(
            card
        )

        layout.setContentsMargins(
            22,
            20,
            22,
            20,
        )

        layout.setSpacing(
            10
        )

        text = QLabel(
            paragraph
        )

        text.setObjectName(
            "InfoCardText"
        )

        text.setWordWrap(
            True
        )

        layout.addWidget(
            text
        )

        if bullets:

            for bullet in bullets:

                row = QHBoxLayout()

                row.setSpacing(
                    10
                )

                dot = QLabel(
                    "•"
                )

                dot.setObjectName(
                    "BulletDot"
                )

                label = QLabel(
                    bullet
                )

                label.setObjectName(
                    "BulletText"
                )

                label.setWordWrap(
                    True
                )

                row.addWidget(
                    dot
                )

                row.addWidget(
                    label,
                    1,
                )

                layout.addLayout(
                    row
                )

        return card

    # ========================================================

    def feature_card(
        self,
        heading,
        body,
    ):

        card = QFrame()

        card.setObjectName(
            "FeatureCard"
        )

        layout = QVBoxLayout(
            card
        )

        layout.setContentsMargins(
            18,
            18,
            18,
            18,
        )

        layout.setSpacing(
            10
        )

        heading_label = QLabel(
            heading
        )

        heading_label.setObjectName(
            "FeatureHeading"
        )

        heading_label.setWordWrap(
            True
        )

        body_label = QLabel(
            body
        )

        body_label.setObjectName(
            "FeatureBody"
        )

        body_label.setWordWrap(
            True
        )

        layout.addWidget(
            heading_label
        )

        layout.addWidget(
            body_label
        )

        layout.addStretch()

        return card

    # ========================================================

    def numbered_card(
        self,
        number,
        heading,
        body,
    ):

        card = QFrame()

        card.setObjectName(
            "StepCard"
        )

        layout = QHBoxLayout(
            card
        )

        layout.setContentsMargins(
            18,
            17,
            18,
            17,
        )

        layout.setSpacing(
            16
        )

        number_label = QLabel(
            number
        )

        number_label.setObjectName(
            "StepNumber"
        )

        number_label.setAlignment(
            Qt.AlignCenter
        )

        number_label.setFixedSize(
            44,
            44,
        )

        text_layout = QVBoxLayout()

        text_layout.setSpacing(
            5
        )

        heading_label = QLabel(
            heading
        )

        heading_label.setObjectName(
            "StepHeading"
        )

        body_label = QLabel(
            body
        )

        body_label.setObjectName(
            "StepBody"
        )

        body_label.setWordWrap(
            True
        )

        text_layout.addWidget(
            heading_label
        )

        text_layout.addWidget(
            body_label
        )

        layout.addWidget(
            number_label
        )

        layout.addLayout(
            text_layout,
            1,
        )

        return card

    # ========================================================

    def create_flow(
        self,
        items,
    ):

        container = QFrame()

        container.setObjectName(
            "FlowContainer"
        )

        outer = QVBoxLayout(
            container
        )

        outer.setContentsMargins(
            18,
            18,
            18,
            18,
        )

        flow = QHBoxLayout()

        flow.setSpacing(
            8
        )

        for index, item in enumerate(
            items
        ):

            box = QFrame()

            box.setObjectName(
                "FlowBox"
            )

            box_layout = QVBoxLayout(
                box
            )

            box_layout.setContentsMargins(
                14,
                16,
                14,
                16,
            )

            box_layout.setSpacing(
                7
            )

            top = QLabel(
                item[0]
            )

            top.setObjectName(
                "FlowTop"
            )

            bottom = QLabel(
                item[1]
            )

            bottom.setObjectName(
                "FlowBottom"
            )

            bottom.setWordWrap(
                True
            )

            box_layout.addWidget(
                top
            )

            box_layout.addWidget(
                bottom
            )

            flow.addWidget(
                box,
                1,
            )

            if index < len(items) - 1:

                arrow = QLabel(
                    "→"
                )

                arrow.setObjectName(
                    "FlowArrow"
                )

                arrow.setAlignment(
                    Qt.AlignCenter
                )

                arrow.setFixedWidth(
                    25
                )

                flow.addWidget(
                    arrow
                )

        outer.addLayout(
            flow
        )

        return container

    # ========================================================
    # INFORMATION PAGE THEME
    # ========================================================

    def style_info_pages(self):

        if self.dark_mode:

            style = """
            QScrollArea {
                background: transparent;
                border: none;
            }

            QWidget {
                background: transparent;
            }

            QLabel#InfoEyebrow {
                color: #70928D;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 2px;
            }

            QLabel#InfoTitle {
                color: #F1F5F3;
                font-size: 34px;
                font-weight: 700;
            }

            QLabel#InfoDescription {
                color: #899795;
                font-size: 15px;
            }

            QLabel#SectionTitle {
                color: #E8EFED;
                font-size: 20px;
                font-weight: 700;
            }

            QLabel#SectionSubtitle {
                color: #687774;
                font-size: 12px;
            }

            QFrame#InfoTextCard {
                background: rgba(18, 24, 25, 220);
                border: 1px solid rgba(255, 255, 255, 18);
                border-radius: 19px;
            }

            QLabel#InfoCardText {
                color: #AEB9B7;
                font-size: 13px;
            }

            QLabel#BulletDot {
                color: #78A9A2;
                font-size: 16px;
            }

            QLabel#BulletText {
                color: #899694;
                font-size: 12px;
            }

            QFrame#FeatureCard {
                background: rgba(18, 24, 25, 220);
                border: 1px solid rgba(255, 255, 255, 18);
                border-radius: 18px;
                min-height: 125px;
            }

            QFrame#FeatureCard:hover {
                background: rgba(24, 32, 33, 235);
                border: 1px solid rgba(120, 169, 162, 55);
            }

            QLabel#FeatureHeading {
                color: #DDE6E3;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            QLabel#FeatureBody {
                color: #7F8E8B;
                font-size: 12px;
            }

            QFrame#StepCard {
                background: rgba(18, 24, 25, 220);
                border: 1px solid rgba(255, 255, 255, 18);
                border-radius: 18px;
            }

            QLabel#StepNumber {
                color: #86AFA9;
                background: rgba(120, 169, 162, 18);
                border: 1px solid rgba(120, 169, 162, 35);
                border-radius: 12px;
                font-size: 11px;
                font-weight: 700;
            }

            QLabel#StepHeading {
                color: #E1E9E6;
                font-size: 14px;
                font-weight: 700;
            }

            QLabel#StepBody {
                color: #808E8C;
                font-size: 12px;
            }

            QFrame#FlowContainer {
                background: rgba(14, 19, 20, 220);
                border: 1px solid rgba(255, 255, 255, 18);
                border-radius: 20px;
            }

            QFrame#FlowBox {
                background: rgba(21, 29, 30, 225);
                border: 1px solid rgba(120, 169, 162, 30);
                border-radius: 15px;
                min-height: 80px;
            }

            QFrame#FlowBox:hover {
                background: rgba(28, 38, 39, 240);
                border: 1px solid rgba(120, 169, 162, 60);
            }

            QLabel#FlowTop {
                color: #75A19A;
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            QLabel#FlowBottom {
                color: #D7E0DE;
                font-size: 11px;
                font-weight: 600;
            }

            QLabel#FlowArrow {
                color: #5E7E79;
                font-size: 20px;
            }

            QFrame#InfoClosing {
                background: rgba(21, 29, 30, 225);
                border: 1px solid rgba(120, 169, 162, 35);
                border-radius: 20px;
            }

            QLabel#ClosingTitle {
                color: #E8EFED;
                font-size: 18px;
                font-weight: 700;
            }

            QLabel#ClosingText {
                color: #78938E;
                font-size: 12px;
            }

            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 5px 1px 5px 1px;
            }

            QScrollBar::handle:vertical {
                background: #334442;
                border-radius: 4px;
                min-height: 35px;
            }

            QScrollBar::handle:vertical:hover {
                background: #4B625E;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
            """

        else:

            style = """
            QScrollArea {
                background: transparent;
                border: none;
            }

            QWidget {
                background: transparent;
            }

            QLabel#InfoEyebrow {
                color: #527F79;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 2px;
            }

            QLabel#InfoTitle {
                color: #18211F;
                font-size: 34px;
                font-weight: 700;
            }

            QLabel#InfoDescription {
                color: #697774;
                font-size: 15px;
            }

            QLabel#SectionTitle {
                color: #1C2724;
                font-size: 20px;
                font-weight: 700;
            }

            QLabel#SectionSubtitle {
                color: #74817E;
                font-size: 12px;
            }

            QFrame#InfoTextCard {
                background: rgba(255, 255, 255, 230);
                border: 1px solid rgba(30, 50, 46, 22);
                border-radius: 19px;
            }

            QLabel#InfoCardText {
                color: #596865;
                font-size: 13px;
            }

            QLabel#BulletDot {
                color: #527F79;
                font-size: 16px;
            }

            QLabel#BulletText {
                color: #687672;
                font-size: 12px;
            }

            QFrame#FeatureCard {
                background: rgba(255, 255, 255, 230);
                border: 1px solid rgba(30, 50, 46, 22);
                border-radius: 18px;
                min-height: 125px;
            }

            QFrame#FeatureCard:hover {
                background: #FFFFFF;
                border: 1px solid rgba(82, 127, 121, 75);
            }

            QLabel#FeatureHeading {
                color: #283532;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            QLabel#FeatureBody {
                color: #71807C;
                font-size: 12px;
            }

            QFrame#StepCard {
                background: rgba(255, 255, 255, 230);
                border: 1px solid rgba(30, 50, 46, 22);
                border-radius: 18px;
            }

            QLabel#StepNumber {
                color: #527F79;
                background: #E7EFEC;
                border: 1px solid #CBD9D5;
                border-radius: 12px;
                font-size: 11px;
                font-weight: 700;
            }

            QLabel#StepHeading {
                color: #26312F;
                font-size: 14px;
                font-weight: 700;
            }

            QLabel#StepBody {
                color: #71807D;
                font-size: 12px;
            }

            QFrame#FlowContainer {
                background: rgba(232, 238, 235, 225);
                border: 1px solid rgba(30, 50, 46, 20);
                border-radius: 20px;
            }

            QFrame#FlowBox {
                background: rgba(255, 255, 255, 235);
                border: 1px solid rgba(82, 127, 121, 35);
                border-radius: 15px;
                min-height: 80px;
            }

            QFrame#FlowBox:hover {
                border: 1px solid rgba(82, 127, 121, 75);
            }

            QLabel#FlowTop {
                color: #527F79;
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            QLabel#FlowBottom {
                color: #34413E;
                font-size: 11px;
                font-weight: 600;
            }

            QLabel#FlowArrow {
                color: #67827D;
                font-size: 20px;
            }

            QFrame#InfoClosing {
                background: rgba(255, 255, 255, 235);
                border: 1px solid rgba(82, 127, 121, 35);
                border-radius: 20px;
            }

            QLabel#ClosingTitle {
                color: #26312F;
                font-size: 18px;
                font-weight: 700;
            }

            QLabel#ClosingText {
                color: #66807B;
                font-size: 12px;
            }

            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 5px 1px 5px 1px;
            }

            QScrollBar::handle:vertical {
                background: #C2D0CB;
                border-radius: 4px;
                min-height: 35px;
            }

            QScrollBar::handle:vertical:hover {
                background: #9FB4AE;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
            """

        self.about_page.setStyleSheet(
            style
        )

        self.how_page.setStyleSheet(
            style
        )

    # ========================================================
    # NAVIGATION
    # ========================================================

    def show_page(
        self,
        index,
    ):

        if index < 0 or index >= len(
            self.pages
        ):
            return

        self.stack.setCurrentIndex(
            index
        )

        for i, button in enumerate(
            self.nav_buttons
        ):

            button.setProperty(
                "active",
                i == index,
            )

            button.style().unpolish(
                button
            )

            button.style().polish(
                button
            )

    # ========================================================

    def open_about(self):

        self.stack.setCurrentIndex(
            self.about_index
        )

        for button in self.nav_buttons:

            button.setProperty(
                "active",
                False,
            )

            button.style().unpolish(
                button
            )

            button.style().polish(
                button
            )

    # ========================================================

    def open_how(self):

        self.stack.setCurrentIndex(
            self.how_index
        )

        for button in self.nav_buttons:

            button.setProperty(
                "active",
                False,
            )

            button.style().unpolish(
                button
            )

            button.style().polish(
                button
            )

    # ========================================================
    # SEARCH
    # ========================================================

    def handle_search(
        self,
        text=None,
    ):

        value = (
            text or self.search.text()
        ).strip().lower()

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

            self.show_page(
                routes[value]
            )

            return

        if "about" in value:

            self.open_about()

            return

        if "how" in value or "works" in value:

            self.open_how()

            return

        if "service" in value:

            self.show_page(1)

            return

        if "tool" in value:

            self.show_page(4)

            return

    # ========================================================
    # THEME
    # ========================================================

    def toggle_theme(self):

        self.dark_mode = not self.dark_mode

        self.apply_theme()

    # ========================================================

    def apply_theme(self):

        self.setStyleSheet(
            DARK_STYLE
            if self.dark_mode
            else LIGHT_STYLE
        )

        self.theme_button.setText(
            "☀"
            if self.dark_mode
            else "☾"
        )

        self.style_info_pages()

        for page in self.pages:

            if hasattr(
                page,
                "set_theme",
            ):

                try:

                    page.set_theme(
                        self.dark_mode
                    )

                except Exception:

                    pass

    # ========================================================
    # LOGIN
    # ========================================================

    def toggle_login(self):

        if self.login_button.text() == "Log in":

            self.login_button.setText(
                "Log out"
            )

        else:

            self.login_button.setText(
                "Log in"
            )

    # ========================================================
    # INCIDENTS
    # ========================================================

    def add_incident(
        self,
        camera,
        detection,
    ):

        self.incidents.add(
            camera,
            detection["event"],
            detection["confidence"],
            detection["severity"],
        )

        self.incident_page.refresh()
        self.alert_page.refresh()
        self.dashboard.refresh()

    # ========================================================
    # CLOSE
    # ========================================================

    def closeEvent(
        self,
        event,
    ):

        self.cameras.stop_all()

        event.accept()