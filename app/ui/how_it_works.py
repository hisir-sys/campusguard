
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
)


class HowItWorksPage(QWidget):
    def __init__(self, main):
        super().__init__()

        self.main = main
        self.setObjectName("howItWorksPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(20)

        # Header
        header = QHBoxLayout()

        title = QLabel("How It Works")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()

        back = QPushButton("←  Dashboard")
        back.setObjectName("backButton")
        back.setCursor(Qt.PointingHandCursor)
        back.clicked.connect(
            lambda: self.main.show_page(self.main.dashboard)
        )
        header.addWidget(back)

        root.addLayout(header)

        intro = QLabel(
            "From camera input to incident review, "
            "everything comes together in one monitoring workflow."
        )
        intro.setObjectName("introText")
        intro.setWordWrap(True)
        root.addWidget(intro)

        # Four workflow cards
        row = QHBoxLayout()
        row.setSpacing(12)

        steps = [
            (
                "01",
                "Connect",
                "Add the camera sources you want to monitor."
            ),
            (
                "02",
                "Process",
                "Video frames enter the camera-processing pipeline."
            ),
            (
                "03",
                "Analyze",
                "The configured AI model analyzes video frames."
            ),
            (
                "04",
                "Review",
                "Review recorded incidents and associated alerts."
            ),
        ]

        self.cards = []

        for number, heading, description in steps:
            card = self._make_card(
                number,
                heading,
                description,
            )
            self.cards.append(card)
            row.addWidget(card, 1)

        root.addLayout(row)

        # Pipeline section
        pipeline = QFrame()
        pipeline.setObjectName("pipelineCard")

        pipeline_layout = QVBoxLayout(pipeline)
        pipeline_layout.setContentsMargins(24, 22, 24, 22)
        pipeline_layout.setSpacing(12)

        pipeline_title = QLabel("Monitoring workflow")
        pipeline_title.setObjectName("sectionTitle")

        pipeline_steps = QHBoxLayout()
        pipeline_steps.setSpacing(8)

        stages = [
            "Camera",
            "Frames",
            "AI analysis",
            "Incident",
            "Alert",
        ]

        for index, stage in enumerate(stages):
            stage_label = QLabel(stage)
            stage_label.setObjectName("pipelineStage")
            stage_label.setAlignment(Qt.AlignCenter)
            pipeline_steps.addWidget(stage_label)

            if index < len(stages) - 1:
                arrow = QLabel("›")
                arrow.setObjectName("pipelineArrow")
                arrow.setAlignment(Qt.AlignCenter)
                pipeline_steps.addWidget(arrow)

        pipeline_layout.addWidget(pipeline_title)
        pipeline_layout.addLayout(pipeline_steps)

        note = QLabel(
            "AI results are indicators for human review, not "
            "proof that an incident has occurred. Actual "
            "detection depends on the configured model and input."
        )
        note.setObjectName("secondaryText")
        note.setWordWrap(True)
        pipeline_layout.addWidget(note)

        root.addWidget(pipeline)
        root.addStretch()

        self.apply_theme(self.main.dark_mode)

    def _make_card(self, number, heading, description):
        card = QFrame()
        card.setObjectName("stepCard")
        card.setMinimumHeight(175)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(19, 19, 19, 19)
        layout.setSpacing(12)

        number_label = QLabel(number)
        number_label.setObjectName("stepNumber")

        heading_label = QLabel(heading)
        heading_label.setObjectName("stepTitle")

        description_label = QLabel(description)
        description_label.setObjectName("stepDescription")
        description_label.setWordWrap(True)

        layout.addWidget(number_label)
        layout.addWidget(heading_label)
        layout.addWidget(description_label)
        layout.addStretch()

        return card

    def apply_theme(self, dark_mode):
        if dark_mode:
            background = "#0B0D0F"
            panel = "#171C1F"
            text = "#E8ECE9"
            muted = "#9AA7A8"
            accent = "#70A9A3"
            border = "#30393B"
            stage = "#20282B"
        else:
            background = "#F1F3F0"
            panel = "#FFFFFF"
            text = "#20292B"
            muted = "#657477"
            accent = "#477E78"
            border = "#D7DFDB"
            stage = "#E6ECE8"

        self.setStyleSheet(f"""
            QWidget#howItWorksPage {{
                background: {background};
                font-family: "Segoe UI";
            }}

            QLabel#pageTitle {{
                color: {text};
                font-size: 27px;
                font-weight: 650;
            }}

            QLabel#introText {{
                color: {muted};
                font-size: 14px;
            }}

            QFrame#stepCard,
            QFrame#pipelineCard {{
                background: {panel};
                border: 1px solid {border};
                border-radius: 17px;
            }}

            QLabel#stepNumber {{
                color: {accent};
                font-size: 12px;
                font-weight: 700;
            }}

            QLabel#stepTitle {{
                color: {text};
                font-size: 17px;
                font-weight: 650;
            }}

            QLabel#stepDescription {{
                color: {muted};
                font-size: 12px;
            }}

            QLabel#sectionTitle {{
                color: {text};
                font-size: 16px;
                font-weight: 650;
            }}

            QLabel#pipelineStage {{
                background: {stage};
                color: {text};
                border: 1px solid {border};
                border-radius: 9px;
                padding: 12px 7px;
                font-size: 12px;
                font-weight: 600;
            }}

            QLabel#pipelineArrow {{
                color: {accent};
                font-size: 23px;
                font-weight: 600;
            }}

            QLabel#secondaryText {{
                color: {muted};
                font-size: 12px;
            }}

            QPushButton#backButton {{
                background: transparent;
                color: {text};
                border: 1px solid {border};
                border-radius: 10px;
                padding: 9px 13px;
                font-size: 12px;
            }}

            QPushButton#backButton:hover {{
                background: {stage};
                border-color: {accent};
            }}
        """)