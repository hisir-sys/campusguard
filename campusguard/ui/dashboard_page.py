from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from campusguard.settings import CameraConfig, CameraStats
from campusguard.storage import Repository
from campusguard.ui.common import CameraPreview, make_card, set_tone
from campusguard.ui.icons import IconLabel
from campusguard.ui.theme import get_palette, rgba


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
    Full-page dark overlay behind the in-app glass popup.
    """

    outside_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setObjectName("popupLayer")
        self.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )

        self.setStyleSheet(
            """
            QWidget#popupLayer {
                background: rgba(0, 0, 0, 115);
            }
            """
        )

    def mousePressEvent(self, event) -> None:
        self.outside_clicked.emit()
        event.accept()


class GlassPopup(QFrame):
    """
    In-app glass popup.

    This is deliberately a QFrame rather than QDialog so that it remains
    part of the CampusGuard dashboard and can sit above the blurred page.
    """

    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setObjectName("glassPopup")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.setMinimumWidth(780)
        self.setMaximumWidth(920)

        # A wider, lower glass panel keeps normal status information readable
        # without forcing the operator through a long scroll.
        self.setMinimumHeight(360)
        self.setMaximumHeight(590)

        self._apply_palette()

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 105))
        self.setGraphicsEffect(shadow)

        # --------------------------------------------------------------
        # Main popup layout
        # --------------------------------------------------------------

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(16)

        # --------------------------------------------------------------
        # TOP HEADER
        #
        # Icon + title + subtitle are all explicitly placed here.
        # --------------------------------------------------------------

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(13)
        self._header_layout = header

        self.icon = IconLabel(
            "cpu",
            25,
        )

        # Important:
        # The icon is inserted directly into the popup header.
        header.addWidget(
            self.icon,
            0,
            Qt.AlignmentFlag.AlignTop,
        )

        title_column = QVBoxLayout()
        title_column.setContentsMargins(0, 0, 0, 0)
        title_column.setSpacing(3)

        self.title = QLabel("AI Engine")
        self.title.setObjectName("popupTitle")

        self.subtitle = QLabel("")
        self.subtitle.setObjectName("popupSubtitle")
        self.subtitle.setProperty("muted", True)
        self.subtitle.setWordWrap(True)

        title_column.addWidget(self.title)
        title_column.addWidget(self.subtitle)

        header.addLayout(
            title_column,
            1,
        )

        self.close_button = QLabel("×")
        self.close_button.setObjectName("popupClose")
        self.close_button.setFixedSize(30, 30)
        self.close_button.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.close_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.close_button.installEventFilter(self)

        header.addWidget(
            self.close_button,
            0,
            Qt.AlignmentFlag.AlignTop,
        )

        root.addLayout(header)

        # --------------------------------------------------------------
        # Scrollable popup body
        #
        # This is the important fix for System Stats.
        # The popup itself stays bounded while the body scrolls.
        # --------------------------------------------------------------

        self.scroll = QScrollArea()
        self.scroll.setObjectName("popupScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.body_widget = QWidget()

        self.body = QVBoxLayout(
            self.body_widget
        )
        self.body.setContentsMargins(
            0,
            0,
            5,
            0,
        )
        self.body.setSpacing(12)

        self.scroll.setWidget(
            self.body_widget
        )

        root.addWidget(
            self.scroll,
            1,
        )

    def _apply_palette(self) -> None:
        palette = get_palette()

        self.setStyleSheet(
            f"""
            QFrame#glassPopup {{
                background: {rgba(palette.glass, palette.glass_alpha)};
                color: {palette.text};
                border: 1px solid {rgba(palette.line, min(255, int(palette.line_alpha * 1.6)))};
                border-radius: 26px;
            }}

            QLabel#popupTitle {{
                color: {palette.text};
                font-size: 18pt;
                font-weight: 760;
                background: transparent;
                border: none;
            }}

            QLabel#popupSubtitle {{
                color: {palette.text_dim};
                font-size: 9pt;
                background: transparent;
                border: none;
            }}

            QLabel#popupClose {{
                color: {palette.text};
                background: {rgba(palette.veil, min(255, palette.veil_alpha * 2))};
                border: 1px solid {rgba(palette.line, palette.line_alpha)};
                border-radius: 15px;
                font-size: 15pt;
                font-weight: 500;
            }}

            QLabel#popupClose:hover {{
                background: {rgba(palette.veil, min(255, palette.veil_alpha * 3))};
            }}

            QFrame#popupSection {{
                background: {rgba(palette.veil, max(1, int(palette.veil_alpha * 0.7)))};
                color: {palette.text};
                border: 1px solid {rgba(palette.line, palette.line_alpha)};
                border-radius: 17px;
            }}

            QFrame#popupMetric {{
                background: {rgba(palette.veil, max(1, int(palette.veil_alpha * 0.6)))};
                color: {palette.text};
                border: 1px solid {rgba(palette.line, max(1, int(palette.line_alpha * 0.8)))};
                border-radius: 15px;
            }}

            QLabel#popupSectionTitle {{
                color: {palette.text_dim};
                font-size: 9pt;
                font-weight: 700;
                background: transparent;
                border: none;
            }}

            QLabel#popupKey {{
                color: {palette.text_dim};
                font-size: 9pt;
                background: transparent;
                border: none;
            }}

            QLabel#popupValue {{
                color: {palette.text};
                font-size: 9pt;
                font-weight: 650;
                background: transparent;
                border: none;
            }}

            QLabel#popupMetricValue {{
                color: {palette.text};
                font-size: 20pt;
                font-weight: 750;
                background: transparent;
                border: none;
            }}

            QLabel#popupMetricCaption {{
                color: {palette.text_dim};
                font-size: 8pt;
                background: transparent;
                border: none;
            }}

            QScrollArea#popupScroll {{
                background: transparent;
                border: none;
            }}

            QScrollArea#popupScroll QWidget {{
                background: transparent;
                color: {palette.text};
            }}
            """
        )

    def retint(self) -> None:
        self._apply_palette()

    def eventFilter(
        self,
        watched,
        event,
    ) -> bool:
        if watched is self.close_button:
            if event.type() == QEvent.Type.MouseButtonPress:
                self.closed.emit()
                return True

        return super().eventFilter(
            watched,
            event,
        )

    def keyPressEvent(
        self,
        event,
    ) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.closed.emit()
            event.accept()
            return

        super().keyPressEvent(event)

    def set_header(
        self,
        title: str,
        subtitle: str,
        icon: str,
    ) -> None:
        """
        Update the existing popup header.

        The icon remains in the header. It is never inserted into
        the body, which fixes the previous floating-icon problem.
        """

        self.title.setText(title)
        self.subtitle.setText(subtitle)

        # Replace only the icon widget in the existing header.
        # Never derive this from parentWidget(): nested Qt layouts can make
        # the parent the popup root, which previously stranded the icon at
        # the bottom of the popup.
        header_layout = self._header_layout

        index = header_layout.indexOf(
            self.icon
        )

        old_icon = self.icon

        new_icon = IconLabel(
            icon,
            25,
        )

        header_layout.insertWidget(
            index,
            new_icon,
            0,
            Qt.AlignmentFlag.AlignTop,
        )

        header_layout.removeWidget(
            old_icon
        )

        old_icon.deleteLater()

        self.icon = new_icon

    def clear_body(self) -> None:
        """
        Completely clear popup content.
        """

        while self.body.count():
            item = self.body.takeAt(0)

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

    def prepare_for_display(self) -> None:
        """
        Reset scroll position whenever a popup is opened.
        """

        self.scroll.verticalScrollBar().setValue(0)
        self.scroll.horizontalScrollBar().setValue(0)


class DashboardPage(QWidget):
    camera_selected = Signal(str)
    view_alerts_requested = Signal()
    clear_notifications_requested = Signal()

    def __init__(
        self,
        repository: Repository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.repository = repository

        self._cameras: dict[str, CameraConfig] = {}
        self._stats: dict[str, CameraStats] = {}
        self._ai_states: dict[
            str,
            tuple[str, float | None],
        ] = {}

        self._model_statuses: dict[
            str,
            dict[str, str],
        ] = {}

        self._tiles: dict[
            str,
            CameraPreview,
        ] = {}

        self._empty_label: QLabel | None = None
        self._camera_grid: QGridLayout | None = None

        self._runtime_loaded: dict[
            str,
            bool,
        ] = {}

        self._runtime_messages: dict[
            str,
            str,
        ] = {}

        self._device_text: str | None = None
        self._settings = None
        self._notification_key: tuple = ()

        self._popup_kind: str | None = None

        # ==============================================================
        # DASHBOARD CONTENT
        # ==============================================================

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        outer.setSpacing(0)

        self._dashboard_content = QWidget()
        self._dashboard_content.setObjectName(
            "dashboardContent"
        )

        root = QVBoxLayout(
            self._dashboard_content
        )

        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(24)

        # --------------------------------------------------------------
        # Primary dashboard: 1/3 left, 2/3 right.
        # Live Network is intentionally full-width below so the camera
        # grid gets the largest uninterrupted visual area.
        # --------------------------------------------------------------
        main_row = QHBoxLayout()
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.setSpacing(24)

        left_column = QVBoxLayout()
        left_column.setContentsMargins(0, 0, 0, 0)
        left_column.setSpacing(24)

        self._engine_card = self._build_engine_card()
        self._stats_card = self._build_stats_card()
        self._notifications_card = self._build_notifications_card()
        self._network_card = self._build_network_card()

        left_column.addWidget(self._engine_card, 0)
        left_column.addWidget(self._stats_card, 0)

        right_column = QVBoxLayout()
        right_column.setContentsMargins(0, 0, 0, 0)
        right_column.setSpacing(24)
        right_column.addWidget(self._notifications_card, 1)

        main_row.addLayout(left_column, 1)
        main_row.addLayout(right_column, 2)
        root.addLayout(main_row, 0)

        self._network_card.setMinimumHeight(360)
        root.addWidget(self._network_card, 1)

        outer.addWidget(self._dashboard_content, 1)

        # ==============================================================
        # DASHBOARD BLUR
        #
        # Keep the dashboard unmodified during normal operation. The blur
        # effect is created only when a popup is actually opened.
        # ==============================================================
        self._dashboard_blur = None

        # ==============================================================
        # POPUP OVERLAY
        # ==============================================================

        self._popup_overlay = PopupLayer(
            self
        )

        self._popup_overlay.hide()

        self._popup_overlay.outside_clicked.connect(
            self._close_popup
        )

        self._popup = GlassPopup(
            self._popup_overlay
        )

        self._popup.closed.connect(
            self._close_popup
        )

        self._popup.hide()

    # ==================================================================
    # RESIZE
    # ==================================================================

    def resizeEvent(
        self,
        event,
    ) -> None:
        super().resizeEvent(event)

        self._popup_overlay.setGeometry(
            self.rect()
        )

        if self._popup.isVisible():
            self._center_popup()

    def _center_popup(self) -> None:
        """
        Center popup inside the DashboardPage.

        Because the popup overlay covers only the dashboard page,
        the popup cannot extend into the application's navigation
        outside this page.
        """

        available_height = self.height()

        # Keep a safe margin around the popup.
        safe_margin = 28

        maximum_height = max(
            260,
            available_height - (safe_margin * 2),
        )

        # Never allow the popup to become excessively tall.
        maximum_height = min(
            maximum_height,
            590,
        )

        self._popup.setMaximumHeight(
            maximum_height
        )

        self._popup.adjustSize()

        width = self._popup.width()
        height = self._popup.height()

        x = (
            self.width() - width
        ) // 2

        y = (
            self.height() - height
        ) // 2

        x = max(
            20,
            x,
        )

        y = max(
            safe_margin,
            y,
        )

        # Extra protection against bottom overflow.
        if (
            y + height
            > self.height() - safe_margin
        ):
            y = (
                self.height()
                - height
                - safe_margin
            )

        y = max(
            safe_margin,
            y,
        )

        self._popup.setGeometry(
            x,
            y,
            width,
            height,
        )

    # ==================================================================
    # AI ENGINE CARD
    # ==================================================================

    def _build_engine_card(self) -> QFrame:
        frame, layout = make_card("AI Engine", icon="cpu")
        frame.setMinimumHeight(176)
        frame.setMaximumHeight(176)
        frame.setCursor(Qt.CursorShape.PointingHandCursor)
        frame.installEventFilter(self)
        for child in frame.findChildren(QWidget):
            child.installEventFilter(self)

        self.engine_values = {}
        rows = (
            ("violence_model", "Active model"),
            ("status", "Engine status"),
            ("device", "Compute"),
        )
        for key, text in rows:
            row = QHBoxLayout()
            label = QLabel(text)
            label.setProperty("kvlabel", True)
            value = QLabel("—")
            value.setProperty("kvvalue", True)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(label)
            row.addStretch(1)
            row.addWidget(value)
            layout.addLayout(row)
            self.engine_values[key] = value
        return frame

    # ==================================================================
    # SYSTEM STATS CARD
    # ==================================================================

    def _build_stats_card(self) -> QFrame:
        frame, layout = make_card("System Stats", icon="server")
        frame.setMinimumHeight(128)
        frame.setMaximumHeight(128)
        frame.setCursor(Qt.CursorShape.PointingHandCursor)
        frame.installEventFilter(self)
        for child in frame.findChildren(QWidget):
            child.installEventFilter(self)

        preview = QGridLayout()
        preview.setContentsMargins(0, 0, 0, 0)
        preview.setHorizontalSpacing(18)
        preview.setVerticalSpacing(4)

        self.online_value = QLabel("0")
        self.online_value.setProperty("kvvalue", True)
        self.offline_value = QLabel("0")
        self.offline_value.setProperty("kvvalue", True)
        self.incident_value = QLabel("0")
        self.incident_value.setProperty("kvvalue", True)
        self.alert_value = QLabel("0")
        self.alert_value.setProperty("kvvalue", True)
        values = (
            ("video", "good", self.online_value, "Cameras"),
            ("file-warning", "warn", self.incident_value, "Open incidents"),
            ("shield-alert", "bad", self.alert_value, "Alerts"),
        )
        for index, (icon, tone, value, label_text) in enumerate(values):
            cell = QHBoxLayout()
            cell.setSpacing(6)
            cell.addWidget(IconLabel(icon, 14, tone))
            cell.addWidget(value)
            label = QLabel(label_text)
            label.setProperty("muted", True)
            cell.addWidget(label)
            cell.addStretch(1)
            wrapper = QWidget()
            wrapper.setLayout(cell)
            preview.addWidget(wrapper, index // 3, index % 3)

        layout.addLayout(preview)
        return frame

    # ==================================================================
    # NOTIFICATIONS
    # ==================================================================

    def _build_notifications_card(
        self,
    ) -> QFrame:
        frame, layout = make_card(
            "Notifications",
            icon="bell",
        )

        view_alerts = QPushButton(
            "View Alerts"
        )

        view_alerts.setProperty(
            "link",
            True,
        )

        view_alerts.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        view_alerts.clicked.connect(
            lambda _checked=False:
            self.view_alerts_requested.emit()
        )

        clear_notifications = QPushButton(
            "Clear All"
        )
        clear_notifications.setProperty(
            "link",
            True,
        )
        clear_notifications.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        clear_notifications.clicked.connect(
            lambda _checked=False:
            self.clear_notifications_requested.emit()
        )

        frame.header_layout.addWidget(
            clear_notifications
        )

        frame.header_layout.addWidget(
            view_alerts
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(
            QFrame.Shape.NoFrame
        )

        scroll.setMinimumHeight(196)

        scroll.viewport().setAutoFillBackground(
            False
        )

        content = QWidget()

        self._notification_layout = QVBoxLayout(
            content
        )

        self._notification_layout.setContentsMargins(
            0,
            0,
            4,
            0,
        )

        self._notification_layout.setSpacing(0)

        self._notification_layout.addStretch(
            1
        )

        scroll.setWidget(
            content
        )

        content.setAutoFillBackground(
            False
        )

        layout.addWidget(
            scroll,
            1,
        )

        return frame

    # ==================================================================
    # LIVE NETWORK
    # ==================================================================

    def _build_network_card(
        self,
    ) -> QFrame:
        frame, layout = make_card(
            "Live Network",
            icon="activity",
        )

        self.camera_count_pill = QLabel(
            "0 cameras"
        )

        self.camera_count_pill.setProperty(
            "pill",
            True,
        )

        frame.header_layout.insertWidget(
            frame.header_layout.count() - 1,
            self.camera_count_pill,
        )

        self.feed_scroll = QScrollArea()

        self.feed_scroll.setWidgetResizable(
            True
        )

        self.feed_scroll.setFrameShape(
            QFrame.Shape.NoFrame
        )

        self.feed_scroll.viewport().setAutoFillBackground(
            False
        )

        self.feed_content = QWidget()

        self._camera_grid = QGridLayout(
            self.feed_content
        )

        self._camera_grid.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self._camera_grid.setHorizontalSpacing(16)
        self._camera_grid.setVerticalSpacing(16)

        self.feed_scroll.setWidget(
            self.feed_content
        )

        self.feed_content.setAutoFillBackground(
            False
        )

        layout.addWidget(
            self.feed_scroll,
            1,
        )

        return frame

    # ==================================================================
    # POPUP EVENT HANDLING
    # ==================================================================

    def eventFilter(
        self,
        watched,
        event,
    ) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:

            if (
                watched is self._engine_card
                or watched
                in self._engine_card.findChildren(
                    QWidget
                )
            ):
                self._open_popup("ai")
                return True

            if (
                watched is self._stats_card
                or watched
                in self._stats_card.findChildren(
                    QWidget
                )
            ):
                self._open_popup("stats")
                return True

        return super().eventFilter(
            watched,
            event,
        )

    def _open_popup(
        self,
        kind: str,
    ) -> None:
        """
        Open exactly one popup.

        The dashboard gets blurred/dimmed while the glass popup remains
        sharp.
        """

        self._popup_kind = kind

        self._popup_overlay.setGeometry(
            self.rect()
        )

        self._popup_overlay.show()
        self._popup_overlay.raise_()

        if kind == "ai":
            self._populate_ai_popup()
        else:
            self._populate_stats_popup()

        self._popup.prepare_for_display()

        self._dashboard_blur = QGraphicsBlurEffect(self)
        self._dashboard_blur.setBlurRadius(13)
        self._dashboard_content.setGraphicsEffect(self._dashboard_blur)

        self._popup.show()
        self._popup.raise_()
        self._popup.setFocus()

        self._center_popup()

    def _close_popup(
        self,
    ) -> None:
        self._popup_kind = None

        self._popup.hide()
        self._popup_overlay.hide()

        if self._dashboard_blur is not None:
            self._dashboard_content.setGraphicsEffect(None)
            self._dashboard_blur.deleteLater()
            self._dashboard_blur = None

        self._dashboard_content.update()

    # ==================================================================
    # AI ENGINE POPUP
    # ==================================================================

    def _populate_ai_popup(self) -> None:
        self._popup.set_header(
            "AI Engine",
            "Live inference status and the active detection pipeline.",
            "cpu",
        )
        self._popup.clear_body()

        model = QFrame()
        model.setObjectName("popupSection")
        ml = QVBoxLayout(model)
        ml.setContentsMargins(24, 24, 24, 24)
        ml.setSpacing(16)

        title = QLabel("ACTIVE MODEL")
        title.setObjectName("popupSectionTitle")
        ml.addWidget(title)

        active = QLabel("Spontim 1.0")
        active.setObjectName("popupMetricValue")
        set_tone(active, "warn")
        ml.addWidget(active)

        desc = QLabel("Temporal fight detection · 16-frame sequence analysis")
        desc.setProperty("muted", True)
        ml.addWidget(desc)
        self._popup.body.addWidget(model)

        pipeline = QFrame()
        pipeline.setObjectName("popupSection")
        pl = QVBoxLayout(pipeline)
        pl.setContentsMargins(24, 24, 24, 24)
        pl.setSpacing(16)

        ptitle = QLabel("PIPELINE")
        ptitle.setObjectName("popupSectionTitle")
        pl.addWidget(ptitle)

        stages = (
            ("Person detection", "YOLO"),
            ("Tracking", "ByteTrack"),
            ("Pose analysis", "YOLO Pose"),
            ("Temporal classifier", "Spontim 1.0"),
            ("Event gate", "4-frame trigger / 6-frame release"),
        )
        for label_text, value_text in stages:
            self._popup_key_value(pl, label_text, value_text)
        self._popup.body.addWidget(pipeline)

        runtime = QFrame()
        runtime.setObjectName("popupSection")
        rl = QVBoxLayout(runtime)
        rl.setContentsMargins(18, 16, 18, 16)
        rl.setSpacing(8)

        rtitle = QLabel("RUNTIME")
        rtitle.setObjectName("popupSectionTitle")
        rl.addWidget(rtitle)

        status_text, status_tone = self._current_model_status()
        row = QHBoxLayout()
        key = QLabel("Engine status")
        key.setObjectName("popupKey")
        value = QLabel(status_text)
        value.setObjectName("popupValue")
        set_tone(value, status_tone)
        row.addWidget(key)
        row.addStretch(1)
        row.addWidget(value)
        rl.addLayout(row)

        settings = self._settings
        self._popup_key_value(
            rl,
            "Confidence threshold",
            f"{settings.confidence_threshold:.0%}" if settings else "—",
        )
        self._popup_key_value(
            rl,
            "Compute device",
            self._device_text or (settings.device.upper() if settings else "—"),
        )
        self._popup_key_value(
            rl,
            "AI monitoring",
            "Enabled" if settings and settings.detection_enabled else "Disabled",
        )
        self._popup.body.addWidget(runtime)
        self._popup.body.addStretch(1)

    def _current_model_status(self) -> tuple[str, str]:
        if self._settings is None:
            return "Waiting", "warn"

        required = ("detector", "pose", "fight")
        loaded = sum(
            self._runtime_loaded.get(key) is True
            for key in required
        )

        if loaded == len(required):
            return "ACTIVE", "good"
        if loaded > 0:
            return "PARTIAL", "warn"
        if self._runtime_loaded:
            return "NOT READY", "bad"
        return "READY", "good"

    # ==================================================================
    # SYSTEM STATS POPUP
    # ==================================================================

    def _populate_stats_popup(
        self,
    ) -> None:
        self._popup.set_header(
            "System Stats",
            "Current camera, incident, and alert activity.",
            "server",
        )

        self._popup.clear_body()

        # --------------------------------------------------------------
        # Four metric cards
        # --------------------------------------------------------------

        grid = QGridLayout()
        grid.setSpacing(10)

        online_tile, online_value = (
            self._stat_tile(
                "video",
                "good",
                "Cameras Online",
            )
        )

        offline_tile, offline_value = (
            self._stat_tile(
                "video-off",
                "muted",
                "Cameras Offline",
            )
        )

        incident_tile, incident_value = (
            self._stat_tile(
                "file-warning",
                "warn",
                "Open Incidents",
            )
        )

        alert_tile, alert_value = (
            self._stat_tile(
                "shield-alert",
                "bad",
                "Active Alerts",
            )
        )

        online_value.setText(
            self.online_value.text()
        )

        offline_value.setText(
            self.offline_value.text()
        )

        incident_value.setText(
            self.incident_value.text()
        )

        alert_value.setText(
            self.alert_value.text()
        )

        grid.addWidget(
            online_tile,
            0,
            0,
        )

        grid.addWidget(
            offline_tile,
            0,
            1,
        )

        grid.addWidget(
            incident_tile,
            1,
            0,
        )

        grid.addWidget(
            alert_tile,
            1,
            1,
        )

        self._popup.body.addLayout(
            grid
        )

        # --------------------------------------------------------------
        # Camera network section
        # --------------------------------------------------------------

        section = QFrame()
        section.setObjectName(
            "popupSection"
        )

        section_layout = QVBoxLayout(
            section
        )

        section_layout.setContentsMargins(
            18,
            15,
            18,
            15,
        )

        section_layout.setSpacing(
            8
        )

        title = QLabel(
            "Camera Network"
        )

        title.setObjectName(
            "popupSectionTitle"
        )

        section_layout.addWidget(
            title
        )

        total = len(
            self._cameras
        )

        online = int(
            self.online_value.text()
            or "0"
        )

        offline = max(
            0,
            total - online,
        )

        self._popup_key_value(
            section_layout,
            "Configured cameras",
            str(total),
        )

        self._popup_key_value(
            section_layout,
            "Live cameras",
            str(online),
        )

        self._popup_key_value(
            section_layout,
            "Offline cameras",
            str(offline),
        )

        self._popup.body.addWidget(
            section
        )

        # --------------------------------------------------------------
        # System activity section
        # --------------------------------------------------------------

        activity = QFrame()
        activity.setObjectName(
            "popupSection"
        )

        activity_layout = QVBoxLayout(
            activity
        )

        activity_layout.setContentsMargins(
            18,
            15,
            18,
            15,
        )

        activity_layout.setSpacing(
            8
        )

        title = QLabel(
            "System Activity"
        )

        title.setObjectName(
            "popupSectionTitle"
        )

        activity_layout.addWidget(
            title
        )

        self._popup_key_value(
            activity_layout,
            "Open incidents",
            self.incident_value.text(),
        )

        self._popup_key_value(
            activity_layout,
            "Active alerts",
            self.alert_value.text(),
        )

        monitoring = QLabel(
            "Monitoring"
            if online > 0
            else "Waiting for cameras"
        )

        monitoring.setObjectName(
            "popupValue"
        )

        set_tone(
            monitoring,
            "good"
            if online > 0
            else "warn",
        )

        row = QHBoxLayout()

        label = QLabel(
            "Monitoring state"
        )

        label.setObjectName(
            "popupKey"
        )

        row.addWidget(
            label
        )

        row.addStretch(1)

        row.addWidget(
            monitoring
        )

        activity_layout.addLayout(
            row
        )

        self._popup.body.addWidget(
            activity
        )

        self._popup.body.addStretch(1)

        # Reset to the top whenever System Stats opens.
        self._popup.scroll.verticalScrollBar().setValue(
            0
        )

    # ==================================================================
    # POPUP HELPERS
    # ==================================================================

    @staticmethod
    def _popup_key_value(
        layout: QVBoxLayout,
        key: str,
        value_text: str,
    ) -> None:

        row = QHBoxLayout()

        label = QLabel(
            key
        )

        label.setObjectName(
            "popupKey"
        )

        value = QLabel(
            value_text
        )

        value.setObjectName(
            "popupValue"
        )

        row.addWidget(
            label
        )

        row.addStretch(1)

        row.addWidget(
            value
        )

        layout.addLayout(
            row
        )

    @staticmethod
    def _stat_tile(
        icon: str,
        tone: str,
        caption: str,
    ) -> tuple[QFrame, QLabel]:

        tile = QFrame()
        tile.setObjectName(
            "popupMetric"
        )

        box = QVBoxLayout(
            tile
        )

        box.setContentsMargins(
            14,
            12,
            14,
            12,
        )

        box.setSpacing(
            3
        )

        box.addWidget(
            IconLabel(
                icon,
                19,
                tone,
            ),
            0,
            Qt.AlignmentFlag.AlignLeft,
        )

        value = QLabel("0")

        value.setObjectName(
            "popupMetricValue"
        )

        label = QLabel(
            caption
        )

        label.setObjectName(
            "popupMetricCaption"
        )

        label.setProperty(
            "muted",
            True,
        )

        box.addWidget(
            value
        )

        box.addWidget(
            label
        )

        return (
            tile,
            value,
        )

    # ==================================================================
    # CAMERA GRID
    # ==================================================================

    def sync_cameras(
        self,
        cameras: list[CameraConfig],
    ) -> None:

        new_ids = {
            camera.camera_id
            for camera in cameras
        }

        for camera_id in (
            set(self._tiles)
            - new_ids
        ):

            tile = self._tiles.pop(
                camera_id
            )

            if self._camera_grid is not None:
                self._camera_grid.removeWidget(
                    tile
                )

            tile.deleteLater()

            self._stats.pop(
                camera_id,
                None,
            )

            self._ai_states.pop(
                camera_id,
                None,
            )

            self._model_statuses.pop(
                camera_id,
                None,
            )

        self._cameras = {
            camera.camera_id: camera
            for camera in cameras
        }

        for camera in cameras:

            tile = self._tiles.get(
                camera.camera_id
            )

            if tile is None:

                tile = CameraPreview(
                    camera
                )

                tile.selected.connect(
                    self.camera_selected.emit
                )

                self._tiles[
                    camera.camera_id
                ] = tile

            else:
                tile.set_camera(
                    camera
                )

            self._update_tile(
                camera.camera_id
            )

        if self._camera_grid is None:
            return

        while self._camera_grid.count():

            item = self._camera_grid.takeAt(
                0
            )

            widget = item.widget()

            if widget is not None:

                if (
                    widget
                    is self._empty_label
                ):

                    widget.deleteLater()

                    self._empty_label = None

                else:
                    widget.setParent(
                        None
                    )

        for index, camera in enumerate(
            cameras
        ):

            self._camera_grid.addWidget(
                self._tiles[
                    camera.camera_id
                ],
                index // 2,
                index % 2,
            )

        count = len(
            cameras
        )

        self.camera_count_pill.setText(
            f"{count} camera"
            f"{'' if count == 1 else 's'}"
        )

        if not cameras:

            self._empty_label = QLabel(
                "No cameras configured. Add an external USB, RTSP, "
                "HTTP/MJPEG, or IP camera from the Cameras page."
            )

            self._empty_label.setWordWrap(
                True
            )

            self._empty_label.setAlignment(
                Qt.AlignmentFlag.AlignCenter
            )

            self._empty_label.setProperty(
                "muted",
                True,
            )

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

        self._stats[
            camera_id
        ] = stats

        self._update_tile(
            camera_id
        )

    def update_frame(
        self,
        camera_id: str,
        image,
        state: str,
        confidence: float | None,
    ) -> None:

        if camera_id not in self._tiles:
            return

        self._ai_states[
            camera_id
        ] = (
            state,
            confidence,
        )

        self._tiles[
            camera_id
        ].set_frame(
            QPixmap.fromImage(
                image
            )
        )

    # ==================================================================
    # MODEL STATUS
    # ==================================================================

    def update_model_status(
        self,
        camera_id: str,
        component: str,
        message: str,
    ) -> None:

        self._model_statuses.setdefault(
            camera_id,
            {},
        )[component] = message

        if component in {
            "detector",
            "pose",
            "fight",
        }:

            self._runtime_loaded[
                component
            ] = message.upper().startswith(
                "READY"
            )

            self._runtime_messages[
                component
            ] = message

        elif component == "device":

            self._device_text = message

        self._refresh_engine()

    def update_settings(
        self,
        confidence_threshold: float,
        detection_enabled: bool,
    ) -> None:
        # Detailed configuration is shown only inside the AI Engine popup.
        # The dashboard card stays intentionally minimal.
        return

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
            return

        self._set_value("violence_model", "Spontim 1.0", "good", "Active production fight-detection engine")
        self._set_value("device", self._device_text or settings.device.upper())

        status_text, status_tone = self._current_model_status()
        self._set_value("status", status_text, status_tone)

    def _set_value(
        self,
        key: str,
        text: str,
        tone: str = "",
        tooltip: str = "",
    ) -> None:

        label = self.engine_values[
            key
        ]

        label.setText(
            text
        )

        label.setToolTip(
            tooltip
        )

        set_tone(
            label,
            tone,
        )

    # ==================================================================
    # SUMMARY / NOTIFICATIONS
    # ==================================================================

    def refresh_summary(
        self,
    ) -> None:

        online = sum(
            self._stats.get(
                camera_id,
                CameraStats(),
            ).status == "LIVE"
            for camera_id in self._cameras
        )

        self.online_value.setText(
            str(online)
        )

        self.offline_value.setText(
            str(max(0, len(self._cameras) - online))
        )

        self.incident_value.setText(
            str(
                self.repository.open_incident_count()
            )
        )

        self.alert_value.setText(
            str(
                self.repository.active_alert_count()
            )
        )

        self._show_notifications(
            self.repository.list_notifications(
                8
            )
        )

        # Keep the currently-open stats popup current.
        if (
            self._popup.isVisible()
            and self._popup_kind == "stats"
        ):
            self._populate_stats_popup()
            self._popup.prepare_for_display()
            self._center_popup()

    def _show_notifications(
        self,
        rows: list[dict],
    ) -> None:

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

        layout = (
            self._notification_layout
        )

        while layout.count() > 1:

            item = layout.takeAt(
                0
            )

            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        if not rows:

            empty = QLabel(
                "No notifications yet."
            )

            empty.setProperty(
                "muted",
                True,
            )

            layout.insertWidget(
                0,
                empty,
            )

            return

        for index, row in enumerate(
            rows
        ):

            layout.insertWidget(
                index,
                self._notification_row(
                    row
                ),
            )

    @staticmethod
    def _notification_row(
        row: dict,
    ) -> QWidget:

        widget = QWidget()

        outer = QHBoxLayout(
            widget
        )

        outer.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        outer.setSpacing(
            10
        )

        dot = QLabel(
            "●"
        )

        tone = NOTIFICATION_TONES.get(
            row.get(
                "kind",
                "",
            ),
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
        text.setSpacing(
            2
        )

        message = QLabel(
            row["message"]
        )

        message.setWordWrap(
            True
        )

        stamp = QLabel(
            row["created_at"][11:19]
        )

        stamp.setProperty(
            "muted",
            True,
        )

        stamp.setStyleSheet(
            "font-size: 8pt;"
        )

        text.addWidget(
            message
        )

        text.addWidget(
            stamp
        )

        outer.addLayout(
            text,
            1,
        )

        return widget

    # ==================================================================
    # CAMERA TILE
    # ==================================================================

    def _update_tile(
        self,
        camera_id: str,
    ) -> None:

        camera = self._cameras.get(
            camera_id
        )

        tile = self._tiles.get(
            camera_id
        )

        if not camera or not tile:
            return

        stats = self._stats.get(
            camera_id,
            CameraStats(),
        )

        tile.set_status(
            stats,
            camera.ai_enabled,
        )