from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget

class AlertsPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main

        layout = QVBoxLayout(self)
        title = QLabel("Alerts")
        title.setStyleSheet("font-size:28px;font-weight:800;")
        layout.addWidget(title)

        self.list = QListWidget()
        layout.addWidget(self.list)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for item in self.main.incidents.items[:50]:
            self.list.addItem(
                f'{item["severity"]} • {item["event"]} • '
                f'{item["camera"]} • {item["time"]}'
            )
