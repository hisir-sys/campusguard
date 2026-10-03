from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from campusguard.storage import Repository
from campusguard.ui.common import make_page_title


def _local_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d  %H:%M:%S")
    except (TypeError, ValueError):
        return value


def _item(value: object, align: Qt.AlignmentFlag | None = None) -> QTableWidgetItem:
    cell = QTableWidgetItem(str(value))
    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if align is not None:
        cell.setTextAlignment(align)
    return cell


class IncidentsPage(QWidget):
    status_change_requested = Signal(str, str)

    def __init__(self, repository: Repository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)
        root.addWidget(make_page_title(
            "Incident history",
            "SQLite-backed events produced by the loaded action model. Search and filter the local record.",
        ))

        filters = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by ID, camera, or event")
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All statuses", "NEW", "ACKNOWLEDGED", "RESOLVED"])
        self.severity_filter = QComboBox()
        self.severity_filter.addItems(["All severity", "HIGH", "MEDIUM", "LOW"])
        self.count_label = QLabel("0 incidents")
        self.count_label.setProperty("muted", True)
        filters.addWidget(self.search_input, 1)
        filters.addWidget(self.status_filter)
        filters.addWidget(self.severity_filter)
        filters.addWidget(self.count_label)
        root.addLayout(filters)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Camera", "Time", "Event", "Confidence", "Severity", "Status", "Actions"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table, 1)

        self.search_input.textChanged.connect(self.refresh)
        self.status_filter.currentTextChanged.connect(self.refresh)
        self.severity_filter.currentTextChanged.connect(self.refresh)

    def refresh(self) -> None:
        query = self.search_input.text().strip().casefold()
        status = self.status_filter.currentText()
        severity = self.severity_filter.currentText()
        rows = self.repository.list_incidents()
        rows = [
            row for row in rows
            if (status == "All statuses" or row["status"] == status)
            and (severity == "All severity" or row["severity"] == severity)
            and (
                not query
                or query in row["public_id"].casefold()
                or query in row["camera_name"].casefold()
                or query in row["event"].casefold()
            )
        ]
        self.count_label.setText(f"{len(rows)} incident{'s' if len(rows) != 1 else ''}")
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.table.setItem(row_index, 0, _item(row["public_id"]))
            self.table.setItem(row_index, 1, _item(row["camera_name"]))
            self.table.setItem(row_index, 2, _item(_local_time(row["happened_at"])))
            self.table.setItem(row_index, 3, _item(row["event"]))
            self.table.setItem(
                row_index,
                4,
                _item(f"{float(row['confidence']):.1%}", Qt.AlignmentFlag.AlignCenter),
            )
            self.table.setItem(row_index, 5, _item(row["severity"]))
            self.table.setItem(row_index, 6, _item(row["status"]))

            actions = QWidget()
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(2, 1, 2, 1)
            if row["status"] == "NEW":
                acknowledge = QPushButton("Acknowledge")
                acknowledge.clicked.connect(
                    lambda checked=False, public_id=row["public_id"]:
                    self.status_change_requested.emit(public_id, "ACKNOWLEDGED")
                )
                action_layout.addWidget(acknowledge)
            if row["status"] != "RESOLVED":
                resolve = QPushButton("Resolve")
                resolve.clicked.connect(
                    lambda checked=False, public_id=row["public_id"]:
                    self.status_change_requested.emit(public_id, "RESOLVED")
                )
                action_layout.addWidget(resolve)
            if not action_layout.count():
                action_layout.addWidget(QLabel("—"))
            self.table.setCellWidget(row_index, 7, actions)


class AlertsPage(QWidget):
    acknowledge_requested = Signal(int)

    def __init__(self, repository: Repository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)
        root.addWidget(make_page_title(
            "Alerts",
            "Alerts are created from actual model-backed incidents and obey the configured camera cooldown.",
        ))

        self.active_title = QLabel("ACTIVE")
        self.active_title.setProperty("eyebrow", True)
        root.addWidget(self.active_title)
        self.active_table = QTableWidget(0, 7)
        self.active_table.setHorizontalHeaderLabels(
            ["Camera", "Event", "Confidence", "Severity", "Time", "Incident", "Action"]
        )
        self._configure_table(self.active_table)
        root.addWidget(self.active_table, 1)

        self.previous_title = QLabel("PREVIOUS")
        self.previous_title.setProperty("eyebrow", True)
        root.addWidget(self.previous_title)
        self.previous_table = QTableWidget(0, 6)
        self.previous_table.setHorizontalHeaderLabels(
            ["Camera", "Event", "Confidence", "Severity", "Time", "Incident"]
        )
        self._configure_table(self.previous_table)
        root.addWidget(self.previous_table, 1)

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)

    def refresh(self) -> None:
        rows = self.repository.list_alerts()
        active = [row for row in rows if not row["acknowledged"]]
        previous = [row for row in rows if row["acknowledged"]]
        self.active_title.setText(f"ACTIVE  ·  {len(active)}")
        self.previous_title.setText(f"PREVIOUS  ·  {len(previous)}")
        self._fill_active(active)
        self._fill_previous(previous)

    def _fill_active(self, rows: list[dict]) -> None:
        self.active_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.active_table.setItem(row_index, 0, _item(row["camera_name"]))
            self.active_table.setItem(row_index, 1, _item(row["event"]))
            self.active_table.setItem(row_index, 2, _item(f"{float(row['confidence']):.1%}"))
            self.active_table.setItem(row_index, 3, _item(row["severity"]))
            self.active_table.setItem(row_index, 4, _item(_local_time(row["happened_at"])))
            self.active_table.setItem(row_index, 5, _item(row["public_id"]))
            button = QPushButton("Acknowledge")
            button.clicked.connect(
                lambda checked=False, alert_id=int(row["alert_id"]):
                self.acknowledge_requested.emit(alert_id)
            )
            self.active_table.setCellWidget(row_index, 6, button)

    def _fill_previous(self, rows: list[dict]) -> None:
        self.previous_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.previous_table.setItem(row_index, 0, _item(row["camera_name"]))
            self.previous_table.setItem(row_index, 1, _item(row["event"]))
            self.previous_table.setItem(row_index, 2, _item(f"{float(row['confidence']):.1%}"))
            self.previous_table.setItem(row_index, 3, _item(row["severity"]))
            self.previous_table.setItem(row_index, 4, _item(_local_time(row["happened_at"])))
            self.previous_table.setItem(row_index, 5, _item(row["public_id"]))