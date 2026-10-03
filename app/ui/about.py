from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QScrollArea,
)


class AboutPage(QWidget):

    def __init__(self, main=None):
        super().__init__()

        self.main = main
        self.setObjectName("AboutPage")

        self.build_ui()

    # ========================================================
    # UI
    # ========================================================

    def build_ui(self):

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        content = QWidget()

        layout = QVBoxLayout(content)
        layout.setContentsMargins(
            52,
            42,
            52,
            80
        )
        layout.setSpacing(20)

        # ====================================================
        # HEADER
        # ====================================================

        eyebrow = QLabel("ABOUT CAMPUSGUARD")
        eyebrow.setObjectName("AboutEyebrow")

        title = QLabel("Security intelligence,\ndesigned for campus operations.")
        title.setObjectName("AboutTitle")

        subtitle = QLabel(
            "CampusGuard is an AI-assisted campus safety monitoring "
            "platform designed to bring live camera monitoring, automated "
            "detection, incident intelligence and operational alerts into "
            "one focused workspace."
        )

        subtitle.setObjectName("AboutSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # ====================================================
        # INTRO PANEL
        # ====================================================

        intro = self.create_panel(
            "THE PLATFORM",
            "CampusGuard provides a centralized operational view of "
            "connected security cameras and detected events. Instead "
            "of requiring operators to constantly move between separate "
            "monitoring screens, the system brings the most relevant "
            "information into a single interface."
        )

        layout.addWidget(intro)

        # ====================================================
        # CAPABILITIES
        # ====================================================

        capabilities_title = QLabel("CORE CAPABILITIES")
        capabilities_title.setObjectName("SectionHeading")

        layout.addWidget(capabilities_title)

        grid = QHBoxLayout()
        grid.setSpacing(12)

        grid.addWidget(
            self.create_feature(
                "01",
                "Live Camera Monitoring",
                "View connected camera sources from a unified "
                "monitoring workspace."
            )
        )

        grid.addWidget(
            self.create_feature(
                "02",
                "AI-Assisted Detection",
                "Process camera frames through the configured "
                "detection pipeline to identify relevant events."
            )
        )

        grid.addWidget(
            self.create_feature(
                "03",
                "Incident Intelligence",
                "Record detected events with camera, confidence "
                "and severity information for later review."
            )
        )

        layout.addLayout(grid)

        grid2 = QHBoxLayout()
        grid2.setSpacing(12)

        grid2.addWidget(
            self.create_feature(
                "04",
                "Operational Alerts",
                "Surface important security events through a "
                "dedicated alert workspace."
            )
        )

        grid2.addWidget(
            self.create_feature(
                "05",
                "Centralized Control",
                "Move between monitoring, incidents, alerts and "
                "configuration without leaving the application."
            )
        )

        grid2.addWidget(
            self.create_feature(
                "06",
                "Focused Interface",
                "A restrained operations-console design built "
                "around clarity, hierarchy and fast access."
            )
        )

        layout.addLayout(grid2)

        # ====================================================
        # HOW IT WORKS
        # ====================================================

        how_title = QLabel("HOW CAMPUSGUARD OPERATES")
        how_title.setObjectName("SectionHeading")

        layout.addWidget(how_title)

        flow = QFrame()
        flow.setObjectName("FlowPanel")

        flow_layout = QHBoxLayout(flow)
        flow_layout.setContentsMargins(
            22,
            22,
            22,
            22
        )
        flow_layout.setSpacing(15)

        steps = [
            ("01", "CAMERA", "Capture"),
            ("02", "AI ENGINE", "Analyze"),
            ("03", "INCIDENT", "Record"),
            ("04", "ALERT", "Notify"),
        ]

        for index, (number, label, description) in enumerate(steps):

            step = QVBoxLayout()
            step.setSpacing(5)

            number_label = QLabel(number)
            number_label.setObjectName("StepNumber")

            label_widget = QLabel(label)
            label_widget.setObjectName("StepLabel")

            desc = QLabel(description)
            desc.setObjectName("StepDescription")

            step.addWidget(number_label)
            step.addWidget(label_widget)
            step.addWidget(desc)

            flow_layout.addLayout(step)

            if index < len(steps) - 1:

                arrow = QLabel("→")
                arrow.setObjectName("StepArrow")

                flow_layout.addWidget(
                    arrow,
                    alignment=Qt.AlignCenter
                )

        layout.addWidget(flow)

        # ====================================================
        # DESIGN PHILOSOPHY
        # ====================================================

        philosophy = self.create_panel(
            "DESIGNED FOR OPERATORS",
            "CampusGuard is intentionally structured around information "
            "hierarchy rather than visual noise. Camera feeds remain the "
            "primary workspace, while incidents, notifications and system "
            "state remain immediately accessible. The interface is designed "
            "to make important information visible without overwhelming "
            "the operator."
        )

        layout.addWidget(philosophy)

        # ====================================================
        # FOOTER
        # ====================================================

        footer = QLabel(
            "CAMPUSGUARD  ·  AI-ASSISTED CAMPUS SAFETY MONITORING"
        )

        footer.setObjectName("AboutFooter")
        footer.setAlignment(Qt.AlignCenter)

        layout.addSpacing(10)
        layout.addWidget(footer)

        scroll.setWidget(content)

        root.addWidget(scroll)

        self.apply_styles()

    # ========================================================
    # PANEL
    # ========================================================

    def create_panel(self, title, text):

        panel = QFrame()
        panel.setObjectName("AboutPanel")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(
            22,
            20,
            22,
            20
        )
        layout.setSpacing(9)

        heading = QLabel(title)
        heading.setObjectName("PanelHeading")

        body = QLabel(text)
        body.setObjectName("PanelBody")
        body.setWordWrap(True)

        layout.addWidget(heading)
        layout.addWidget(body)

        return panel

    # ========================================================
    # FEATURE CARD
    # ========================================================

    def create_feature(
        self,
        number,
        title,
        description
    ):

        card = QFrame()
        card.setObjectName("FeatureCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            18,
            17,
            18,
            18
        )
        layout.setSpacing(8)

        number_label = QLabel(number)
        number_label.setObjectName("FeatureNumber")

        title_label = QLabel(title)
        title_label.setObjectName("FeatureTitle")

        description_label = QLabel(description)
        description_label.setObjectName("FeatureDescription")
        description_label.setWordWrap(True)

        layout.addWidget(number_label)
        layout.addWidget(title_label)
        layout.addWidget(description_label)

        return card

    # ========================================================
    # STYLES
    # ========================================================

    def apply_styles(self):

        self.setStyleSheet("""
            #AboutPage {
                background: #090B0C;
            }

            QScrollArea {
                background: #090B0C;
                border: none;
            }

            QScrollBar:vertical {
                background: transparent;
                width: 8px;
            }

            QScrollBar::handle:vertical {
                background: #293231;
                border-radius: 4px;
                min-height: 40px;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }

            #AboutEyebrow {
                color: #78918B;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 2px;
            }

            #AboutTitle {
                color: #EEF2F0;
                font-size: 32px;
                font-weight: 600;
                line-height: 1.15;
            }

            #AboutSubtitle {
                color: #7E8A88;
                font-size: 13px;
                line-height: 1.6;
                max-width: 800px;
            }

            #AboutPanel {
                background: #101516;
                border: 1px solid #202829;
                border-radius: 13px;
            }

            #AboutPanel:hover {
                border: 1px solid #34413F;
            }

            #PanelHeading {
                color: #829B95;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1.5px;
            }

            #PanelBody {
                color: #899492;
                font-size: 12px;
                line-height: 1.6;
            }

            #SectionHeading {
                color: #E6ECE9;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1.7px;
                margin-top: 8px;
            }

            #FeatureCard {
                background: #101516;
                border: 1px solid #202829;
                border-radius: 12px;
                min-height: 145px;
            }

            #FeatureCard:hover {
                background: #141A1B;
                border: 1px solid #3A4745;
            }

            #FeatureNumber {
                color: #5D7972;
                font-size: 10px;
                font-weight: 700;
            }

            #FeatureTitle {
                color: #E6ECE9;
                font-size: 13px;
                font-weight: 600;
            }

            #FeatureDescription {
                color: #7C8886;
                font-size: 10px;
                line-height: 1.5;
            }

            #FlowPanel {
                background: #0F1314;
                border: 1px solid #202829;
                border-radius: 13px;
            }

            #StepNumber {
                color: #71918A;
                font-size: 10px;
                font-weight: 700;
            }

            #StepLabel {
                color: #E6ECE9;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            #StepDescription {
                color: #778481;
                font-size: 9px;
            }

            #StepArrow {
                color: #52625F;
                font-size: 18px;
            }

            #AboutFooter {
                color: #4F5C59;
                font-size: 9px;
                font-weight: 600;
                letter-spacing: 1.5px;
            }
        """)

    # ========================================================
    # THEME SUPPORT
    # ========================================================

    def set_theme(self, dark=True):

        if dark:
            self.setStyleSheet("""
                #AboutPage,
                QScrollArea {
                    background: #090B0C;
                }

                #AboutEyebrow {
                    color: #78918B;
                }

                #AboutTitle {
                    color: #EEF2F0;
                }

                #AboutSubtitle,
                #PanelBody,
                #FeatureDescription,
                #StepDescription {
                    color: #7E8A88;
                }

                #AboutPanel,
                #FeatureCard,
                #FlowPanel {
                    background: #101516;
                    border: 1px solid #202829;
                }

                #AboutPanel:hover,
                #FeatureCard:hover {
                    background: #141A1B;
                    border: 1px solid #34413F;
                }

                #PanelHeading,
                #FeatureNumber,
                #StepNumber {
                    color: #78918B;
                }

                #SectionHeading,
                #FeatureTitle,
                #StepLabel {
                    color: #E6ECE9;
                }

                #AboutFooter {
                    color: #4F5C59;
                }
            """)

        else:
            self.setStyleSheet("""
                #AboutPage,
                QScrollArea {
                    background: #F4F6F4;
                }

                #AboutEyebrow {
                    color: #59766E;
                }

                #AboutTitle {
                    color: #18201F;
                }

                #AboutSubtitle,
                #PanelBody,
                #FeatureDescription,
                #StepDescription {
                    color: #687572;
                }

                #AboutPanel,
                #FeatureCard,
                #FlowPanel {
                    background: #FFFFFF;
                    border: 1px solid #DCE3E0;
                }

                #AboutPanel:hover,
                #FeatureCard:hover {
                    background: #F9FBFA;
                    border: 1px solid #B8C8C3;
                }

                #PanelHeading,
                #FeatureNumber,
                #StepNumber {
                    color: #58776E;
                }

                #SectionHeading,
                #FeatureTitle,
                #StepLabel {
                    color: #1D2825;
                }

                #StepArrow {
                    color: #8A9995;
                }

                #AboutFooter {
                    color: #7A8783;
                }
            """)