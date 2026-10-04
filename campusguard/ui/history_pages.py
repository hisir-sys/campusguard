from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
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
        return datetime.fromisoformat(value).astimezone().strftime(
            "%Y-%m-%d  %H:%M:%S"
        )
    except (TypeError, ValueError):
        return value


def _item(
    value: object,
    align: Qt.AlignmentFlag | None = None,
) -> QTableWidgetItem:
    cell = QTableWidgetItem(str(value))
    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)

    if align is not None:
        cell.setTextAlignment(align)

    return cell


def _metric_card(title: str, value: str) -> QFrame:
    frame = QFrame()
    frame.setProperty("card", True)

    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(5)

    title_label = QLabel(title)
    title_label.setProperty("muted", True)
    title_label.setStyleSheet(
        "font-size: 9px; font-weight: 800; letter-spacing: 0.8px;"
    )

    value_label = QLabel(value)
    value_label.setStyleSheet("font-size: 18px; font-weight: 800;")

    layout.addWidget(title_label)
    layout.addWidget(value_label)

    frame.value_label = value_label  # type: ignore[attr-defined]
    return frame


class IncidentsPage(QWidget):
    status_change_requested = Signal(str, str)

    def __init__(
        self,
        repository: Repository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.repository = repository

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(13)

        header = QHBoxLayout()
        header.addWidget(
            make_page_title(
                "Incident history",
                "Review model-backed events stored in the local incident database. "
                "Search, filter, acknowledge, and resolve incidents from one workspace.",
            ),
            1,
        )

        self.total_badge = QLabel("0 INCIDENTS")
        self.total_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.total_badge.setMinimumHeight(30)
        self.total_badge.setStyleSheet(
            """
            QLabel {
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 15px;
                padding: 0 12px;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.8px;
            }
            """
        )
        header.addWidget(self.total_badge, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        # Overview
        overview = QHBoxLayout()
        overview.setSpacing(10)

        self.total_card = _metric_card("TOTAL", "0")
        self.new_card = _metric_card("NEW", "0")
        self.ack_card = _metric_card("ACKNOWLEDGED", "0")
        self.resolved_card = _metric_card("RESOLVED", "0")

        for card in (
            self.total_card,
            self.new_card,
            self.ack_card,
            self.resolved_card,
        ):
            overview.addWidget(card, 1)

        root.addLayout(overview)

        # Filters
        filter_frame = QFrame()
        filter_frame.setProperty("card", True)

        filters = QHBoxLayout(filter_frame)
        filters.setContentsMargins(12, 10, 12, 10)
        filters.setSpacing(9)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search incident ID, camera, or event..."
        )

        self.status_filter = QComboBox()
        self.status_filter.addItems(
            ["All statuses", "NEW", "ACKNOWLEDGED", "RESOLVED"]
        )

        self.severity_filter = QComboBox()
        self.severity_filter.addItems(
            ["All severity", "HIGH", "MEDIUM", "LOW"]
        )

        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self._clear_filters)

        filters.addWidget(self.search_input, 1)
        filters.addWidget(self.status_filter)
        filters.addWidget(self.severity_filter)
        filters.addWidget(clear_button)

        root.addWidget(filter_frame)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "Camera",
                "Time",
                "Event",
                "Confidence",
                "Severity",
                "Status",
                "Actions",
            ]
        )
        self._configure_table(self.table)

        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)

        root.addWidget(self.table, 1)

        self.search_input.textChanged.connect(self.refresh)
        self.status_filter.currentTextChanged.connect(self.refresh)
        self.severity_filter.currentTextChanged.connect(self.refresh)

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(46)
        table.horizontalHeader().setStretchLastSection(False)

    def _clear_filters(self) -> None:
        self.search_input.clear()
        self.status_filter.setCurrentIndex(0)
        self.severity_filter.setCurrentIndex(0)

    def refresh(self) -> None:
        query = self.search_input.text().strip().casefold()
        status = self.status_filter.currentText()
        severity = self.severity_filter.currentText()

        rows = self.repository.list_incidents()

        rows = [
            row
            for row in rows
            if (status == "All statuses" or row["status"] == status)
            and (severity == "All severity" or row["severity"] == severity)
            and (
                not query
                or query in row["public_id"].casefold()
                or query in row["camera_name"].casefold()
                or query in row["event"].casefold()
            )
        ]

        all_rows = self.repository.list_incidents()
        total = len(all_rows)
        new_count = sum(1 for row in all_rows if row["status"] == "NEW")
        ack_count = sum(
            1 for row in all_rows if row["status"] == "ACKNOWLEDGED"
        )
        resolved_count = sum(
            1 for row in all_rows if row["status"] == "RESOLVED"
        )

        self.total_card.value_label.setText(str(total))
        self.new_card.value_label.setText(str(new_count))
        self.ack_card.value_label.setText(str(ack_count))
        self.resolved_card.value_label.setText(str(resolved_count))

        self.total_badge.setText(
            f"{len(rows)} INCIDENT{'S' if len(rows) != 1 else ''}"
        )

        self.table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            self.table.setItem(
                row_index,
                0,
                _item(row["public_id"]),
            )
            self.table.setItem(
                row_index,
                1,
                _item(row["camera_name"]),
            )
            self.table.setItem(
                row_index,
                2,
                _item(_local_time(row["happened_at"])),
            )
            self.table.setItem(
                row_index,
                3,
                _item(row["event"]),
            )
            self.table.setItem(
                row_index,
                4,
                _item(
                    f"{float(row['confidence']):.1%}",
                    Qt.AlignmentFlag.AlignCenter,
                ),
            )
            self.table.setItem(
                row_index,
                5,
                _item(row["severity"]),
            )
            self.table.setItem(
                row_index,
                6,
                _item(row["status"]),
            )

            actions = QWidget()
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(4, 3, 4, 3)
            action_layout.setSpacing(5)

            if row["status"] == "NEW":
                acknowledge = QPushButton("Acknowledge")
                acknowledge.clicked.connect(
                    lambda checked=False, public_id=row["public_id"]:
                    self.status_change_requested.emit(
                        public_id,
                        "ACKNOWLEDGED",
                    )
                )
                action_layout.addWidget(acknowledge)

            if row["status"] != "RESOLVED":
                resolve = QPushButton("Resolve")
                resolve.clicked.connect(
                    lambda checked=False, public_id=row["public_id"]:
                    self.status_change_requested.emit(
                        public_id,
                        "RESOLVED",
                    )
                )
                action_layout.addWidget(resolve)

            if not action_layout.count():
                done = QLabel("Resolved")
                done.setProperty("muted", True)
                done.setAlignment(Qt.AlignmentFlag.AlignCenter)
                action_layout.addWidget(done)

            self.table.setCellWidget(row_index, 7, actions)


class AlertsPage(QWidget):
    acknowledge_requested = Signal(int)

    def __init__(
        self,
        repository: Repository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.repository = repository

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(13)

        header = QHBoxLayout()
        header.addWidget(
            make_page_title(
                "Alerts",
                "Monitor active alerts generated from model-backed incidents and review previously acknowledged events.",
            ),
            1,
        )

        self.alert_badge = QLabel("0 ACTIVE")
        self.alert_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.alert_badge.setMinimumHeight(30)
        self.alert_badge.setStyleSheet(
            """
            QLabel {
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 15px;
                padding: 0 12px;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.8px;
            }
            """
        )
        header.addWidget(self.alert_badge, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        overview = QHBoxLayout()
        overview.setSpacing(10)

        self.active_card = _metric_card("ACTIVE", "0")
        self.previous_card = _metric_card("PREVIOUS", "0")
        self.high_card = _metric_card("HIGH SEVERITY", "0")
        self.medium_card = _metric_card("MEDIUM / LOW", "0")

        for card in (
            self.active_card,
            self.previous_card,
            self.high_card,
            self.medium_card,
        ):
            overview.addWidget(card, 1)

        root.addLayout(overview)

        active_frame = QFrame()
        active_frame.setProperty("card", True)
        active_layout = QVBoxLayout(active_frame)
        active_layout.setContentsMargins(12, 11, 12, 11)
        active_layout.setSpacing(8)

        self.active_title = QLabel("ACTIVE  ·  0")
        self.active_title.setProperty("eyebrow", True)
        active_layout.addWidget(self.active_title)

        self.active_table = QTableWidget(0, 7)
        self.active_table.setHorizontalHeaderLabels(
            [
                "Camera",
                "Event",
                "Confidence",
                "Severity",
                "Time",
                "Incident",
                "Action",
            ]
        )
        self._configure_table(self.active_table)
        active_header = self.active_table.horizontalHeader()
        active_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        active_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        active_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        active_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        active_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        active_header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        active_header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

        active_layout.addWidget(self.active_table, 1)
        root.addWidget(active_frame, 1)

        previous_frame = QFrame()
        previous_frame.setProperty("card", True)
        previous_layout = QVBoxLayout(previous_frame)
        previous_layout.setContentsMargins(12, 11, 12, 11)
        previous_layout.setSpacing(8)

        self.previous_title = QLabel("PREVIOUS  ·  0")
        self.previous_title.setProperty("eyebrow", True)
        previous_layout.addWidget(self.previous_title)

        self.previous_table = QTableWidget(0, 6)
        self.previous_table.setHorizontalHeaderLabels(
            [
                "Camera",
                "Event",
                "Confidence",
                "Severity",
                "Time",
                "Incident",
            ]
        )
        self._configure_table(self.previous_table)
        previous_header = self.previous_table.horizontalHeader()
        previous_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        previous_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        previous_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        previous_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        previous_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        previous_header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        previous_layout.addWidget(self.previous_table, 1)
        root.addWidget(previous_frame, 1)

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(44)
        table.horizontalHeader().setStretchLastSection(False)

    def refresh(self) -> None:
        rows = self.repository.list_alerts()

        active = [row for row in rows if not row["acknowledged"]]
        previous = [row for row in rows if row["acknowledged"]]

        high_count = sum(1 for row in active if row["severity"] == "HIGH")
        medium_low_count = len(active) - high_count

        self.active_card.value_label.setText(str(len(active)))
        self.previous_card.value_label.setText(str(len(previous)))
        self.high_card.value_label.setText(str(high_count))
        self.medium_card.value_label.setText(str(medium_low_count))

        self.alert_badge.setText(
            f"{len(active)} ACTIVE"
        )
        self.active_title.setText(f"ACTIVE  ·  {len(active)}")
        self.previous_title.setText(f"PREVIOUS  ·  {len(previous)}")

        self._fill_active(active)
        self._fill_previous(previous)

    def _fill_active(self, rows: list[dict]) -> None:
        self.active_table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            self.active_table.setItem(
                row_index,
                0,
                _item(row["camera_name"]),
            )
            self.active_table.setItem(
                row_index,
                1,
                _item(row["event"]),
            )
            self.active_table.setItem(
                row_index,
                2,
                _item(
                    f"{float(row['confidence']):.1%}",
                    Qt.AlignmentFlag.AlignCenter,
                ),
            )
            self.active_table.setItem(
                row_index,
                3,
                _item(row["severity"]),
            )
            self.active_table.setItem(
                row_index,
                4,
                _item(_local_time(row["happened_at"])),
            )
            self.active_table.setItem(
                row_index,
                5,
                _item(row["public_id"]),
            )

            button = QPushButton("Acknowledge")
            button.clicked.connect(
                lambda checked=False, alert_id=int(row["alert_id"]):
                self.acknowledge_requested.emit(alert_id)
            )

            actions = QWidget()
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(3, 2, 3, 2)
            action_layout.addWidget(button)

            self.active_table.setCellWidget(
                row_index,
                6,
                actions,
            )

    def _fill_previous(self, rows: list[dict]) -> None:
        self.previous_table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            self.previous_table.setItem(
                row_index,
                0,
                _item(row["camera_name"]),
            )
            self.previous_table.setItem(
                row_index,
                1,
                _item(row["event"]),
            )
            self.previous_table.setItem(
                row_index,
                2,
                _item(
                    f"{float(row['confidence']):.1%}",
                    Qt.AlignmentFlag.AlignCenter,
                ),
            )
            self.previous_table.setItem(
                row_index,
                3,
                _item(row["severity"]),
            )
            self.previous_table.setItem(
                row_index,
                4,
                _item(_local_time(row["happened_at"])),
            )
            self.previous_table.setItem(
                row_index,
                5,
                _item(row["public_id"]),
            )
