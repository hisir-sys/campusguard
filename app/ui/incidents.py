from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView
)

class IncidentsPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main

        layout = QVBoxLayout(self)
        title = QLabel("Incident Log")
        title.setStyleSheet("font-size:28px;font-weight:800;")
        layout.addWidget(title)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Time", "Camera", "Event", "Confidence", "Severity"
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        layout.addWidget(self.table)

        clear = QPushButton("Clear Incident Log")
        clear.clicked.connect(self.clear)
        layout.addWidget(clear)

        self.refresh()

    def refresh(self):
        items = self.main.incidents.items
        self.table.setRowCount(len(items))

        for row, item in enumerate(items):
            values = [
                item["time"], item["camera"], item["event"],
                f'{item["confidence"]:.1f}%', item["severity"]
            ]
            for column, value in enumerate(values):
                self.table.setItem(
                    row, column, QTableWidgetItem(str(value))
                )

    def clear(self):
        self.main.incidents.clear()
        self.refresh()
