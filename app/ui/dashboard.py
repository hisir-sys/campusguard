from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame

class DashboardPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        layout = QVBoxLayout(self)

        title = QLabel("CampusGuard")
        title.setStyleSheet("font-size:30px;font-weight:800;")
        layout.addWidget(title)
        layout.addWidget(QLabel("AI-assisted campus safety monitoring"))

        row = QHBoxLayout()
        self.incident_value = QLabel(str(len(main.incidents.items)))
        row.addWidget(self.card("MONITORING NETWORK", "0 / 4", "active camera feeds"))
        row.addWidget(self.card("MODEL", main.detector.status, "inference engine"))
        row.addWidget(self.card_widget("INCIDENTS", self.incident_value, "logged events"))
        layout.addLayout(row)
        layout.addStretch()

    def card_widget(self, title, value_widget, subtitle):
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:#081018;border:1px solid #182a39;border-radius:14px;}"
        )
        box = QVBoxLayout(frame)
        box.addWidget(QLabel(title))
        value_widget.setStyleSheet("font-size:28px;font-weight:800;")
        box.addWidget(value_widget)
        box.addWidget(QLabel(subtitle))
        return frame

    def card(self, title, value, subtitle):
        return self.card_widget(title, QLabel(value), subtitle)

    def refresh(self):
        self.incident_value.setText(str(len(self.main.incidents.items)))
