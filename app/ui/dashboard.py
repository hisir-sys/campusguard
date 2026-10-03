from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QPushButton,
    QSizePolicy,
)


class CameraPanel(QFrame):
    def __init__(self, camera_number):
        super().__init__()

        self.camera_number = camera_number
        self.setObjectName("CameraPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        header = QHBoxLayout()

        self.name = QLabel(f"CAMERA {camera_number}")
        self.name.setObjectName("CameraName")

        self.status = QLabel("●  STANDBY")
        self.status.setObjectName("CameraStatus")

        header.addWidget(self.name)
        header.addStretch()
        header.addWidget(self.status)

        layout.addLayout(header)

        self.feed = QLabel("WAITING FOR FEED")
        self.feed.setObjectName("CameraFeed")
        self.feed.setAlignment(Qt.AlignCenter)
        self.feed.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        layout.addWidget(self.feed, 1)

        footer = QHBoxLayout()

        self.location = QLabel("CONNECTED SOURCE")
        self.location.setObjectName("CameraFooter")

        self.expand = QPushButton("↗")
        self.expand.setObjectName("CameraExpand")
        self.expand.setFixedSize(30, 30)

        footer.addWidget(self.location)
        footer.addStretch()
        footer.addWidget(self.expand)

        layout.addLayout(footer)

    def set_frame(self, pixmap):
        self.feed.setPixmap(
            pixmap.scaled(
                self.feed.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

        self.feed.setText("")


class DashboardPage(QWidget):
    def __init__(self, main):
        super().__init__()

        self.main = main
        self.dark_mode = True

        self.camera_panels = []

        self.build_ui()
        self.set_theme(True)
        self.refresh()

    # ---------------------------------------------------------
    # UI
    # ---------------------------------------------------------

    def build_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 4, 8, 8)
        self.layout.setSpacing(18)

        # Header
        header = QHBoxLayout()

        title_area = QVBoxLayout()
        title_area.setSpacing(3)

        self.eyebrow = QLabel("CAMPUS OPERATIONS")
        self.eyebrow.setObjectName("Eyebrow")

        self.title = QLabel("Campus Overview")
        self.title.setObjectName("DashboardTitle")

        self.subtitle = QLabel(
            "Real-time monitoring, AI-assisted detection and incident awareness."
        )
        self.subtitle.setObjectName("DashboardSubtitle")

        title_area.addWidget(self.eyebrow)
        title_area.addWidget(self.title)
        title_area.addWidget(self.subtitle)

        header.addLayout(title_area)
        header.addStretch()

        self.system_status = QLabel("● SYSTEM ONLINE")
        self.system_status.setObjectName("SystemStatus")

        header.addWidget(self.system_status, 0, Qt.AlignBottom)

        self.layout.addLayout(header)

        # Main split
        main_area = QHBoxLayout()
        main_area.setSpacing(16)

        # -----------------------------------------------------
        # LEFT
        # -----------------------------------------------------

        left = QVBoxLayout()
        left.setSpacing(14)

        # AI engine
        self.ai_card = QFrame()
        self.ai_card.setObjectName("DashboardCard")

        ai_layout = QVBoxLayout(self.ai_card)
        ai_layout.setContentsMargins(18, 18, 18, 18)
        ai_layout.setSpacing(10)

        self.ai_label = QLabel("AI ENGINE")
        self.ai_label.setObjectName("CardLabel")

        self.ai_status = QLabel("READY")
        self.ai_status.setObjectName("LargeValue")

        self.ai_detail = QLabel(
            "Detection engine initialized and ready for incoming frames."
        )
        self.ai_detail.setObjectName("CardDetail")
        self.ai_detail.setWordWrap(True)

        ai_layout.addWidget(self.ai_label)
        ai_layout.addWidget(self.ai_status)
        ai_layout.addWidget(self.ai_detail)

        left.addWidget(self.ai_card)

        # Incident card
        self.incident_card = QFrame()
        self.incident_card.setObjectName("DashboardCard")

        incident_layout = QVBoxLayout(self.incident_card)
        incident_layout.setContentsMargins(18, 18, 18, 18)
        incident_layout.setSpacing(8)

        self.incident_label = QLabel("INCIDENTS")
        self.incident_label.setObjectName("CardLabel")

        self.incident_count = QLabel("0")
        self.incident_count.setObjectName("IncidentNumber")

        self.incident_detail = QLabel("No incidents recorded.")
        self.incident_detail.setObjectName("CardDetail")

        incident_layout.addWidget(self.incident_label)
        incident_layout.addWidget(self.incident_count)
        incident_layout.addWidget(self.incident_detail)

        left.addWidget(self.incident_card)

        # Notifications
        self.notifications_card = QFrame()
        self.notifications_card.setObjectName("DashboardCard")

        notifications_layout = QVBoxLayout(self.notifications_card)
        notifications_layout.setContentsMargins(18, 18, 18, 18)
        notifications_layout.setSpacing(10)

        self.notifications_title = QLabel("NOTIFICATIONS")
        self.notifications_title.setObjectName("CardLabel")

        notifications_layout.addWidget(self.notifications_title)

        self.notifications_container = QVBoxLayout()
        self.notifications_container.setSpacing(7)

        notifications_layout.addLayout(self.notifications_container)
        notifications_layout.addStretch()

        left.addWidget(self.notifications_card, 1)

        main_area.addLayout(left, 1)

        # -----------------------------------------------------
        # RIGHT - LIVE NETWORK
        # -----------------------------------------------------

        right = QVBoxLayout()
        right.setSpacing(10)

        network_header = QHBoxLayout()

        network_title_area = QVBoxLayout()
        network_title_area.setSpacing(2)

        self.network_label = QLabel("LIVE NETWORK")
        self.network_label.setObjectName("NetworkTitle")

        self.network_subtitle = QLabel("CONNECTED CAMERA SOURCES")
        self.network_subtitle.setObjectName("NetworkSubtitle")

        network_title_area.addWidget(self.network_label)
        network_title_area.addWidget(self.network_subtitle)

        network_header.addLayout(network_title_area)
        network_header.addStretch()

        self.camera_count = QLabel("04 CAMERAS")
        self.camera_count.setObjectName("CameraCount")

        network_header.addWidget(self.camera_count, 0, Qt.AlignVCenter)

        right.addLayout(network_header)

        # Camera grid
        grid_frame = QFrame()
        grid_frame.setObjectName("NetworkFrame")

        grid = QGridLayout(grid_frame)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setSpacing(12)

        for i in range(4):
            panel = CameraPanel(i + 1)
            self.camera_panels.append(panel)

            row = i // 2
            column = i % 2

            grid.addWidget(panel, row, column)

        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        right.addWidget(grid_frame, 1)

        main_area.addLayout(right, 2)

        self.layout.addLayout(main_area, 1)

    # ---------------------------------------------------------
    # THEME
    # ---------------------------------------------------------

    def set_theme(self, dark):
        self.dark_mode = dark

        if dark:
            self.setStyleSheet("""
            DashboardPage {
                background: transparent;
            }

            QLabel#Eyebrow {
                color: #6F8582;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 2px;
            }

            QLabel#DashboardTitle {
                color: #F0F5F3;
                font-size: 29px;
                font-weight: 700;
            }

            QLabel#DashboardSubtitle {
                color: #7F8C8B;
                font-size: 13px;
            }

            QLabel#SystemStatus {
                color: #83AAA4;
                font-size: 11px;
                font-weight: 700;
                padding: 8px 12px;
                background: #111A19;
                border: 1px solid #283B39;
                border-radius: 12px;
            }

            QFrame#DashboardCard {
                background: #111719;
                border: 1px solid #263133;
                border-radius: 19px;
            }

            QLabel#CardLabel {
                color: #71807E;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1.5px;
            }

            QLabel#LargeValue {
                color: #E9EFED;
                font-size: 25px;
                font-weight: 700;
            }

            QLabel#IncidentNumber {
                color: #E8EEEC;
                font-size: 38px;
                font-weight: 700;
            }

            QLabel#CardDetail {
                color: #778583;
                font-size: 12px;
            }

            QLabel#NetworkTitle {
                color: #E8EFED;
                font-size: 18px;
                font-weight: 700;
            }

            QLabel#NetworkSubtitle {
                color: #687674;
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1.3px;
            }

            QLabel#CameraCount {
                color: #7EA39E;
                background: #111A19;
                border: 1px solid #283B39;
                border-radius: 11px;
                padding: 7px 10px;
                font-size: 10px;
                font-weight: 700;
            }

            QFrame#NetworkFrame {
                background: #0D1213;
                border: 1px solid #222C2E;
                border-radius: 21px;
            }

            QFrame#CameraPanel {
                background: #151B1D;
                border: 1px solid #293436;
                border-radius: 17px;
            }

            QFrame#CameraPanel:hover {
                border: 1px solid #3B514E;
            }

            QLabel#CameraName {
                color: #DCE5E3;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            QLabel#CameraStatus {
                color: #6E9A93;
                font-size: 9px;
                font-weight: 700;
            }

            QLabel#CameraFeed {
                background: #0A0D0E;
                border: 1px solid #222B2D;
                border-radius: 12px;
                color: #52615F;
                font-size: 10px;
                letter-spacing: 1px;
            }

            QLabel#CameraFooter {
                color: #657370;
                font-size: 8px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            QPushButton#CameraExpand {
                background: #1D2729;
                color: #A9B6B4;
                border: 1px solid #334143;
                border-radius: 9px;
            }

            QPushButton#CameraExpand:hover {
                background: #293637;
                color: #FFFFFF;
            }
            """)
        else:
            self.setStyleSheet("""
            DashboardPage {
                background: transparent;
            }

            QLabel#Eyebrow {
                color: #66817C;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 2px;
            }

            QLabel#DashboardTitle {
                color: #18211F;
                font-size: 29px;
                font-weight: 700;
            }

            QLabel#DashboardSubtitle {
                color: #6C7A77;
                font-size: 13px;
            }

            QLabel#SystemStatus {
                color: #527F79;
                font-size: 11px;
                font-weight: 700;
                padding: 8px 12px;
                background: #E7EFEC;
                border: 1px solid #CBD9D5;
                border-radius: 12px;
            }

            QFrame#DashboardCard {
                background: #FFFFFF;
                border: 1px solid #D4DEDA;
                border-radius: 19px;
            }

            QLabel#CardLabel {
                color: #71807D;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1.5px;
            }

            QLabel#LargeValue {
                color: #1B2523;
                font-size: 25px;
                font-weight: 700;
            }

            QLabel#IncidentNumber {
                color: #18211F;
                font-size: 38px;
                font-weight: 700;
            }

            QLabel#CardDetail {
                color: #74817E;
                font-size: 12px;
            }

            QLabel#NetworkTitle {
                color: #1B2523;
                font-size: 18px;
                font-weight: 700;
            }

            QLabel#NetworkSubtitle {
                color: #75827F;
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1.3px;
            }

            QLabel#CameraCount {
                color: #527F79;
                background: #E7EFEC;
                border: 1px solid #CBD9D5;
                border-radius: 11px;
                padding: 7px 10px;
                font-size: 10px;
                font-weight: 700;
            }

            QFrame#NetworkFrame {
                background: #E7ECEA;
                border: 1px solid #D1DBD7;
                border-radius: 21px;
            }

            QFrame#CameraPanel {
                background: #FFFFFF;
                border: 1px solid #D1DAD7;
                border-radius: 17px;
            }

            QFrame#CameraPanel:hover {
                border: 1px solid #AEBFBA;
            }

            QLabel#CameraName {
                color: #34413E;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            QLabel#CameraStatus {
                color: #527F79;
                font-size: 9px;
                font-weight: 700;
            }

            QLabel#CameraFeed {
                background: #EEF2F0;
                border: 1px solid #D4DEDA;
                border-radius: 12px;
                color: #7C8986;
                font-size: 10px;
                letter-spacing: 1px;
            }

            QLabel#CameraFooter {
                color: #7A8784;
                font-size: 8px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            QPushButton#CameraExpand {
                background: #EDF2F0;
                color: #596966;
                border: 1px solid #D0DAD7;
                border-radius: 9px;
            }

            QPushButton#CameraExpand:hover {
                background: #E1E9E6;
                color: #17201F;
            }
            """)

    # ---------------------------------------------------------
    # REFRESH
    # ---------------------------------------------------------

    def refresh(self):
        try:
            count = len(self.main.incidents.items)
        except Exception:
            count = 0

        self.incident_count.setText(str(count))

        if count == 0:
            self.incident_detail.setText("No incidents recorded.")
        elif count == 1:
            self.incident_detail.setText("1 incident requires review.")
        else:
            self.incident_detail.setText(
                f"{count} incidents currently recorded."
            )

        # Clear notifications
        while self.notifications_container.count():
            item = self.notifications_container.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        incidents = []

        try:
            incidents = list(self.main.incidents.items)[-4:]
            incidents.reverse()
        except Exception:
            pass

        if not incidents:
            self.add_notification(
                "SYSTEM",
                "Monitoring network is ready.",
            )
        else:
            for incident in incidents:
                event = incident.get("event", "Incident detected")
                camera = incident.get("camera", "Unknown camera")

                self.add_notification(
                    str(camera),
                    str(event),
                )

    # ---------------------------------------------------------
    # NOTIFICATION
    # ---------------------------------------------------------

    def add_notification(self, source, message):
        card = QFrame()
        card.setObjectName("NotificationItem")

        if self.dark_mode:
            card.setStyleSheet("""
            QFrame#NotificationItem {
                background: #151B1D;
                border: 1px solid #263133;
                border-radius: 13px;
            }

            QLabel#NotificationSource {
                color: #7EA39E;
                font-size: 9px;
                font-weight: 700;
            }

            QLabel#NotificationMessage {
                color: #C6D0CE;
                font-size: 11px;
            }
            """)
        else:
            card.setStyleSheet("""
            QFrame#NotificationItem {
                background: #F5F8F7;
                border: 1px solid #D7E0DD;
                border-radius: 13px;
            }

            QLabel#NotificationSource {
                color: #527F79;
                font-size: 9px;
                font-weight: 700;
            }

            QLabel#NotificationMessage {
                color: #44514E;
                font-size: 11px;
            }
            """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(3)

        source_label = QLabel(source.upper())
        source_label.setObjectName("NotificationSource")

        message_label = QLabel(message)
        message_label.setObjectName("NotificationMessage")
        message_label.setWordWrap(True)

        layout.addWidget(source_label)
        layout.addWidget(message_label)

        self.notifications_container.addWidget(card)

    # ---------------------------------------------------------
    # CAMERA FRAME
    # ---------------------------------------------------------

    def update_camera(self, camera_index, pixmap):
        if 0 <= camera_index < len(self.camera_panels):
            self.camera_panels[camera_index].set_frame(pixmap)

            self.camera_panels[camera_index].status.setText(
                "● LIVE"
            )