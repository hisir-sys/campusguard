from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QPushButton,
)


class DashboardPage(QWidget):

    def __init__(self, main):
        super().__init__()

        self.main = main
        self.setObjectName("Dashboard")

        self.build_ui()
        self.set_theme(True)
        self.refresh()

    # ========================================================
    # BUILD
    # ========================================================

    def build_ui(self):

        outer = QVBoxLayout(self)

        # IMPORTANT:
        # Bottom is now small because the dock is outside
        # the stacked page and already has its own space.
        outer.setContentsMargins(
            34,
            28,
            34,
            22
        )

        outer.setSpacing(18)

        # ----------------------------------------------------
        # HEADER
        # ----------------------------------------------------

        header = QHBoxLayout()

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        eyebrow = QLabel("CAMPUS OPERATIONS")
        eyebrow.setObjectName("Eyebrow")

        title = QLabel("Campus Overview")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Monitor connected cameras, AI detections, "
            "incidents and notifications from one workspace."
        )

        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        title_box.addWidget(eyebrow)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        header.addLayout(title_box)
        header.addStretch()

        self.system_status = QLabel(
            "●  ALL SYSTEMS OPERATIONAL"
        )

        self.system_status.setObjectName(
            "SystemStatus"
        )

        header.addWidget(
            self.system_status,
            alignment=Qt.AlignTop
        )

        outer.addLayout(header)

        # ----------------------------------------------------
        # WORKSPACE
        # ----------------------------------------------------

        workspace = QHBoxLayout()
        workspace.setSpacing(18)

        # ====================================================
        # LEFT
        # ====================================================

        left = QVBoxLayout()
        left.setSpacing(14)

        self.model_card = self.create_stat_card(
            "AI ENGINE",
            "MC3-18",
            "READY",
            True
        )

        self.incident_card = self.create_stat_card(
            "INCIDENTS",
            "0",
            "DETECTED",
            False
        )

        left.addWidget(self.model_card)
        left.addWidget(self.incident_card)

        # Notifications
        notification_panel = QFrame()
        notification_panel.setObjectName(
            "PremiumPanel"
        )

        notification_layout = QVBoxLayout(
            notification_panel
        )

        notification_layout.setContentsMargins(
            18,
            17,
            18,
            17
        )

        notification_layout.setSpacing(12)

        notification_header = QHBoxLayout()

        notification_title = QLabel(
            "NOTIFICATIONS"
        )

        notification_title.setObjectName(
            "SectionTitle"
        )

        notification_header.addWidget(
            notification_title
        )

        notification_header.addStretch()

        self.notification_count = QLabel("0")
        self.notification_count.setObjectName(
            "NotificationCount"
        )

        notification_header.addWidget(
            self.notification_count
        )

        notification_layout.addLayout(
            notification_header
        )

        self.notification_content = QLabel(
            "No new notifications.\n\n"
            "Security events and important detections "
            "will appear here."
        )

        self.notification_content.setWordWrap(True)
        self.notification_content.setObjectName(
            "NotificationContent"
        )

        notification_layout.addWidget(
            self.notification_content
        )

        notification_layout.addStretch()

        left.addWidget(
            notification_panel,
            1
        )

        workspace.addLayout(left, 1)

        # ====================================================
        # RIGHT — LIVE NETWORK
        # ====================================================

        camera_panel = QFrame()
        camera_panel.setObjectName(
            "CameraPanel"
        )

        # No forced 500px minimum.
        # It now uses the available page height.
        camera_panel.setMinimumHeight(0)

        camera_layout = QVBoxLayout(
            camera_panel
        )

        camera_layout.setContentsMargins(
            18,
            18,
            18,
            18
        )

        camera_layout.setSpacing(13)

        # ----------------------------------------------------
        # Header
        # ----------------------------------------------------

        camera_header = QHBoxLayout()

        camera_title_box = QVBoxLayout()
        camera_title_box.setSpacing(3)

        network_title = QLabel(
            "LIVE NETWORK"
        )

        network_title.setObjectName(
            "NetworkTitle"
        )

        network_subtitle = QLabel(
            "Connected camera monitoring"
        )

        network_subtitle.setObjectName(
            "NetworkSubtitle"
        )

        camera_title_box.addWidget(
            network_title
        )

        camera_title_box.addWidget(
            network_subtitle
        )

        camera_header.addLayout(
            camera_title_box
        )

        camera_header.addStretch()

        camera_count = QLabel(
            "04 CAMERAS"
        )

        camera_count.setObjectName(
            "CameraCount"
        )

        camera_header.addWidget(
            camera_count
        )

        camera_layout.addLayout(
            camera_header
        )

        # ----------------------------------------------------
        # Camera matrix
        # ----------------------------------------------------

        matrix = QGridLayout()

        matrix.setContentsMargins(
            0,
            0,
            0,
            0
        )

        matrix.setHorizontalSpacing(10)
        matrix.setVerticalSpacing(10)

        # Equal stretch means the network stays nicely
        # centered vertically instead of being pushed down.
        matrix.setRowStretch(0, 1)
        matrix.setRowStretch(1, 1)

        matrix.setColumnStretch(0, 1)
        matrix.setColumnStretch(1, 1)

        for row in range(2):

            for col in range(2):

                camera = self.create_camera_tile(
                    row * 2 + col + 1
                )

                matrix.addWidget(
                    camera,
                    row,
                    col
                )

        camera_layout.addLayout(
            matrix,
            1
        )

        workspace.addWidget(
            camera_panel,
            2
        )

        outer.addLayout(
            workspace,
            1
        )

        self.apply_base_styles()

    # ========================================================
    # STAT CARD
    # ========================================================

    def create_stat_card(
        self,
        label,
        value,
        footer,
        ready=False
    ):

        card = QFrame()
        card.setObjectName(
            "StatCard"
        )

        layout = QVBoxLayout(card)

        layout.setContentsMargins(
            18,
            15,
            18,
            15
        )

        layout.setSpacing(7)

        top = QHBoxLayout()

        label_widget = QLabel(label)
        label_widget.setObjectName(
            "StatLabel"
        )

        top.addWidget(label_widget)
        top.addStretch()

        indicator = QLabel("●")

        indicator.setObjectName(
            "ReadyIndicator"
            if ready
            else
            "NeutralIndicator"
        )

        top.addWidget(indicator)

        layout.addLayout(top)

        value_widget = QLabel(value)
        value_widget.setObjectName(
            "StatValue"
        )

        layout.addWidget(value_widget)

        footer_widget = QLabel(footer)
        footer_widget.setObjectName(
            "StatFooter"
        )

        layout.addWidget(
            footer_widget
        )

        if label == "AI ENGINE":
            self.model_value = value_widget

        if label == "INCIDENTS":
            self.incident_value = value_widget

        return card

    # ========================================================
    # CAMERA TILE
    # ========================================================

    def create_camera_tile(
        self,
        number
    ):

        tile = QFrame()
        tile.setObjectName(
            "CameraTile"
        )

        # Don't force a large height.
        # Grid stretching determines the correct height.
        tile.setMinimumHeight(0)

        layout = QVBoxLayout(tile)

        layout.setContentsMargins(
            13,
            12,
            13,
            12
        )

        layout.setSpacing(7)

        top = QHBoxLayout()

        camera_name = QLabel(
            f"CAMERA {number:02d}"
        )

        camera_name.setObjectName(
            "CameraName"
        )

        top.addWidget(
            camera_name
        )

        top.addStretch()

        live = QLabel("● LIVE")
        live.setObjectName(
            "LiveIndicator"
        )

        top.addWidget(live)

        layout.addLayout(top)

        # Feed takes all remaining space.
        feed = QFrame()
        feed.setObjectName(
            "FeedArea"
        )

        feed_layout = QVBoxLayout(
            feed
        )

        feed_status = QLabel(
            "WAITING FOR FEED"
        )

        feed_status.setAlignment(
            Qt.AlignCenter
        )

        feed_status.setObjectName(
            "FeedStatus"
        )

        feed_layout.addWidget(
            feed_status,
            alignment=Qt.AlignCenter
        )

        layout.addWidget(
            feed,
            1
        )

        bottom = QHBoxLayout()

        state = QLabel(
            "MONITORING"
        )

        state.setObjectName(
            "MonitoringLabel"
        )

        bottom.addWidget(state)
        bottom.addStretch()

        expand = QPushButton("↗")

        expand.setObjectName(
            "ExpandButton"
        )

        expand.setFixedSize(
            27,
            27
        )

        expand.setCursor(
            Qt.PointingHandCursor
        )

        expand.setToolTip(
            "Open camera"
        )

        bottom.addWidget(
            expand
        )

        layout.addLayout(
            bottom
        )

        return tile

    # ========================================================
    # REFRESH
    # ========================================================

    def refresh(self):

        try:

            count = len(
                self.main.incidents.items
            )

            self.incident_value.setText(
                str(count)
            )

            self.notification_count.setText(
                str(count)
            )

            if count == 0:

                self.notification_content.setText(
                    "No new notifications.\n\n"
                    "Security events and important "
                    "detections will appear here."
                )

                return

            recent = (
                self.main.incidents.items[-4:]
            )

            lines = []

            for item in reversed(recent):

                camera = item.get(
                    "camera",
                    "Camera"
                )

                event = item.get(
                    "event",
                    "Activity detected"
                )

                severity = item.get(
                    "severity",
                    "INFO"
                )

                lines.append(
                    f"●  {camera}\n"
                    f"   {event}  ·  {severity}"
                )

            self.notification_content.setText(
                "\n\n".join(lines)
            )

        except Exception:

            self.incident_value.setText(
                "0"
            )

            self.notification_count.setText(
                "0"
            )

    # ========================================================
    # BASE STYLES
    # ========================================================

    def apply_base_styles(self):

        self.setStyleSheet("""
            #Dashboard {
                background: transparent;
            }

            #Eyebrow {
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 2px;
            }

            #PageTitle {
                font-size: 30px;
                font-weight: 600;
            }

            #PageSubtitle {
                font-size: 12px;
            }

            #SystemStatus {
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 10px;
                font-weight: 600;
            }

            #StatCard {
                border-radius: 13px;
            }

            #StatLabel {
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1.4px;
            }

            #StatValue {
                font-size: 29px;
                font-weight: 500;
            }

            #StatFooter {
                font-size: 9px;
            }

            #ReadyIndicator,
            #NeutralIndicator {
                font-size: 10px;
            }

            #PremiumPanel {
                border-radius: 13px;
            }

            #SectionTitle {
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1.5px;
            }

            #NotificationCount {
                border-radius: 6px;
                padding: 3px 7px;
                font-size: 9px;
                font-weight: 700;
            }

            #NotificationContent {
                font-size: 11px;
            }

            #CameraPanel {
                border-radius: 14px;
            }

            #NetworkTitle {
                font-size: 14px;
                font-weight: 600;
            }

            #NetworkSubtitle {
                font-size: 10px;
            }

            #CameraCount {
                font-size: 10px;
                font-weight: 700;
            }

            #CameraTile {
                border-radius: 11px;
            }

            #CameraName {
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            #LiveIndicator {
                font-size: 9px;
                font-weight: 700;
            }

            #FeedArea {
                border-radius: 8px;
            }

            #FeedStatus {
                font-size: 9px;
                font-weight: 600;
                letter-spacing: 1px;
            }

            #MonitoringLabel {
                font-size: 8px;
                font-weight: 600;
                letter-spacing: 1px;
            }

            #ExpandButton {
                border-radius: 7px;
                font-size: 14px;
            }
        """)

    # ========================================================
    # THEME
    # ========================================================

    def set_theme(
        self,
        dark=True
    ):

        if dark:

            self.setStyleSheet("""
                #Dashboard {
                    background: transparent;
                }

                #Eyebrow {
                    color: #71807E;
                }

                #PageTitle {
                    color: #EEF2F0;
                }

                #PageSubtitle {
                    color: #7D8987;
                }

                #SystemStatus {
                    color: #8FB3A9;
                    background: #111A18;
                    border: 1px solid #263D38;
                }

                #StatCard,
                #PremiumPanel,
                #CameraPanel {
                    background: #101516;
                    border: 1px solid #202829;
                }

                #StatCard:hover,
                #PremiumPanel:hover,
                #CameraPanel:hover {
                    background: #141A1B;
                    border: 1px solid #35413F;
                }

                #StatLabel,
                #StatFooter,
                #NotificationContent,
                #NetworkSubtitle,
                #MonitoringLabel {
                    color: #71807E;
                }

                #StatValue,
                #NetworkTitle,
                #SectionTitle {
                    color: #E9EEEC;
                }

                #ReadyIndicator,
                #LiveIndicator {
                    color: #86AFA5;
                }

                #NeutralIndicator {
                    color: #697574;
                }

                #NotificationCount {
                    color: #829F98;
                    background: #17201F;
                }

                #CameraTile {
                    background: #101516;
                    border: 1px solid #222A2B;
                }

                #CameraTile:hover {
                    background: #141A1B;
                    border: 1px solid #3A4947;
                }

                #CameraName {
                    color: #DCE4E1;
                }

                #FeedArea {
                    background: #0B0F10;
                    border: 1px solid #1C2324;
                }

                #FeedStatus {
                    color: #4F5B5A;
                }

                #ExpandButton {
                    color: #82908D;
                    background: #151B1C;
                    border: 1px solid #273031;
                }

                #ExpandButton:hover {
                    color: #E9EEEC;
                    background: #202829;
                    border: 1px solid #42504E;
                }
            """)

        else:

            self.setStyleSheet("""
                #Dashboard {
                    background: transparent;
                }

                #Eyebrow {
                    color: #647A75;
                }

                #PageTitle {
                    color: #18201F;
                }

                #PageSubtitle {
                    color: #687572;
                }

                #SystemStatus {
                    color: #496D64;
                    background: #EDF4F1;
                    border: 1px solid #C9DCD5;
                }

                #StatCard,
                #PremiumPanel,
                #CameraPanel {
                    background: #FFFFFF;
                    border: 1px solid #DCE3E0;
                }

                #StatCard:hover,
                #PremiumPanel:hover,
                #CameraPanel:hover {
                    background: #F9FBFA;
                    border: 1px solid #BBCBC6;
                }

                #StatLabel {
                    color: #687572;
                }

                #StatValue {
                    color: #1B2523;
                }

                #StatFooter,
                #NotificationContent,
                #NetworkSubtitle,
                #MonitoringLabel {
                    color: #74807D;
                }

                #SectionTitle,
                #NetworkTitle {
                    color: #1D2825;
                }

                #ReadyIndicator,
                #LiveIndicator {
                    color: #4C776D;
                }

                #NeutralIndicator {
                    color: #899491;
                }

                #NotificationCount {
                    color: #4F7068;
                    background: #EDF4F1;
                }

                #CameraTile {
                    background: #F8FAF9;
                    border: 1px solid #DCE3E0;
                }

                #CameraTile:hover {
                    background: #FFFFFF;
                    border: 1px solid #B8C8C3;
                }

                #CameraName {
                    color: #34413E;
                }

                #FeedArea {
                    background: #EEF2F0;
                    border: 1px solid #D8E0DD;
                }

                #FeedStatus {
                    color: #899491;
                }

                #ExpandButton {
                    color: #5D6A67;
                    background: #EEF2F0;
                    border: 1px solid #D6DEDB;
                }

                #ExpandButton:hover {
                    color: #1C2724;
                    background: #E3EAE7;
                    border: 1px solid #B9C8C3;
                }
            """)

        self.update()