from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsBlurEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from campusguard.settings import CameraConfig, CameraStats
from campusguard.storage import Repository
from campusguard.ui.common import CameraPreview, make_card, set_tone
from campusguard.ui.icons import IconLabel
from campusguard.ui.theme import get_palette


# Color of the little dot next to each notification, by notification "kind".
# "" means a neutral grey dot.
NOTIFICATION_TONES = {
    "camera_connected": "good",
    "camera_added": "good",
    "camera_disconnected": "",
    "camera_removed": "",
    "incident_detected": "bad",
    "alert_generated": "bad",
}


class PopupLayer(QWidget):
    """
    Full dashboard-local dimming layer.

    This is deliberately a QWidget rather than a QDialog so the popup
    remains completely inside the CampusGuard application.
    """

    outside_clicked = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            """
            QWidget {
                background: rgba(0, 0, 0, 105);
            }
            """
        )

        self.hide()

    def mousePressEvent(self, event) -> None:
        self.outside_clicked.emit()
        event.accept()


class GlassPopup(QFrame):
    """
    Reusable in-app glass popup.

    There is only ever one of these on DashboardPage. Its contents are
    replaced when the user switches between AI Engine and System Stats.
    """

    close_requested = Signal()

    def __init__(
        self,
        parent: QWidget,
        title: str,
        icon: str,
    ) -> None:
        super().__init__(parent)

        self.setObjectName("dashboardGlassPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._build_style()
        self._build_ui(title, icon)

    def _build_style(self) -> None:
        palette = get_palette()

        self.setStyleSheet(
            f"""
            QFrame#dashboardGlassPopup {{
                background: {palette.glass};
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 20px;
            }}

            QLabel#popupTitle {{
                font-size: 15pt;
                font-weight: 800;
                background: transparent;
                border: none;
            }}

            QLabel#popupSubtitle {{
                font-size: 8.5pt;
                color: palette(mid);
                background: transparent;
                border: none;
            }}

            QPushButton#popupClose {{
                border: none;
                background: transparent;
                font-size: 17pt;
                font-weight: 500;
                padding: 2px 5px;
                min-width: 28px;
                min-height: 28px;
            }}

            QPushButton#popupClose:hover {{
                background: rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }}

            QFrame#popupSection {{
                background: rgba(255, 255, 255, 0.035);
                border: 1px solid rgba(255, 255, 255, 0.075);
                border-radius: 13px;
            }}

            QFrame#popupStatTile {{
                background: rgba(255, 255, 255, 0.035);
                border: 1px solid rgba(255, 255, 255, 0.075);
                border-radius: 12px;
            }}

            QLabel#popupSectionTitle {{
                font-size: 8pt;
                font-weight: 800;
                letter-spacing: 1px;
                color: palette(mid);
                background: transparent;
                border: none;
            }}

            QLabel#popupKey {{
                font-size: 8.5pt;
                color: palette(mid);
                background: transparent;
                border: none;
            }}

            QLabel#popupValue {{
                font-size: 8.8pt;
                font-weight: 700;
                background: transparent;
                border: none;
            }}

            QLabel#popupBigValue {{
                font-size: 18pt;
                font-weight: 800;
                background: transparent;
                border: none;
            }}

            QLabel#popupSmallValue {{
                font-size: 7.5pt;
                color: palette(mid);
                background: transparent;
                border: none;
            }}
            """
        )

    def _build_ui(self, title: str, icon: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 17, 20, 18)
        root.setSpacing(10)

        # --------------------------------------------------------------
        # HEADER
        # --------------------------------------------------------------
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(9)

        # IMPORTANT:
        # Icon is created directly inside the header.
        # It cannot fall down into the popup body.
        self.header_icon = IconLabel(icon, 20, "good")
        header.addWidget(
            self.header_icon,
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )

        self.title_label = QLabel(title)
        self.title_label.setObjectName("popupTitle")
        header.addWidget(
            self.title_label,
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )

        header.addStretch(1)

        self.close_button = QPushButton("×")
        self.close_button.setObjectName("popupClose")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setToolTip("Close")
        self.close_button.clicked.connect(self.close_requested.emit)

        header.addWidget(
            self.close_button,
            0,
            Qt.AlignmentFlag.AlignTop,
        )

        root.addLayout(header)

        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("popupSubtitle")
        self.subtitle_label.setWordWrap(True)
        root.addWidget(self.subtitle_label)

        # Thin divider.
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        divider.setStyleSheet(
            "background: rgba(255,255,255,0.08); border: none; max-height: 1px;"
        )
        root.addWidget(divider)

        # Body is a normal QWidget.
        # NO QScrollArea here.
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(9)

        root.addWidget(self.body, 1)

    def set_header(
        self,
        title: str,
        icon: str,
        subtitle: str,
    ) -> None:
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)

        # Replace only the header icon.
        old_icon = self.header_icon
        header = old_icon.parentWidget().layout()

        if header is not None:
            index = header.indexOf(old_icon)

            new_icon = IconLabel(icon, 20, "good")
            header.removeWidget(old_icon)
            old_icon.deleteLater()

            header.insertWidget(
                index,
                new_icon,
                0,
                Qt.AlignmentFlag.AlignVCenter,
            )

            self.header_icon = new_icon

    def clear_body(self) -> None:
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

            child_layout = item.layout()
            if child_layout is not None:
                while child_layout.count():
                    child_item = child_layout.takeAt(0)
                    child_widget = child_item.widget()
                    if child_widget is not None:
                        child_widget.deleteLater()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_requested.emit()
            event.accept()
            return

        super().keyPressEvent(event)


class DashboardPage(QWidget):
    camera_selected = Signal(str)
    view_alerts_requested = Signal()

    def __init__(
        self,
        repository: Repository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.repository = repository

        self._cameras: dict[str, CameraConfig] = {}
        self._stats: dict[str, CameraStats] = {}
        self._ai_states: dict[str, tuple[str, float | None]] = {}
        self._model_statuses: dict[str, dict[str, str]] = {}
        self._tiles: dict[str, CameraPreview] = {}

        self._empty_label: QLabel | None = None
        self._camera_grid: QGridLayout | None = None

        # Runtime/model state.
        self._runtime_loaded: dict[str, bool] = {}
        self._runtime_messages: dict[str, str] = {}
        self._device_text: str | None = None
        self._settings = None
        self._notification_key: tuple = ()

        # Popup state.
        self._popup: GlassPopup | None = None
        self._popup_layer: PopupLayer | None = None
        self._popup_kind: str | None = None

        # --------------------------------------------------------------
        # Main dashboard shell
        # --------------------------------------------------------------
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # Everything below this widget is blurred when a popup opens.
        self._dashboard_content = QWidget()
        content_layout = QVBoxLayout(self._dashboard_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)

        # Blur effect belongs only to the dashboard content.
        # Popup layer and popup itself remain sharp.
        self._dashboard_blur = QGraphicsBlurEffect(self)
        self._dashboard_blur.setBlurRadius(0)
        self._dashboard_content.setGraphicsEffect(self._dashboard_blur)

        root.addWidget(self._dashboard_content, 1)

        # --------------------------------------------------------------
        # MAIN 1 : 3 STRUCTURE
        #
        # LEFT  = roughly 1/3
        # RIGHT = roughly 2/3
        # --------------------------------------------------------------
        main_row = QHBoxLayout()
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.setSpacing(16)

        # LEFT COLUMN
        left_column = QVBoxLayout()
        left_column.setContentsMargins(0, 0, 0, 0)
        left_column.setSpacing(12)

        self._engine_card = self._build_engine_card()
        self._stats_card = self._build_stats_card()
        self._notifications_card = self._build_notifications_card()

        # AI Engine and System Stats stay compact.
        left_column.addWidget(self._engine_card, 0)
        left_column.addWidget(self._stats_card, 0)

        # Notifications gets the remaining vertical space.
        left_column.addWidget(self._notifications_card, 1)

        left_wrapper = QWidget()
        left_wrapper.setLayout(left_column)

        # RIGHT COLUMN
        right_column = QVBoxLayout()
        right_column.setContentsMargins(0, 0, 0, 0)
        right_column.setSpacing(0)

        self._network_card = self._build_network_card()
        right_column.addWidget(self._network_card, 1)

        right_wrapper = QWidget()
        right_wrapper.setLayout(right_column)

        # 1 : 2 ratio.
        main_row.addWidget(left_wrapper, 1)
        main_row.addWidget(right_wrapper, 2)

        content_layout.addLayout(main_row, 1)

        # Popup layer is a sibling of the dashboard content.
        # Therefore the popup itself is NOT blurred.
        self._popup_layer = PopupLayer(self)
        self._popup_layer.outside_clicked.connect(self._close_popup)

    # ------------------------------------------------------------------
    # Dashboard cards
    # ------------------------------------------------------------------

    def _build_engine_card(self) -> QFrame:
        frame, layout = make_card("AI Engine", icon="cpu")

        frame.setCursor(Qt.CursorShape.PointingHandCursor)
        frame.setProperty("dashboardPopupCard", True)

        # --------------------------------------------------------------
        # Explicit header repair.
        #
        # make_card() is still used to preserve the existing theme,
        # but we explicitly guarantee that the title exists.
        # --------------------------------------------------------------
        self._ensure_card_header(frame, "AI Engine", "cpu")

        # Only a compact summary is visible on the dashboard.
        self.engine_summary = QLabel("Loading AI engine…")
        self.engine_summary.setProperty("muted", True)
        self.engine_summary.setWordWrap(True)
        self.engine_summary.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )

        layout.addWidget(self.engine_summary)

        hint = QLabel("Click to view engine configuration")
        hint.setProperty("muted", True)
        hint.setStyleSheet("font-size: 7.5pt;")
        layout.addWidget(hint)

        # Preserve backend-facing values.
        self.engine_values: dict[str, QLabel] = {}

        rows = (
            ("detector", "Person detector"),
            ("pose", "Pose model"),
            ("fight", "Fight classifier"),
            ("status", "Status"),
            ("device", "Compute device"),
            ("threshold", "Confidence threshold"),
            ("detection", "Detection"),
        )

        # Hidden values are still maintained by update_model_status()
        # and update_settings(). They are used by the popup.
        for key, text in rows:
            value = QLabel("—")
            value.setProperty("kvvalue", True)
            value.setVisible(False)
            self.engine_values[key] = value
            layout.addWidget(value)

        self._install_popup_filter(frame)

        return frame

    def _build_stats_card(self) -> QFrame:
        frame, layout = make_card("System Stats", icon="server")

        frame.setCursor(Qt.CursorShape.PointingHandCursor)
        frame.setProperty("dashboardPopupCard", True)

        self._ensure_card_header(frame, "System Stats", "server")

        # Compact dashboard summary.
        self.stats_summary = QLabel("0 Online · 0 Offline · 0 Incidents · 0 Alerts")
        self.stats_summary.setProperty("muted", True)
        self.stats_summary.setWordWrap(True)

        layout.addWidget(self.stats_summary)

        hint = QLabel("Click to view system statistics")
        hint.setProperty("muted", True)
        hint.setStyleSheet("font-size: 7.5pt;")
        layout.addWidget(hint)

        # Values remain available for the popup.
        self.online_value = QLabel("0")
        self.offline_value = QLabel("0")
        self.incident_value = QLabel("0")
        self.alert_value = QLabel("0")

        for label in (
            self.online_value,
            self.offline_value,
            self.incident_value,
            self.alert_value,
        ):
            label.setVisible(False)
            layout.addWidget(label)

        self._install_popup_filter(frame)

        return frame

    @staticmethod
    def _stat_tile(
        icon: str,
        tone: str,
        caption: str,
    ) -> tuple[QFrame, QLabel]:
        tile = QFrame()
        tile.setObjectName("popupStatTile")

        box = QVBoxLayout(tile)
        box.setContentsMargins(11, 9, 11, 9)
        box.setSpacing(2)

        box.addWidget(
            IconLabel(icon, 17, tone),
            0,
            Qt.AlignmentFlag.AlignLeft,
        )

        value = QLabel("0")
        value.setObjectName("popupBigValue")

        label = QLabel(caption)
        label.setObjectName("popupSmallValue")

        box.addWidget(value)
        box.addWidget(label)

        return tile, value

    def _build_notifications_card(self) -> QFrame:
        frame, layout = make_card("Notifications", icon="bell")

        view_alerts = QPushButton("View Alerts")
        view_alerts.setProperty("link", True)
        view_alerts.setCursor(Qt.CursorShape.PointingHandCursor)

        view_alerts.clicked.connect(
            lambda _checked=False: self.view_alerts_requested.emit()
        )

        frame.header_layout.addWidget(view_alerts)

        # Existing notification scrolling is preserved because this is
        # the dashboard notification feed, NOT one of the popups.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumHeight(120)
        scroll.viewport().setAutoFillBackground(False)

        content = QWidget()

        self._notification_layout = QVBoxLayout(content)
        self._notification_layout.setContentsMargins(0, 0, 4, 0)
        self._notification_layout.setSpacing(9)
        self._notification_layout.addStretch(1)

        scroll.setWidget(content)
        content.setAutoFillBackground(False)

        layout.addWidget(scroll, 1)

        return frame

    def _build_network_card(self) -> QFrame:
        frame, layout = make_card("Live Network", icon="activity")

        self.camera_count_pill = QLabel("0 cameras")
        self.camera_count_pill.setProperty("pill", True)

        frame.header_layout.insertWidget(
            frame.header_layout.count() - 1,
            self.camera_count_pill,
        )

        self.feed_scroll = QScrollArea()
        self.feed_scroll.setWidgetResizable(True)
        self.feed_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.feed_scroll.viewport().setAutoFillBackground(False)

        self.feed_content = QWidget()

        self._camera_grid = QGridLayout(self.feed_content)
        self._camera_grid.setContentsMargins(0, 0, 0, 0)
        self._camera_grid.setSpacing(12)

        self.feed_scroll.setWidget(self.feed_content)
        self.feed_content.setAutoFillBackground(False)

        layout.addWidget(self.feed_scroll, 1)

        return frame

    # ------------------------------------------------------------------
    # Header helper
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_card_header(
        frame: QFrame,
        title: str,
        icon: str,
    ) -> None:
        """
        Explicitly guarantee [icon] [title] in a card header.

        This prevents the AI Engine title from disappearing while still
        using the project's existing make_card/glass styling.
        """

        header = getattr(frame, "header_layout", None)

        if header is None:
            return

        # Look for an existing text title.
        title_found = False

        for index in range(header.count()):
            item = header.itemAt(index)
            widget = item.widget()

            if isinstance(widget, QLabel):
                if widget.text().strip() == title:
                    title_found = True
                    break

        if title_found:
            return

        # Find the first stretch and insert before it.
        insert_at = header.count()

        for index in range(header.count()):
            item = header.itemAt(index)
            if item.spacerItem() is not None:
                insert_at = index
                break

        icon_widget = IconLabel(icon, 18, "good")

        title_widget = QLabel(title)
        title_widget.setStyleSheet(
            "font-size: 10pt; font-weight: 800; "
            "background: transparent; border: none;"
        )

        header.insertWidget(
            insert_at,
            icon_widget,
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )

        header.insertWidget(
            insert_at + 1,
            title_widget,
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )

    def _install_popup_filter(self, widget: QWidget) -> None:
        widget.installEventFilter(self)

        for child in widget.findChildren(QWidget):
            child.installEventFilter(self)

    # ------------------------------------------------------------------
    # Popup interaction
    # ------------------------------------------------------------------

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            if watched is self._engine_card or watched in self._engine_card.findChildren(
                QWidget
            ):
                self._open_popup("ai")
                return True

            if watched is self._stats_card or watched in self._stats_card.findChildren(
                QWidget
            ):
                self._open_popup("stats")
                return True

        return super().eventFilter(watched, event)

    def _open_popup(self, kind: str) -> None:
        if self._popup_layer is None:
            return

        # --------------------------------------------------------------
        # Create only ONE popup.
        #
        # Switching AI Engine -> System Stats reuses the same popup.
        # --------------------------------------------------------------
        if self._popup is None:
            self._popup = GlassPopup(
                self,
                "AI Engine",
                "cpu",
            )

            self._popup.close_requested.connect(self._close_popup)
            self._popup_layer.raise_()

        self._popup_kind = kind

        if kind == "ai":
            self._populate_ai_popup()
        else:
            self._populate_stats_popup()

        self._popup_layer.setGeometry(self.rect())
        self._popup_layer.show()
        self._popup_layer.raise_()

        self._dashboard_blur.setBlurRadius(13)

        self._popup.show()
        self._popup.raise_()
        self._center_popup()

        self._popup.setFocus()

    def _close_popup(self) -> None:
        self._popup_kind = None

        self._dashboard_blur.setBlurRadius(0)

        if self._popup is not None:
            self._popup.hide()

        if self._popup_layer is not None:
            self._popup_layer.hide()

        self.setFocus()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)

        if self._popup_layer is not None:
            self._popup_layer.setGeometry(self.rect())

        if self._popup is not None and self._popup.isVisible():
            self._center_popup()

    def _center_popup(self) -> None:
        if self._popup is None:
            return

        viewport = self.rect()

        # Keep the popup away from the edges of the dashboard page.
        margin_x = 26
        margin_y = 22

        x = max(
            margin_x,
            (viewport.width() - self._popup.width()) // 2,
        )

        y = max(
            margin_y,
            (viewport.height() - self._popup.height()) // 2,
        )

        # Clamp it inside DashboardPage.
        x = min(
            x,
            max(
                margin_x,
                viewport.width() - self._popup.width() - margin_x,
            ),
        )

        y = min(
            y,
            max(
                margin_y,
                viewport.height() - self._popup.height() - margin_y,
            ),
        )

        self._popup.move(x, y)

    # ------------------------------------------------------------------
    # AI Engine popup
    # ------------------------------------------------------------------

    def _populate_ai_popup(self) -> None:
        if self._popup is None:
            return

        self._popup.set_header(
            "AI Engine",
            "cpu",
            "Current local detection engine configuration and runtime state.",
        )

        self._popup.clear_body()

        # Fixed compact size.
        self._popup.setFixedSize(650, 500)

        body = self._popup.body_layout

        # --------------------------------------------------------------
        # MODEL STATUS
        # --------------------------------------------------------------
        section = self._popup_section("MODEL STATUS")

        model_grid = QGridLayout()
        model_grid.setContentsMargins(11, 7, 11, 8)
        model_grid.setHorizontalSpacing(12)
        model_grid.setVerticalSpacing(5)

        self._popup_kv(
            model_grid,
            0,
            "Person detector",
            self._label_text("detector"),
        )
        self._popup_kv(
            model_grid,
            1,
            "Pose model",
            self._label_text("pose"),
        )
        self._popup_kv(
            model_grid,
            2,
            "Fight classifier",
            self._label_text("fight"),
        )

        section.layout().addLayout(model_grid)
        body.addWidget(section)

        # --------------------------------------------------------------
        # RUNTIME
        # --------------------------------------------------------------
        runtime_section = self._popup_section("RUNTIME")

        runtime_grid = QGridLayout()
        runtime_grid.setContentsMargins(11, 7, 11, 8)
        runtime_grid.setHorizontalSpacing(12)
        runtime_grid.setVerticalSpacing(5)

        self._popup_kv(
            runtime_grid,
            0,
            "Status",
            self._label_text("status"),
        )
        self._popup_kv(
            runtime_grid,
            1,
            "Compute device",
            self._label_text("device"),
        )
        self._popup_kv(
            runtime_grid,
            2,
            "Confidence threshold",
            self._label_text("threshold"),
        )
        self._popup_kv(
            runtime_grid,
            3,
            "Detection",
            self._label_text("detection"),
        )

        runtime_section.layout().addLayout(runtime_grid)
        body.addWidget(runtime_section)

        # --------------------------------------------------------------
        # CAMERA AI STATE
        # --------------------------------------------------------------
        state_section = self._popup_section("CAMERA AI STATE")

        state_grid = QGridLayout()
        state_grid.setContentsMargins(11, 7, 11, 8)
        state_grid.setHorizontalSpacing(12)
        state_grid.setVerticalSpacing(5)

        camera_count = len(self._cameras)

        live_count = 0
        detecting_count = 0

        for camera_id, state_data in self._ai_states.items():
            state, _confidence = state_data

            if camera_id in self._cameras:
                live_count += 1

            if state and state.upper() not in {"IDLE", "NONE", "NORMAL"}:
                detecting_count += 1

        self._popup_kv(
            state_grid,
            0,
            "Configured cameras",
            str(camera_count),
        )

        self._popup_kv(
            state_grid,
            1,
            "Receiving AI state",
            str(live_count),
        )

        self._popup_kv(
            state_grid,
            2,
            "Active detections",
            str(detecting_count),
        )

        state_section.layout().addLayout(state_grid)
        body.addWidget(state_section)

        # --------------------------------------------------------------
        # CURRENT MODEL PATHS
        # --------------------------------------------------------------
        model_section = self._popup_section("MODEL CONFIGURATION")

        model_grid_2 = QGridLayout()
        model_grid_2.setContentsMargins(11, 7, 11, 8)
        model_grid_2.setHorizontalSpacing(10)
        model_grid_2.setVerticalSpacing(4)

        settings = self._settings

        if settings is not None:
            paths = (
                ("Detector", settings.detector_model_path),
                ("Pose", settings.pose_model_path),
                ("Fight", settings.fight_model_path),
            )

            for row, (name, configured_path) in enumerate(paths):
                key = QLabel(name)
                key.setObjectName("popupKey")

                value = QLabel(
                    Path(configured_path).name
                    if configured_path
                    else "Not configured"
                )
                value.setObjectName("popupValue")
                value.setAlignment(
                    Qt.AlignmentFlag.AlignRight
                    | Qt.AlignmentFlag.AlignVCenter
                )

                model_grid_2.addWidget(key, row, 0)
                model_grid_2.addWidget(value, row, 1)

        else:
            empty = QLabel("Model configuration is not available yet.")
            empty.setObjectName("popupKey")
            model_grid_2.addWidget(empty, 0, 0)

        model_section.layout().addLayout(model_grid_2)
        body.addWidget(model_section)

        body.addStretch(1)

    # ------------------------------------------------------------------
    # System Stats popup
    # ------------------------------------------------------------------

    def _populate_stats_popup(self) -> None:
        if self._popup is None:
            return

        self._popup.set_header(
            "System Stats",
            "server",
            "Current camera, incident, alert, and system activity overview.",
        )

        self._popup.clear_body()

        # Fixed-size compact popup.
        # No QScrollArea is used.
        self._popup.setFixedSize(680, 500)

        body = self._popup.body_layout

        # --------------------------------------------------------------
        # FOUR MAIN STAT TILES
        # --------------------------------------------------------------
        stats_grid = QGridLayout()
        stats_grid.setContentsMargins(0, 0, 0, 0)
        stats_grid.setHorizontalSpacing(9)
        stats_grid.setVerticalSpacing(9)

        online_tile, online = self._stat_tile(
            "video",
            "good",
            "Cameras Online",
        )
        offline_tile, offline = self._stat_tile(
            "video-off",
            "muted",
            "Cameras Offline",
        )
        incidents_tile, incidents = self._stat_tile(
            "file-warning",
            "warn",
            "Total Incidents",
        )
        alerts_tile, alerts = self._stat_tile(
            "shield-alert",
            "bad",
            "Active Alerts",
        )

        online.setText(self.online_value.text())
        offline.setText(self.offline_value.text())
        incidents.setText(self.incident_value.text())
        alerts.setText(self.alert_value.text())

        stats_grid.addWidget(online_tile, 0, 0)
        stats_grid.addWidget(offline_tile, 0, 1)
        stats_grid.addWidget(incidents_tile, 0, 2)
        stats_grid.addWidget(alerts_tile, 0, 3)

        body.addLayout(stats_grid)

        # --------------------------------------------------------------
        # CAMERA FLEET
        # --------------------------------------------------------------
        fleet_section = self._popup_section("CAMERA FLEET")

        fleet_grid = QGridLayout()
        fleet_grid.setContentsMargins(11, 7, 11, 8)
        fleet_grid.setHorizontalSpacing(12)
        fleet_grid.setVerticalSpacing(5)

        camera_count = len(self._cameras)
        online_count = self._safe_int(self.online_value.text())
        offline_count = self._safe_int(self.offline_value.text())

        self._popup_kv(
            fleet_grid,
            0,
            "Configured cameras",
            str(camera_count),
        )
        self._popup_kv(
            fleet_grid,
            1,
            "Online",
            str(online_count),
        )
        self._popup_kv(
            fleet_grid,
            2,
            "Offline",
            str(offline_count),
        )

        # Resolution / FPS summary from camera stats.
        fps_values: list[float] = []

        for stats in self._stats.values():
            try:
                fps = float(getattr(stats, "fps", 0) or 0)
                if fps > 0:
                    fps_values.append(fps)
            except (TypeError, ValueError):
                pass

        average_fps = (
            sum(fps_values) / len(fps_values)
            if fps_values
            else 0.0
        )

        self._popup_kv(
            fleet_grid,
            3,
            "Average FPS",
            f"{average_fps:.1f}" if average_fps else "—",
        )

        fleet_section.layout().addLayout(fleet_grid)
        body.addWidget(fleet_section)

        # --------------------------------------------------------------
        # SYSTEM ACTIVITY
        # --------------------------------------------------------------
        activity_section = self._popup_section("SYSTEM ACTIVITY")

        activity_grid = QGridLayout()
        activity_grid.setContentsMargins(11, 7, 11, 8)
        activity_grid.setHorizontalSpacing(12)
        activity_grid.setVerticalSpacing(5)

        self._popup_kv(
            activity_grid,
            0,
            "Notifications",
            self._notification_count_text(),
        )

        self._popup_kv(
            activity_grid,
            1,
            "AI components",
            self._model_component_summary(),
        )

        device = (
            self._device_text
            or getattr(self._settings, "device", None)
            or "—"
        )

        self._popup_kv(
            activity_grid,
            2,
            "Compute device",
            str(device).upper(),
        )

        activity_section.layout().addLayout(activity_grid)
        body.addWidget(activity_section)

        # --------------------------------------------------------------
        # ACTIVE CAMERA DETAILS
        # --------------------------------------------------------------
        camera_section = self._popup_section("ACTIVE CAMERA DETAILS")

        camera_layout = QGridLayout()
        camera_layout.setContentsMargins(11, 7, 11, 8)
        camera_layout.setHorizontalSpacing(12)
        camera_layout.setVerticalSpacing(5)

        cameras = list(self._cameras.values())

        if cameras:
            # Compact fixed popup: show up to four configured camera
            # summaries in a two-column layout. No scrollbar is introduced.
            for index, camera in enumerate(cameras[:4]):
                stats = self._stats.get(camera.camera_id)

                camera_name = getattr(
                    camera,
                    "name",
                    None,
                ) or getattr(
                    camera,
                    "camera_id",
                    "Camera",
                )

                status = getattr(
                    stats,
                    "status",
                    "UNKNOWN",
                ) if stats is not None else "UNKNOWN"

                resolution = getattr(
                    stats,
                    "resolution",
                    "—",
                ) if stats is not None else "—"

                cell = QLabel(
                    f"{camera_name}  ·  {status}  ·  {resolution}"
                )
                cell.setObjectName("popupKey")
                cell.setWordWrap(False)

                row = index // 2
                column = index % 2

                camera_layout.addWidget(cell, row, column)

            if len(cameras) > 4:
                more = QLabel(
                    f"+ {len(cameras) - 4} additional configured camera(s)"
                )
                more.setObjectName("popupSmallValue")
                camera_layout.addWidget(
                    more,
                    2,
                    0,
                    1,
                    2,
                )
        else:
            empty = QLabel("No cameras are currently configured.")
            empty.setObjectName("popupKey")
            camera_layout.addWidget(empty, 0, 0, 1, 2)

        camera_section.layout().addLayout(camera_layout)
        body.addWidget(camera_section)

        body.addStretch(1)

    # ------------------------------------------------------------------
    # Popup helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _popup_section(title: str) -> QFrame:
        section = QFrame()
        section.setObjectName("popupSection")

        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        heading = QLabel(title)
        heading.setObjectName("popupSectionTitle")

        layout.addWidget(heading)

        return section

    @staticmethod
    def _popup_kv(
        grid: QGridLayout,
        row: int,
        key: str,
        value: str,
    ) -> None:
        key_label = QLabel(key)
        key_label.setObjectName("popupKey")

        value_label = QLabel(value or "—")
        value_label.setObjectName("popupValue")
        value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter
        )

        grid.addWidget(key_label, row, 0)
        grid.addWidget(value_label, row, 1)

    def _label_text(self, key: str) -> str:
        label = self.engine_values.get(key)

        if label is None:
            return "—"

        return label.text() or "—"

    @staticmethod
    def _safe_int(value: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _notification_count_text(self) -> str:
        try:
            rows = self.repository.list_notifications(100)
            return str(len(rows))
        except Exception:
            return "—"

    def _model_component_summary(self) -> str:
        loaded = sum(
            1
            for value in self._runtime_loaded.values()
            if value is True
        )

        total = 3

        if loaded == total:
            return f"{loaded}/{total} Ready"

        if loaded:
            return f"{loaded}/{total} Ready"

        if self._runtime_loaded:
            return "Not ready"

        return "Pending"

    # ------------------------------------------------------------------
    # Camera grid
    # ------------------------------------------------------------------

    def sync_cameras(self, cameras: list[CameraConfig]) -> None:
        if self._camera_grid is None:
            return

        new_ids = {camera.camera_id for camera in cameras}

        for camera_id in set(self._tiles) - new_ids:
            tile = self._tiles.pop(camera_id)
            self._camera_grid.removeWidget(tile)
            tile.deleteLater()

            self._stats.pop(camera_id, None)
            self._ai_states.pop(camera_id, None)
            self._model_statuses.pop(camera_id, None)

        self._cameras = {
            camera.camera_id: camera
            for camera in cameras
        }

        for camera in cameras:
            tile = self._tiles.get(camera.camera_id)

            if tile is None:
                tile = CameraPreview(camera)
                tile.selected.connect(self.camera_selected.emit)
                self._tiles[camera.camera_id] = tile
            else:
                tile.set_camera(camera)

            self._update_tile(camera.camera_id)

        while self._camera_grid.count():
            item = self._camera_grid.takeAt(0)
            widget = item.widget()

            if widget is not None and widget is self._empty_label:
                widget.deleteLater()
                self._empty_label = None

        for index, camera in enumerate(cameras):
            self._camera_grid.addWidget(
                self._tiles[camera.camera_id],
                index // 2,
                index % 2,
            )

        count = len(cameras)

        self.camera_count_pill.setText(
            f"{count} camera{'' if count == 1 else 's'}"
        )

        if not cameras:
            self._empty_label = QLabel(
                "No cameras configured. Add an external USB, RTSP, "
                "HTTP/MJPEG, or IP camera from the Cameras page."
            )

            self._empty_label.setWordWrap(True)
            self._empty_label.setAlignment(
                Qt.AlignmentFlag.AlignCenter
            )
            self._empty_label.setProperty("muted", True)

            self._camera_grid.addWidget(
                self._empty_label,
                0,
                0,
            )

    def update_camera_stats(
        self,
        camera_id: str,
        stats: CameraStats,
    ) -> None:
        self._stats[camera_id] = stats
        self._update_tile(camera_id)

    def update_frame(
        self,
        camera_id: str,
        image,
        state: str,
        confidence: float | None,
    ) -> None:
        if camera_id not in self._tiles:
            return

        self._ai_states[camera_id] = (
            state,
            confidence,
        )

        self._tiles[camera_id].set_frame(
            QPixmap.fromImage(image)
        )

    # ------------------------------------------------------------------
    # AI Engine backend
    # ------------------------------------------------------------------

    def update_model_status(
        self,
        camera_id: str,
        component: str,
        message: str,
    ) -> None:
        """
        Called whenever a camera worker reports on a model or device.
        """

        self._model_statuses.setdefault(
            camera_id,
            {},
        )[component] = message

        if component in {"detector", "pose", "fight"}:
            self._runtime_loaded[component] = (
                message.upper().startswith("READY")
            )
            self._runtime_messages[component] = message

        elif component == "device":
            self._device_text = message

        self._refresh_engine()

    def update_settings(
        self,
        confidence_threshold: float,
        detection_enabled: bool,
    ) -> None:
        self._set_value(
            "threshold",
            f"{confidence_threshold:.0%}",
        )

        self._set_value(
            "detection",
            "Enabled" if detection_enabled else "Disabled",
        )

    def update_model_configuration(
        self,
        settings,
    ) -> None:
        self._settings = settings

        self.update_settings(
            settings.confidence_threshold,
            settings.detection_enabled,
        )

        self._refresh_engine()

    def _refresh_engine(self) -> None:
        settings = self._settings

        if settings is None:
            self._update_engine_summary()
            return

        paths = {
            "detector": settings.detector_model_path,
            "pose": settings.pose_model_path,
            "fight": settings.fight_model_path,
        }

        loaded = 0
        present = 0

        for key, configured in paths.items():
            path = (
                Path(configured).expanduser()
                if configured.strip()
                else None
            )

            exists = bool(
                path
                and path.is_file()
            )

            runtime = self._runtime_loaded.get(key)
            name = path.name if path else ""

            tooltip = self._runtime_messages.get(
                key,
                "",
            )

            if runtime is True:
                loaded += 1
                present += 1

                self._set_value(
                    key,
                    name or "Loaded",
                    "good",
                    tooltip,
                )

            elif runtime is False or not exists:
                self._set_value(
                    key,
                    "Not loaded",
                    "warn",
                    tooltip
                    or f"File not found: {configured}",
                )

            else:
                present += 1

                self._set_value(
                    key,
                    name,
                    "",
                    "Found on disk; loads when a camera starts",
                )

        if loaded == 3:
            status = ("ACTIVE", "good")
        elif loaded > 0:
            status = ("PARTIAL", "warn")
        elif self._runtime_loaded:
            status = ("NOT LOADED", "bad")
        elif present == 3:
            status = ("READY", "")
        elif present > 0:
            status = ("PARTIAL", "warn")
        else:
            status = ("NO MODELS", "warn")

        self._set_value(
            "status",
            *status,
        )

        self._set_value(
            "device",
            self._device_text
            or settings.device.upper(),
        )

        self._update_engine_summary()

    def _set_value(
        self,
        key: str,
        text: str,
        tone: str = "",
        tooltip: str = "",
    ) -> None:
        label = self.engine_values[key]

        label.setText(text)
        label.setToolTip(tooltip)

        set_tone(
            label,
            tone,
        )

    def _update_engine_summary(self) -> None:
        model_status = self._label_text("status")
        device = self._label_text("device")
        detection = self._label_text("detection")

        models = [
            self._label_text("detector"),
            self._label_text("pose"),
            self._label_text("fight"),
        ]

        ready_count = sum(
            1
            for model in models
            if model not in {
                "—",
                "",
                "Not loaded",
            }
        )

        if ready_count == 3:
            model_text = "3 Models"
        elif ready_count:
            model_text = f"{ready_count}/3 Models"
        else:
            model_text = "Models pending"

        self.engine_summary.setText(
            f"{model_text}  ·  {device}  ·  "
            f"{detection}  ·  {model_status}"
        )

    # ------------------------------------------------------------------
    # Stats + notifications
    # ------------------------------------------------------------------

    def refresh_summary(self) -> None:
        online = 0

        for camera_id in self._cameras:
            stats = self._stats.get(camera_id)

            if stats is not None:
                if getattr(stats, "status", "") == "LIVE":
                    online += 1

        offline = max(
            0,
            len(self._cameras) - online,
        )

        incident_count = self.repository.incident_count()
        alert_count = self.repository.active_alert_count()

        self.online_value.setText(str(online))
        self.offline_value.setText(str(offline))
        self.incident_value.setText(str(incident_count))
        self.alert_value.setText(str(alert_count))

        self.stats_summary.setText(
            f"{online} Online  ·  "
            f"{offline} Offline  ·  "
            f"{incident_count} Incidents  ·  "
            f"{alert_count} Alerts"
        )

        self._show_notifications(
            self.repository.list_notifications(8)
        )

    def _show_notifications(
        self,
        rows: list[dict],
    ) -> None:
        # This runs every 1.5 seconds.
        # Only rebuild when something actually changed.
        key = tuple(
            (
                row["created_at"],
                row["message"],
            )
            for row in rows
        )

        if key == self._notification_key:
            return

        self._notification_key = key

        layout = self._notification_layout

        while layout.count() > 1:
            item = layout.takeAt(0)

            if item.widget() is not None:
                item.widget().deleteLater()

        if not rows:
            empty = QLabel("No notifications yet.")
            empty.setProperty("muted", True)

            layout.insertWidget(
                0,
                empty,
            )

            return

        for index, row in enumerate(rows):
            layout.insertWidget(
                index,
                self._notification_row(row),
            )

    @staticmethod
    def _notification_row(
        row: dict,
    ) -> QWidget:
        widget = QWidget()

        outer = QHBoxLayout(widget)
        outer.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        outer.setSpacing(8)

        dot = QLabel("●")

        tone = NOTIFICATION_TONES.get(
            row.get("kind", ""),
            "",
        )

        if tone:
            set_tone(
                dot,
                tone,
            )
        else:
            dot.setProperty(
                "muted",
                True,
            )

        outer.addWidget(
            dot,
            0,
            Qt.AlignmentFlag.AlignTop,
        )

        text = QVBoxLayout()
        text.setSpacing(1)

        message = QLabel(
            row["message"]
        )
        message.setWordWrap(True)

        stamp = QLabel(
            row["created_at"][11:19]
        )
        stamp.setProperty(
            "muted",
            True,
        )
        stamp.setStyleSheet(
            "font-size: 7.5pt;"
        )

        text.addWidget(message)
        text.addWidget(stamp)

        outer.addLayout(
            text,
            1,
        )

        return widget

    # ------------------------------------------------------------------
    # Camera tile update
    # ------------------------------------------------------------------

    def _update_tile(
        self,
        camera_id: str,
    ) -> None:
        camera = self._cameras.get(camera_id)
        tile = self._tiles.get(camera_id)

        if not camera or not tile:
            return

        # IMPORTANT:
        # Do not instantiate CameraStats() as a fallback. Some versions
        # of CameraStats may require constructor arguments.
        stats = self._stats.get(camera_id)

        if stats is None:
            return

        tile.set_status(
            stats,
            camera.ai_enabled,
        )