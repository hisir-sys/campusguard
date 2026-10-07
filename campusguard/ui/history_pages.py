from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsBlurEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from campusguard.storage import Repository
from campusguard.ui.common import make_page_title


# ============================================================================
# HELPERS
# ============================================================================
# ============================================================================
# FOOTAGE PLAYER
# ============================================================================

class FootagePlayerDialog(QWidget):
    def __init__(self, footage_path: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("footageViewerOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "QWidget#footageViewerOverlay { background: rgba(0, 0, 0, 135); }"
        )
        self.setGeometry(parent.rect() if parent is not None else self.rect())
        self.setMinimumSize(760, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(10)

        self.video = QVideoWidget()
        self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        layout.addWidget(self.video, 1)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        speed_label = QLabel("Playback")
        speed_label.setProperty("muted", True)
        controls.addWidget(speed_label)

        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5×", "0.75×", "1×"])
        self.speed_combo.setCurrentIndex(1)
        self.speed_combo.setMinimumWidth(86)
        self.speed_combo.currentIndexChanged.connect(self._set_playback_speed)
        controls.addWidget(self.speed_combo)

        controls.addStretch(1)

        close_button = QPushButton("Close")
        close_button.setProperty("secondaryButton", True)
        close_button.clicked.connect(self.close)
        controls.addWidget(close_button)
        layout.addLayout(controls)

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.7)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)

        path = Path(footage_path)
        if not path.is_file():
            message = QLabel("The saved footage file is no longer available.")
            message.setProperty("muted", True)
            message.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.insertWidget(0, message)
            self.video.hide()
            return

        self.player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        self.player.setPlaybackRate(0.75)

    def _set_playback_speed(self, index: int) -> None:
        rates = [0.5, 0.75, 1.0]
        if 0 <= index < len(rates):
            self.player.setPlaybackRate(rates[index])

    def closeEvent(self, event) -> None:
        self.player.stop()
        super().closeEvent(event)



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
    item = QTableWidgetItem(str(value))

    item.setFlags(
        item.flags() & ~Qt.ItemFlag.ItemIsEditable
    )

    if align is not None:
        item.setTextAlignment(align)

    return item


def _metric_card(
    title: str,
    value: str,
) -> QFrame:
    frame = QFrame()
    frame.setProperty("card", True)
    frame.setProperty("minimalCard", True)

    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 13, 16, 13)
    layout.setSpacing(3)

    title_label = QLabel(title)
    title_label.setProperty("muted", True)

    title_label.setStyleSheet(
        """
        QLabel {
            font-size: 9px;
            font-weight: 800;
            letter-spacing: 0.8px;
        }
        """
    )

    value_label = QLabel(value)

    value_label.setStyleSheet(
        """
        QLabel {
            font-size: 21px;
            font-weight: 800;
        }
        """
    )

    layout.addWidget(title_label)
    layout.addWidget(value_label)

    frame.value_label = value_label  # type: ignore[attr-defined]

    return frame


def _pill(
    text: str,
    property_name: str,
) -> QLabel:
    label = QLabel(text)

    label.setProperty(
        property_name,
        True,
    )

    label.setAlignment(
        Qt.AlignmentFlag.AlignCenter
    )

    label.setMinimumHeight(24)
    label.setMinimumWidth(68)

    return label


def _severity_widget(
    severity: str,
) -> QLabel:
    value = str(severity).upper()

    label = _pill(
        value,
        "severityPill",
    )

    if value == "HIGH":
        label.setProperty("severity", "high")
    elif value == "MEDIUM":
        label.setProperty("severity", "medium")
    else:
        label.setProperty("severity", "low")

    label.style().unpolish(label)
    label.style().polish(label)

    return label


def _status_widget(
    status: str,
) -> QLabel:
    value = str(status).upper()

    label = _pill(
        value,
        "statusPill",
    )

    if value == "NEW":
        label.setProperty("status", "new")
    elif value == "ACKNOWLEDGED":
        label.setProperty("status", "acknowledged")
    elif value == "RESOLVED":
        label.setProperty("status", "resolved")

    label.style().unpolish(label)
    label.style().polish(label)

    return label


def _section_header(
    title: str,
    subtitle: str,
) -> QWidget:
    widget = QWidget()

    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)

    title_label = QLabel(title)

    title_label.setStyleSheet(
        """
        QLabel {
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.4px;
        }
        """
    )

    subtitle_label = QLabel(subtitle)
    subtitle_label.setProperty("muted", True)

    subtitle_label.setStyleSheet(
        """
        QLabel {
            font-size: 10px;
        }
        """
    )

    layout.addWidget(title_label)
    layout.addWidget(subtitle_label)

    return widget


def _empty_state(
    title: str,
    description: str,
) -> QWidget:
    widget = QWidget()

    layout = QVBoxLayout(widget)
    layout.setContentsMargins(
        24,
        28,
        24,
        28,
    )

    layout.setSpacing(5)
    layout.setAlignment(
        Qt.AlignmentFlag.AlignCenter
    )

    mark = QLabel("—")
    mark.setProperty("muted", True)
    mark.setAlignment(
        Qt.AlignmentFlag.AlignCenter
    )

    mark.setStyleSheet(
        """
        QLabel {
            font-size: 22px;
            font-weight: 600;
        }
        """
    )

    title_label = QLabel(title)

    title_label.setAlignment(
        Qt.AlignmentFlag.AlignCenter
    )

    title_label.setStyleSheet(
        """
        QLabel {
            font-size: 13px;
            font-weight: 750;
        }
        """
    )

    description_label = QLabel(
        description
    )

    description_label.setProperty(
        "muted",
        True,
    )

    description_label.setAlignment(
        Qt.AlignmentFlag.AlignCenter
    )

    description_label.setWordWrap(True)

    layout.addWidget(mark)
    layout.addWidget(title_label)
    layout.addWidget(description_label)

    return widget


def _action_button(
    text: str,
    action: str,
) -> QPushButton:
    button = QPushButton(text)

    button.setProperty(
        "minimalAction",
        True,
    )

    button.setProperty(
        "action",
        action,
    )

    button.setCursor(
        Qt.CursorShape.PointingHandCursor
    )

    button.setMinimumHeight(29)

    return button


def _configure_table(
    table: QTableWidget,
) -> None:
    """Configure the history tables as compact, theme-aware data grids."""

    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setEditTriggers(
        QTableWidget.EditTrigger.NoEditTriggers
    )
    table.setSelectionBehavior(
        QTableWidget.SelectionBehavior.SelectRows
    )
    table.setSelectionMode(
        QTableWidget.SelectionMode.SingleSelection
    )
    table.setFocusPolicy(
        Qt.FocusPolicy.NoFocus
    )

    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(58)

    header = table.horizontalHeader()
    header.show()
    header.setDefaultAlignment(
        Qt.AlignmentFlag.AlignLeft
        | Qt.AlignmentFlag.AlignVCenter
    )
    header.setMinimumHeight(34)
    header.setFixedHeight(34)
    header.setStretchLastSection(False)

    table.setWordWrap(False)
    table.setTextElideMode(Qt.TextElideMode.ElideRight)


def _apply_table_palette(table: QTableWidget) -> None:
    """Keep table colors owned by the active application theme."""
    table.style().unpolish(table)
    table.style().polish(table)


# ============================================================================
# GENERIC POPUP
# ============================================================================

class _HistoryPopup(QWidget):
    """
    In-app glass popup.

    The underlying page is blurred and dimmed while this popup is visible.
    """

    closed = Signal()

    def __init__(
        self,
        parent: QWidget,
        title: str,
        subtitle: str,
    ) -> None:
        super().__init__(parent)

        self.setObjectName(
            "historyPopupOverlay"
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.setStyleSheet(
            """
            QWidget#historyPopupOverlay {
                background: rgba(0, 0, 0, 105);
            }
            """
        )

        self.popup = QFrame(self)

        self.popup.setObjectName(
            "historyPopup"
        )
        self.popup.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.popup.setMinimumSize(920, 560)

        self.popup.setProperty(
            "card",
            True,
        )

        self.popup.setStyleSheet(
            """
            QFrame#historyPopup {
                border-radius: 18px;
            }
            """
        )

        outer = QVBoxLayout(self)

        outer.setContentsMargins(
            20,
            20,
            20,
            20,
        )

        outer.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        outer.addWidget(
            self.popup
        )

        popup_layout = QVBoxLayout(
            self.popup
        )

        popup_layout.setContentsMargins(
            22,
            20,
            22,
            18,
        )

        popup_layout.setSpacing(12)

        # --------------------------------------------------------------
        # Popup heading
        # --------------------------------------------------------------

        heading = QHBoxLayout()

        heading.setSpacing(12)

        title_block = QVBoxLayout()
        title_block.setSpacing(3)

        title_label = QLabel(title)

        title_label.setStyleSheet(
            """
            QLabel {
                font-size: 18px;
                font-weight: 850;
            }
            """
        )

        subtitle_label = QLabel(
            subtitle
        )

        subtitle_label.setProperty(
            "muted",
            True,
        )

        subtitle_label.setWordWrap(True)

        title_block.addWidget(
            title_label
        )

        title_block.addWidget(
            subtitle_label
        )

        heading.addLayout(
            title_block,
            1,
        )

        close_button = QPushButton("Close")

        close_button.setProperty(
            "secondaryButton",
            True,
        )

        close_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        close_button.setMinimumHeight(
            32
        )

        close_button.clicked.connect(
            self.close_popup
        )

        heading.addWidget(
            close_button,
            0,
            Qt.AlignmentFlag.AlignTop,
        )

        popup_layout.addLayout(
            heading
        )

        # --------------------------------------------------------------
        # Content container
        # --------------------------------------------------------------

        self.content = QWidget()

        content_layout = QVBoxLayout(
            self.content
        )

        content_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        content_layout.setSpacing(8)

        self.scroll = QScrollArea()

        self.scroll.setWidgetResizable(
            True
        )

        self.scroll.setFrameShape(
            QFrame.Shape.NoFrame
        )

        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.scroll.setWidget(
            self.content
        )

        popup_layout.addWidget(
            self.scroll,
            1,
        )

        self.setVisible(False)

    def set_content(
        self,
        widget: QWidget,
    ) -> None:
        while self.content.layout().count():
            item = (
                self.content.layout()
                .takeAt(0)
            )

            child = item.widget()

            if child is not None:
                child.deleteLater()

        self.content.layout().addWidget(
            widget
        )

    def show_popup(self) -> None:
        parent_rect = self.parentWidget().rect()
        width = min(1320, max(920, int(parent_rect.width() * 0.88)))
        height = min(760, max(560, int(parent_rect.height() * 0.78)))
        self.setGeometry(parent_rect)
        self.popup.setFixedSize(width, height)

        self.show()
        self.raise_()
        self.popup.raise_()

    def close_popup(self) -> None:
        self.hide()
        self.closed.emit()


# ============================================================================
# INCIDENTS PAGE
# ============================================================================

class IncidentsPage(QWidget):
    status_change_requested = Signal(str, str)
    clear_all_requested = Signal()
    clear_footage_requested = Signal()

    def __init__(
        self,
        repository: Repository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.repository = repository

        self._blur_effect: QGraphicsBlurEffect | None = None
        self._popup: _HistoryPopup | None = None
        self._live_open_handler = None
        self._history_open_handler = None

        # ------------------------------------------------------------------
        # Root
        # ------------------------------------------------------------------

        root = QVBoxLayout(self)

        root.setContentsMargins(
            20,
            16,
            20,
            16,
        )

        root.setSpacing(14)

        # ------------------------------------------------------------------
        # Main content wrapper
        # ------------------------------------------------------------------

        self.main_content = QWidget()

        content_layout = QVBoxLayout(
            self.main_content
        )

        content_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        content_layout.setSpacing(14)

        root.addWidget(
            self.main_content,
            1,
        )

        # ------------------------------------------------------------------
        # Header
        # ------------------------------------------------------------------

        header = QHBoxLayout()

        header.addWidget(
            make_page_title(
                "Incident history",
                "Review security events detected across the CampusGuard network.",
            ),
            1,
        )

        self.total_badge = QLabel(
            "0 INCIDENTS"
        )

        self.total_badge.setProperty(
            "statusBadge",
            True,
        )

        self.total_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.total_badge.setMinimumHeight(
            28
        )

        self.clear_footage_button = QPushButton("Clear Footage")
        self.clear_footage_button.setProperty("secondaryButton", True)
        self.clear_footage_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_footage_button.setMinimumHeight(30)
        self.clear_footage_button.clicked.connect(self.clear_footage_requested.emit)

        self.clear_all_button = QPushButton("Clear All")
        self.clear_all_button.setProperty("secondaryButton", True)
        self.clear_all_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_all_button.setMinimumHeight(30)
        self.clear_all_button.clicked.connect(self.clear_all_requested.emit)

        header.addWidget(self.clear_footage_button, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(self.clear_all_button, 0, Qt.AlignmentFlag.AlignTop)

        header.addWidget(
            self.total_badge,
            0,
            Qt.AlignmentFlag.AlignTop,
        )

        content_layout.addLayout(
            header
        )

        # ------------------------------------------------------------------
        # Metrics
        # ------------------------------------------------------------------

        metrics = QHBoxLayout()
        metrics.setSpacing(9)

        self.total_card = _metric_card(
            "TOTAL",
            "0",
        )

        self.new_card = _metric_card(
            "NEW",
            "0",
        )

        self.ack_card = _metric_card(
            "ACKNOWLEDGED",
            "0",
        )

        self.resolved_card = _metric_card(
            "RESOLVED",
            "0",
        )

        for card in (
            self.total_card,
            self.new_card,
            self.ack_card,
            self.resolved_card,
        ):
            metrics.addWidget(
                card,
                1,
            )

        content_layout.addLayout(
            metrics
        )

        # ------------------------------------------------------------------
        # Search
        # ------------------------------------------------------------------

        filter_frame = QFrame()

        filter_frame.setProperty(
            "card",
            True,
        )

        filters = QHBoxLayout(
            filter_frame
        )

        filters.setContentsMargins(
            10,
            9,
            10,
            9,
        )

        filters.setSpacing(8)

        self.search_input = QLineEdit()

        self.search_input.setPlaceholderText(
            "Search incidents..."
        )

        self.search_input.setMinimumHeight(
            34
        )

        self.status_filter = QComboBox()

        self.status_filter.addItems(
            [
                "All statuses",
                "NEW",
                "ACKNOWLEDGED",
                "RESOLVED",
            ]
        )

        self.status_filter.setMinimumHeight(
            34
        )

        self.severity_filter = QComboBox()

        self.severity_filter.addItems(
            [
                "All severity",
                "HIGH",
                "MEDIUM",
                "LOW",
            ]
        )

        self.severity_filter.setMinimumHeight(
            34
        )

        clear_button = QPushButton(
            "Clear"
        )

        clear_button.setProperty(
            "secondaryButton",
            True,
        )

        clear_button.clicked.connect(
            self._clear_filters
        )

        filters.addWidget(
            self.search_input,
            1,
        )

        filters.addWidget(
            self.status_filter
        )

        filters.addWidget(
            self.severity_filter
        )

        filters.addWidget(
            clear_button
        )

        content_layout.addWidget(
            filter_frame
        )

        # ------------------------------------------------------------------
        # Split incident workspace
        # ------------------------------------------------------------------

        workspace = QHBoxLayout()
        workspace.setSpacing(12)

        # Left: live/new incidents
        self.live_card = self._create_incident_preview(
            "CURRENT INCIDENTS",
            "Open incidents awaiting operator confirmation",
            "Open incident list",
        )

        # Right: history
        self.history_card = self._create_incident_preview(
            "RESOLVED HISTORY",
            "Incidents completed with the OK action",
            "Open incident history",
        )

        workspace.addWidget(
            self.live_card,
            1,
        )

        workspace.addWidget(
            self.history_card,
            1,
        )

        content_layout.addLayout(
            workspace,
            1,
        )

        # ------------------------------------------------------------------
        # Signals
        # ------------------------------------------------------------------

        self.search_input.textChanged.connect(
            self.refresh
        )

        self.status_filter.currentTextChanged.connect(
            self.refresh
        )

        self.severity_filter.currentTextChanged.connect(
            self.refresh
        )

    # ----------------------------------------------------------------------
    # Preview cards
    # ----------------------------------------------------------------------

    def _create_incident_preview(
        self,
        title: str,
        subtitle: str,
        button_text: str,
    ) -> QFrame:
        frame = QFrame()

        frame.setProperty(
            "card",
            True,
        )

        layout = QVBoxLayout(
            frame
        )

        layout.setContentsMargins(
            17,
            16,
            17,
            16,
        )

        layout.setSpacing(10)

        header = _section_header(
            title,
            subtitle,
        )

        layout.addWidget(
            header
        )

        preview = QLabel(
            "No incidents"
        )

        preview.setProperty(
            "muted",
            True,
        )

        preview.setWordWrap(True)

        preview.setMinimumHeight(
            90
        )

        layout.addWidget(
            preview,
            1,
        )

        button = QPushButton(
            button_text
        )

        button.setProperty(
            "secondaryButton",
            True,
        )

        button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        layout.addWidget(
            button
        )

        frame.preview_label = preview  # type: ignore[attr-defined]
        frame.open_button = button  # type: ignore[attr-defined]

        return frame

    # ----------------------------------------------------------------------
    # Filters
    # ----------------------------------------------------------------------

    def _clear_filters(self) -> None:
        self.search_input.clear()
        self.status_filter.setCurrentIndex(0)
        self.severity_filter.setCurrentIndex(0)

    # ----------------------------------------------------------------------
    # Refresh
    # ----------------------------------------------------------------------

    def refresh(self) -> None:
        query = (
            self.search_input
            .text()
            .strip()
            .casefold()
        )

        status = self.status_filter.currentText()
        severity = self.severity_filter.currentText()

        all_rows = (
            self.repository
            .list_incidents()
        )

        rows = [
            row
            for row in all_rows
            if (
                status == "All statuses"
                or row["status"] == status
            )
            and (
                severity == "All severity"
                or row["severity"] == severity
            )
            and (
                not query
                or query in row["public_id"].casefold()
                or query in row["camera_name"].casefold()
                or query in row["event"].casefold()
            )
        ]

        # Metrics
        self.total_card.value_label.setText(
            str(len(all_rows))
        )

        self.new_card.value_label.setText(
            str(
                sum(
                    1
                    for row in all_rows
                    if row["status"] == "NEW"
                )
            )
        )

        self.ack_card.value_label.setText(
            str(
                sum(
                    1
                    for row in all_rows
                    if row["status"] == "ACKNOWLEDGED"
                )
            )
        )

        self.resolved_card.value_label.setText(
            str(
                sum(
                    1
                    for row in all_rows
                    if row["status"] == "RESOLVED"
                )
            )
        )

        self.total_badge.setText(
            f"{len(rows)} INCIDENT"
            f"{'S' if len(rows) != 1 else ''}"
        )

        current = [
            row
            for row in rows
            if row["status"] != "RESOLVED"
        ]

        resolved = [
            row
            for row in rows
            if row["status"] == "RESOLVED"
        ]

        self._update_preview(
            self.live_card,
            current,
            "No current incidents."
        )

        self._update_preview(
            self.history_card,
            resolved,
            "No resolved incidents."
        )

        if self._live_open_handler is not None:
            try:
                self.live_card.open_button.clicked.disconnect(
                    self._live_open_handler
                )
            except (RuntimeError, TypeError):
                pass

        if self._history_open_handler is not None:
            try:
                self.history_card.open_button.clicked.disconnect(
                    self._history_open_handler
                )
            except (RuntimeError, TypeError):
                pass

        self._live_open_handler = lambda: self._open_incident_popup(
            current,
            "Current incidents",
            "Active and acknowledged security events.",
        )
        self._history_open_handler = lambda: self._open_incident_popup(
            resolved,
            "Incident history",
            "Previously resolved security events.",
        )

        self.live_card.open_button.clicked.connect(
            self._live_open_handler
        )
        self.history_card.open_button.clicked.connect(
            self._history_open_handler
        )

    def _update_preview(
        self,
        card: QFrame,
        rows: list[dict],
        empty_text: str,
    ) -> None:
        if not rows:
            card.preview_label.setText(
                empty_text
            )
            return

        lines: list[str] = []

        for row in rows[:4]:
            confidence = (
                float(row["confidence"]) * 100
            )

            lines.append(
                f"{row['camera_name']}   ·   "
                f"{row['event']}   ·   "
                f"{confidence:.0f}%"
            )

        if len(rows) > 4:
            lines.append(
                f"+ {len(rows) - 4} more incidents"
            )

        card.preview_label.setText(
            "\n".join(lines)
        )

    # ----------------------------------------------------------------------
    # Incident popup
    # ----------------------------------------------------------------------

    def _open_incident_popup(
        self,
        rows: list[dict],
        title: str,
        subtitle: str,
    ) -> None:
        if self._popup is not None:
            old_popup = self._popup
            self._popup = None
            old_popup.close_popup()
            old_popup.deleteLater()

        self._blur_effect = QGraphicsBlurEffect()
        self._blur_effect.setBlurRadius(
            8
        )

        self.main_content.setGraphicsEffect(
            self._blur_effect
        )

        popup = _HistoryPopup(
            self.window(),
            title,
            subtitle,
        )

        self._popup = popup

        popup.closed.connect(
            self._close_popup
        )

        body = QWidget()

        layout = QVBoxLayout(body)
        layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        if not rows:
            layout.addWidget(
                _empty_state(
                    "Nothing to show",
                    "There are no incidents matching the current filters.",
                )
            )
        else:
            table = QTableWidget(
                len(rows),
                8,
            )

            table.setHorizontalHeaderLabels(
                [
                    "ID",
                    "CAMERA",
                    "EVENT",
                    "CONFIDENCE",
                    "SEVERITY",
                    "STATUS",
                    "TIME",
                    "ACTIONS",
                ]
            )

            _configure_table(
                table
            )

            header = table.horizontalHeader()

            header.setSectionResizeMode(
                0,
                header.ResizeMode.ResizeToContents,
            )

            header.setSectionResizeMode(
                1,
                header.ResizeMode.Stretch,
            )

            header.setSectionResizeMode(
                2,
                header.ResizeMode.Stretch,
            )

            header.setSectionResizeMode(
                3,
                header.ResizeMode.ResizeToContents,
            )

            header.setSectionResizeMode(
                4,
                header.ResizeMode.ResizeToContents,
            )

            header.setSectionResizeMode(
                5,
                header.ResizeMode.ResizeToContents,
            )

            header.setSectionResizeMode(
                6,
                header.ResizeMode.ResizeToContents,
            )

            header.setSectionResizeMode(
                7,
                header.ResizeMode.ResizeToContents,
            )

            _apply_table_palette(
                table
            )

            for index, row in enumerate(rows):
                table.setItem(
                    index,
                    0,
                    _item(row["public_id"]),
                )

                table.setItem(
                    index,
                    1,
                    _item(row["camera_name"]),
                )

                table.setItem(
                    index,
                    2,
                    _item(row["event"]),
                )

                table.setItem(
                    index,
                    3,
                    _item(
                        f"{float(row['confidence']):.1%}",
                        Qt.AlignmentFlag.AlignCenter,
                    ),
                )

                table.setCellWidget(
                    index,
                    4,
                    _severity_widget(
                        row["severity"]
                    ),
                )

                table.setCellWidget(
                    index,
                    5,
                    _status_widget(
                        row["status"]
                    ),
                )

                table.setItem(
                    index,
                    6,
                    _item(
                        _local_time(
                            row["happened_at"]
                        )
                    ),
                )

                self._set_incident_action_cell(
                    table,
                    index,
                    7,
                    row,
                    allow_resolve=(row["status"] != "RESOLVED"),
                )

                table.setRowHeight(index, 64)

            layout.addWidget(
                table,
                1,
            )

        popup.set_content(
            body
        )

        popup.show_popup()

    def _set_incident_action_cell(
        self,
        table: QTableWidget,
        row_index: int,
        column: int,
        row: dict,
        allow_resolve: bool,
    ) -> None:
        actions = QWidget()
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(4, 4, 4, 4)
        action_layout.setSpacing(7)

        path = str(row.get("footage_path") or "")
        available = Path(path).is_file()

        view_button = _action_button(
            "View" if available else "Unavailable",
            "view",
        )
        view_button.setEnabled(available)
        if available:
            view_button.clicked.connect(
                lambda checked=False, p=path, public_id=row["public_id"]:
                self._open_footage(p, public_id)
            )
        action_layout.addWidget(view_button)

        if allow_resolve:
            ok_button = _action_button("OK", "resolve")
            ok_button.setCursor(Qt.CursorShape.PointingHandCursor)
            ok_button.clicked.connect(
                lambda checked=False, public_id=row["public_id"]:
                self._resolve_incident(public_id)
            )
            action_layout.addWidget(ok_button)

        table.setCellWidget(row_index, column, actions)

    def _resolve_incident(self, public_id: str) -> None:
        self.status_change_requested.emit(public_id, "RESOLVED")
        self._close_popup()

    def _open_footage(self, path: str, public_id: str) -> None:
        viewer = FootagePlayerDialog(path, f"Incident {public_id}", self.window())
        viewer.show()
        viewer.raise_()




    def _close_popup(self) -> None:
        if self._blur_effect is not None:
            self.main_content.setGraphicsEffect(None)
        self._blur_effect = None
        self._popup = None

# ============================================================================
# ALERTS PAGE
# ============================================================================

class AlertsPage(QWidget):
    clear_all_requested = Signal()

    def __init__(
        self,
        repository: Repository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.repository = repository

        self._blur_effect: QGraphicsBlurEffect | None = None
        self._popup: _HistoryPopup | None = None

        # Signal handlers are stored so refresh() can safely replace
        # existing button connections without disconnecting unknown slots.
        self._live_open_handler = None
        self._history_open_handler = None

        # ------------------------------------------------------------------
        # Root
        # ------------------------------------------------------------------

        root = QVBoxLayout(self)

        root.setContentsMargins(
            20,
            16,
            20,
            16,
        )

        root.setSpacing(14)

        self.main_content = QWidget()

        content_layout = QVBoxLayout(
            self.main_content
        )

        content_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        content_layout.setSpacing(14)

        root.addWidget(
            self.main_content,
            1,
        )

        # ------------------------------------------------------------------
        # Header
        # ------------------------------------------------------------------

        header = QHBoxLayout()

        header.addWidget(
            make_page_title(
                "Alerts",
                "Monitor active security alerts and review previously acknowledged events.",
            ),
            1,
        )

        self.alert_badge = QLabel(
            "0 ACTIVE"
        )

        self.alert_badge.setProperty(
            "statusBadge",
            True,
        )

        self.alert_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.alert_badge.setMinimumHeight(
            28
        )

        self.clear_all_button = QPushButton("Clear All")
        self.clear_all_button.setProperty("secondaryButton", True)
        self.clear_all_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_all_button.setMinimumHeight(30)
        self.clear_all_button.clicked.connect(self.clear_all_requested.emit)

        header.addWidget(
            self.clear_all_button,
            0,
            Qt.AlignmentFlag.AlignTop,
        )

        header.addWidget(
            self.alert_badge,
            0,
            Qt.AlignmentFlag.AlignTop,
        )

        content_layout.addLayout(
            header
        )

        # ------------------------------------------------------------------
        # Metrics
        # ------------------------------------------------------------------

        metrics = QHBoxLayout()
        metrics.setSpacing(9)

        self.active_card = _metric_card(
            "ACTIVE",
            "0",
        )

        self.history_card = _metric_card(
            "HISTORY",
            "0",
        )

        self.high_card = _metric_card(
            "HIGH SEVERITY",
            "0",
        )

        self.medium_card = _metric_card(
            "MEDIUM / LOW",
            "0",
        )

        for card in (
            self.active_card,
            self.history_card,
            self.high_card,
            self.medium_card,
        ):
            metrics.addWidget(
                card,
                1,
            )

        content_layout.addLayout(
            metrics
        )

        # ------------------------------------------------------------------
        # Split alert workspace
        # ------------------------------------------------------------------

        workspace = QHBoxLayout()
        workspace.setSpacing(12)

        self.history_panel = self._create_alert_panel(
            "ALERT HISTORY",
            "All generated security alerts, with active events shown first",
            "Open alert history",
        )

        workspace.addWidget(
            self.history_panel,
            1,
        )

        content_layout.addLayout(
            workspace,
            1,
        )

    # ----------------------------------------------------------------------
    # Alert panels
    # ----------------------------------------------------------------------

    def _create_alert_panel(
        self,
        title: str,
        subtitle: str,
        button_text: str,
    ) -> QFrame:
        frame = QFrame()

        frame.setProperty(
            "card",
            True,
        )

        layout = QVBoxLayout(
            frame
        )

        layout.setContentsMargins(
            17,
            16,
            17,
            16,
        )

        layout.setSpacing(10)

        header = _section_header(
            title,
            subtitle,
        )

        layout.addWidget(
            header
        )

        preview = QLabel(
            "No alerts"
        )

        preview.setProperty(
            "muted",
            True,
        )

        preview.setWordWrap(True)

        preview.setMinimumHeight(
            110
        )

        layout.addWidget(
            preview,
            1,
        )

        button = QPushButton(
            button_text
        )

        button.setProperty(
            "secondaryButton",
            True,
        )

        button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        layout.addWidget(
            button
        )

        frame.preview_label = preview  # type: ignore[attr-defined]
        frame.open_button = button  # type: ignore[attr-defined]

        return frame

    # ----------------------------------------------------------------------
    # Refresh
    # ----------------------------------------------------------------------

    def refresh(self) -> None:
        rows = (
            self.repository
            .list_alerts()
        )

        active = [
            row
            for row in rows
            if not row["acknowledged"]
        ]

        high_count = sum(
            1
            for row in active
            if row["severity"] == "HIGH"
        )

        medium_low_count = len(active) - high_count

        self.active_card.value_label.setText(
            str(len(active))
        )

        self.history_card.value_label.setText(
            str(len(rows))
        )

        self.high_card.value_label.setText(
            str(high_count)
        )

        self.medium_card.value_label.setText(
            str(medium_low_count)
        )

        self.alert_badge.setText(
            f"{len(active)} ACTIVE"
        )

        self._update_alert_preview(
            self.history_panel,
            rows,
            "No alerts in history."
        )

        if self._history_open_handler is not None:
            try:
                self.history_panel.open_button.clicked.disconnect(
                    self._history_open_handler
                )
            except (RuntimeError, TypeError):
                pass

        self._history_open_handler = lambda: self._open_alert_popup(
            rows,
            "Alert history",
            "All generated security alerts, with active events shown first.",
        )

        self.history_panel.open_button.clicked.connect(
            self._history_open_handler
        )

    def _update_alert_preview(
        self,
        panel: QFrame,
        rows: list[dict],
        empty_text: str,
    ) -> None:
        if not rows:
            panel.preview_label.setText(
                empty_text
            )
            return

        lines: list[str] = []

        for row in rows[:5]:
            confidence = (
                float(row["confidence"]) * 100
            )

            lines.append(
                f"{row['camera_name']}   ·   "
                f"{row['event']}   ·   "
                f"{row['severity']}   ·   "
                f"{confidence:.0f}%"
            )

        if len(rows) > 5:
            lines.append(
                f"+ {len(rows) - 5} more alerts"
            )

        panel.preview_label.setText(
            "\n".join(lines)
        )

    # ----------------------------------------------------------------------
    # Alert popup
    # ----------------------------------------------------------------------

    def _open_alert_popup(
        self,
        rows: list[dict],
        title: str,
        subtitle: str,
    ) -> None:
        if self._popup is not None:
            old_popup = self._popup
            self._popup = None
            old_popup.close_popup()
            old_popup.deleteLater()

        self._blur_effect = QGraphicsBlurEffect()

        self._blur_effect.setBlurRadius(
            8
        )

        self.main_content.setGraphicsEffect(
            self._blur_effect
        )

        popup = _HistoryPopup(
            self.window(),
            title,
            subtitle,
        )

        self._popup = popup

        popup.closed.connect(
            self._close_popup
        )

        body = QWidget()

        layout = QVBoxLayout(
            body
        )

        layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        if not rows:
            layout.addWidget(
                _empty_state(
                    "Nothing to show",
                    "There are no alerts in history.",
                )
            )

        else:
            columns = [
                "CAMERA",
                "EVENT",
                "CONFIDENCE",
                "SEVERITY",
                "TIME",
                "INCIDENT",
                "FOOTAGE",
            ]

            table_columns = 7

            table = QTableWidget(
                len(rows),
                table_columns,
            )

            table.setHorizontalHeaderLabels(
                [
                    "CAMERA",
                    "EVENT",
                    "CONFIDENCE",
                    "SEVERITY",
                    "TIME",
                    "INCIDENT",
                    "FOOTAGE",
                ]
            )

            _configure_table(
                table
            )

            header = table.horizontalHeader()

            header.setSectionResizeMode(
                0,
                header.ResizeMode.Stretch,
            )

            header.setSectionResizeMode(
                1,
                header.ResizeMode.Stretch,
            )

            header.setSectionResizeMode(
                2,
                header.ResizeMode.ResizeToContents,
            )

            header.setSectionResizeMode(
                3,
                header.ResizeMode.ResizeToContents,
            )

            header.setSectionResizeMode(
                4,
                header.ResizeMode.ResizeToContents,
            )

            header.setSectionResizeMode(
                5,
                header.ResizeMode.ResizeToContents,
            )

            header.setSectionResizeMode(
                6,
                header.ResizeMode.ResizeToContents,
            )

            _apply_table_palette(
                table
            )

            for index, row in enumerate(rows):
                table.setItem(
                    index,
                    0,
                    _item(
                        row["camera_name"]
                    ),
                )

                table.setItem(
                    index,
                    1,
                    _item(
                        row["event"]
                    ),
                )

                table.setItem(
                    index,
                    2,
                    _item(
                        f"{float(row['confidence']):.1%}",
                        Qt.AlignmentFlag.AlignCenter,
                    ),
                )

                table.setCellWidget(
                    index,
                    3,
                    _severity_widget(
                        row["severity"]
                    ),
                )

                table.setItem(
                    index,
                    4,
                    _item(
                        _local_time(
                            row["happened_at"]
                        )
                    ),
                )

                table.setItem(
                    index,
                    5,
                    _item(
                        row["public_id"]
                    ),
                )

                self._set_footage_cell(table, index, 6, row)
                table.setRowHeight(index, 64)

            layout.addWidget(
                table,
                1,
            )

        popup.set_content(
            body
        )

        popup.show_popup()

    def _set_footage_cell(
        self,
        table: QTableWidget,
        row_index: int,
        column: int,
        row: dict,
    ) -> None:
        path = str(row.get("footage_path") or "")
        available = Path(path).is_file()

        button = _action_button(
            "View" if available else "Unavailable",
            "view",
        )
        button.setEnabled(available)

        if available:
            button.clicked.connect(
                lambda checked=False, p=path, public_id=row["public_id"]:
                self._open_footage(p, public_id)
            )

        cell = QWidget()
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(button)
        table.setCellWidget(row_index, column, cell)

    def _open_footage(self, path: str, public_id: str) -> None:
        viewer = FootagePlayerDialog(
            path,
            f"Alert {public_id}",
            self.window(),
        )
        viewer.show()
        viewer.raise_()

    def _close_popup(self) -> None:
        if self._blur_effect is not None:
            self.main_content.setGraphicsEffect(
                None
            )

        self._blur_effect = None
        self._popup = None