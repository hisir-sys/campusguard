from __future__ import annotations

from pathlib import Path
import time

from PySide6.QtCore import QEvent, QEasingCurve, QPropertyAnimation, QRect, Qt, Signal
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
    QSizePolicy,
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

        self._apply_overlay_palette()

    def _apply_overlay_palette(self) -> None:
        palette = get_palette()
        # Use a softer, palette-aware veil: the old fixed black layer made
        # the light theme look like a dark rectangle behind the popup.
        alpha = 72 if palette.name == "dark" else 30
        self.setStyleSheet(
            f"""
            QWidget#popupLayer {{
                background: {rgba("#000000" if palette.name == "dark" else "#344154", alpha)};
                border: none;
            }}
            """
        )

    def retint(self) -> None:
        self._apply_overlay_palette()

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
        self._geometry_animation = QPropertyAnimation(self, b"geometry", self)
        self._geometry_animation.setDuration(220)
        self._geometry_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Give operational popups enough room to read their metrics and details.
        # Final geometry is still capped by the available application window.
        self.setMinimumWidth(960)
        self.setMaximumWidth(1240)
        self.setMinimumHeight(520)
        self.setMaximumHeight(900)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )

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
        root.setContentsMargins(32, 30, 32, 30)
        root.setSpacing(17)

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
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
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

        self.body_widget = QWidget()

        self.body = QVBoxLayout(
            self.body_widget
        )
        self.body.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        self.body.setSpacing(12)

        self.body_scroll = QScrollArea()
        self.body_scroll.setObjectName("popupScroll")
        self.body_scroll.setWidgetResizable(True)
        self.body_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.body_scroll.setWidget(self.body_widget)
        self.body_scroll.setMinimumHeight(0)
        self.body_scroll.setMaximumHeight(760)
        root.addWidget(self.body_scroll, 1)

    def _apply_palette(self) -> None:
        palette = get_palette()

        self.setStyleSheet(
            f"""
            QFrame#glassPopup {{
                background: {rgba(palette.glass, 174 if palette.name == "dark" else 164)};
                color: {palette.text};
                border: 1px solid {rgba(palette.line, 54 if palette.name == "dark" else 76)};
                border-radius: 28px;
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
                background: {rgba(palette.veil, 38 if palette.name == "dark" else 84)};
                color: {palette.text};
                border: 1px solid {rgba(palette.line, min(255, int(palette.line_alpha * 1.5)))};
                border-radius: 19px;
            }}

            QFrame#popupMetric {{
                background: {rgba(palette.veil, 32 if palette.name == "dark" else 72)};
                color: {palette.text};
                border: 1px solid {rgba(palette.line, palette.line_alpha)};
                border-radius: 16px;
            }}

            QPushButton[modelChoice="true"] {{
                color: {palette.text};
                background: {rgba(palette.veil, 42 if palette.name == "dark" else 104)};
                border: 1px solid {rgba(palette.line, 34 if palette.name == "dark" else 58)};
                border-radius: 11px;
                padding: 7px 8px;
                text-align: center;
            }}

            QPushButton[modelChoice="true"]:hover {{
                background: {rgba(palette.veil, 62 if palette.name == "dark" else 142)};
                border-color: {rgba(palette.edge, 100)};
            }}

            QPushButton[modelChoice="true"]:checked {{
                background: {rgba(palette.edge, 35 if palette.name == "dark" else 32)};
                border-color: {rgba(palette.edge, 150)};
                font-weight: 700;
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

    def animate_in(self, target: QRect) -> None:
        # Restrained scale/settle motion; no flashy bounce.
        self._geometry_animation.stop()
        start = QRect(target)
        start.setWidth(max(240, int(target.width() * 0.965)))
        start.setHeight(max(220, int(target.height() * 0.965)))
        start.moveCenter(target.center())
        self.setGeometry(start)
        self.show()
        self._geometry_animation.setStartValue(start)
        self._geometry_animation.setEndValue(target)
        self._geometry_animation.start()

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

    def prepare_for_display(self, kind: str = "notifications") -> None:
        """Fit compact popups to their content; reserve scrolling for notifications."""
        self.body_scroll.verticalScrollBar().setValue(0)
        self.body_scroll.setMaximumHeight(690)
        self.body_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if kind == "notifications"
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.body_scroll.setMinimumHeight(0)



class DashboardPage(QWidget):
    camera_selected = Signal(str)
    model_switch_requested = Signal(str)
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
        self._offline_tiles: list[QFrame] = []

        self._runtime_loaded: dict[
            str,
            bool,
        ] = {}

        self._runtime_messages: dict[
            str,
            str,
        ] = {}
        self._session_started_at = time.monotonic()

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

        root.setContentsMargins(24, 16, 24, 112)
        root.setSpacing(14)

        # --------------------------------------------------------------
        # Operations overview
        #
        # A single three-column status strip keeps the most important
        # information visible at a glance. The camera wall sits underneath
        # as the main visual surface.
        # --------------------------------------------------------------
        main_row = QHBoxLayout()
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.setSpacing(18)

        self._engine_card = self._build_engine_card()
        self._stats_card = self._build_stats_card()
        self._notifications_card = self._build_notifications_card()
        self._network_card = self._build_network_card()

        self._engine_card.setMinimumHeight(170)
        self._engine_card.setMaximumHeight(170)
        self._stats_card.setMinimumHeight(170)
        self._stats_card.setMaximumHeight(170)
        self._notifications_card.setMinimumHeight(170)
        self._notifications_card.setMaximumHeight(170)

        main_row.addWidget(self._engine_card, 11)
        main_row.addWidget(self._stats_card, 11)
        main_row.addWidget(self._notifications_card, 15)
        root.addLayout(main_row, 0)

        self._network_card.setMinimumHeight(410)
        root.addWidget(self._network_card, 1)

        # Keep a dedicated bottom breathing space in the scrollable content.
        # This reserves clear canvas above the floating dock at the end of the
        # Live Network section while keeping every camera tile reachable.
        self.dashboard_scroll = QScrollArea()
        self.dashboard_scroll.setObjectName("dashboardWorkspaceScroll")
        self.dashboard_scroll.setWidgetResizable(True)
        self.dashboard_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.dashboard_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.dashboard_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.dashboard_scroll.viewport().setAutoFillBackground(False)
        self.dashboard_scroll.setWidget(self._dashboard_content)
        outer.addWidget(self.dashboard_scroll, 1)

        # ==============================================================
        # DASHBOARD BLUR
        #
        # Keep the dashboard unmodified during normal operation. The blur
        # effect is created only when a popup is actually opened.
        # ==============================================================
        self._dashboard_blur = None
        self._navigation_blurs: list[tuple[QWidget, QGraphicsBlurEffect]] = []

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
            220,
            available_height - (safe_margin * 2),
        )

        # Never allow the popup to become excessively tall.
        maximum_height = min(
            maximum_height,
            840,
        )

        self._popup.setMaximumHeight(
            maximum_height
        )

        self._popup.adjustSize()

        width = min(
            max(520, self.width() - 40),
            max(780, min(1040, self._popup.sizeHint().width())),
        )
        self._popup.setFixedWidth(width)
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
        frame.setMinimumHeight(170)
        frame.setMaximumHeight(170)
        frame.setCursor(Qt.CursorShape.PointingHandCursor)
        frame.installEventFilter(self)
        for child in frame.findChildren(QWidget):
            child.installEventFilter(self)

        self.engine_values = {}

        # Compact dashboard summary: only the three useful values remain.
        # Detailed model switching/configuration is inside the popup.
        active_model = QLabel("Spontim 1.0")
        active_model.setProperty("kvvalue", True)
        active_model.setStyleSheet(
            "font-size: 13pt; font-weight: 700; letter-spacing: -0.2px;"
        )
        layout.addWidget(active_model)
        self.engine_values["violence_model"] = active_model

        rows = (
            ("status", "Status"),
            ("device", "Compute"),
        )
        for key, text in rows:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(10)
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
        frame.setMinimumHeight(222)
        frame.setMaximumHeight(222)
        frame.setCursor(Qt.CursorShape.PointingHandCursor)
        frame.installEventFilter(self)
        for child in frame.findChildren(QWidget):
            child.installEventFilter(self)

        self.online_value = QLabel("0")
        self.online_value.setProperty("kvvalue", True)
        self.offline_value = QLabel("0")
        self.offline_value.setProperty("kvvalue", True)
        self.incident_value = QLabel("0")
        self.incident_value.setProperty("kvvalue", True)
        self.alert_value = QLabel("0")
        self.alert_value.setProperty("kvvalue", True)

        stats = (
            ("video", "muted", self.online_value, "Cameras"),
            ("file-warning", "muted", self.incident_value, "Open incidents"),
            ("shield-alert", "muted", self.alert_value, "Active alerts"),
        )

        grid = QGridLayout()
        grid.setContentsMargins(0, 2, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        for index, (icon, tone, value, label_text) in enumerate(stats):
            tile = QFrame()
            tile.setObjectName("dashboardStatTile")
            box = QVBoxLayout(tile)
            box.setContentsMargins(12, 11, 12, 10)
            box.setSpacing(3)

            top = QHBoxLayout()
            top.setContentsMargins(0, 0, 0, 0)
            top.addWidget(IconLabel(icon, 16, tone))
            top.addStretch(1)
            box.addLayout(top)

            box.addWidget(value)

            label = QLabel(label_text)
            label.setProperty("muted", True)
            label.setStyleSheet("font-size: 8.5pt;")
            box.addWidget(label)

            grid.addWidget(tile, 0, index)

        layout.addLayout(grid)

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

        view_all = QPushButton("See All")
        view_all.setProperty("link", True)
        view_all.setCursor(Qt.CursorShape.PointingHandCursor)
        view_all.clicked.connect(lambda _checked=False: self._open_popup("notifications"))

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

        frame.header_layout.addWidget(clear_notifications)
        frame.header_layout.addWidget(view_all)
        frame.header_layout.addWidget(view_alerts)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(
            QFrame.Shape.NoFrame
        )

        scroll.setMinimumHeight(150)
        scroll.setContentsMargins(0, 0, 0, 6)

        scroll.viewport().setAutoFillBackground(
            False
        )

        content = QWidget()

        self._notification_layout = QVBoxLayout(
            content
        )

        self._notification_layout.setContentsMargins(
            0,
            4,
            8,
            34,
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
        self.feed_scroll.setObjectName("liveNetworkScroll")
        self.feed_scroll.setWidgetResizable(True)
        self.feed_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.feed_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.feed_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.feed_scroll.viewport().setAutoFillBackground(False)

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
        self._camera_grid.setColumnStretch(0, 1)
        self._camera_grid.setColumnStretch(1, 1)

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

    def _blur_navigation(self, enabled: bool) -> None:
        self._clear_navigation_blur()
        if not enabled:
            return
        window = self.window()
        for name in ("top_bar", "bottom_bar"):
            widget = getattr(window, name, None)
            if isinstance(widget, QWidget):
                effect = QGraphicsBlurEffect(widget)
                effect.setBlurRadius(7)
                widget.setGraphicsEffect(effect)
                self._navigation_blurs.append((widget, effect))

    def _clear_navigation_blur(self) -> None:
        for widget, effect in self._navigation_blurs:
            if widget.graphicsEffect() is effect:
                widget.setGraphicsEffect(None)
            # setGraphicsEffect(None) may already destroy the effect;
            # do not schedule a second deletion of its Python wrapper.
        self._navigation_blurs.clear()
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
        elif kind == "stats":
            self._populate_stats_popup()
        else:
            self._populate_notifications_popup()

        self._popup.prepare_for_display(kind)

        # A restrained blur keeps the background legible and avoids the
        # heavy, dark-edged rectangle produced by a large blur radius.
        self._dashboard_blur = QGraphicsBlurEffect(self)
        self._dashboard_blur.setBlurRadius(9)
        self._dashboard_content.setGraphicsEffect(self._dashboard_blur)
        self._blur_navigation(True)

        self._center_popup()
        target = QRect(self._popup.geometry())
        self._popup.animate_in(target)
        self._popup.raise_()
        self._popup.setFocus()

    def _close_popup(
        self,
    ) -> None:
        self._popup_kind = None

        self._popup._geometry_animation.stop()
        self._popup.hide()
        self._popup_overlay.hide()

        if self._dashboard_blur is not None:
            if self._dashboard_content.graphicsEffect() is self._dashboard_blur:
                self._dashboard_content.setGraphicsEffect(None)
            # Clearing the effect transfers/destroys its Qt ownership.
            # Do not call deleteLater() on the wrapper afterwards.
            self._dashboard_blur = None

        # Always clear navigation blur even if the popup was already hidden.
        self._clear_navigation_blur()
        self._dashboard_content.update()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self._popup_kind is not None:
            self._close_popup()
            event.accept()
            return
        super().keyPressEvent(event)

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
        ml.setContentsMargins(18, 16, 18, 16)
        ml.setSpacing(10)

        title = QLabel("ACTIVE MODEL")
        title.setObjectName("popupSectionTitle")
        ml.addWidget(title)

        model_names = {"fdsc_mc3": "Spontim 1.0", "mc3": "CampusGuard MC3-18", "x3d": "X3D-M"}
        current_key = getattr(self._settings, "violence_model", "fdsc_mc3") if self._settings else "fdsc_mc3"

        # Horizontal choices use the popup width instead of stacking three
        # tall buttons, keeping the full AI overview visible without scrolling.
        choices = QHBoxLayout()
        choices.setContentsMargins(0, 0, 0, 0)
        choices.setSpacing(8)
        options = (
            ("Spontim 1.0", "fdsc_mc3"),
            ("CampusGuard MC3-18", "mc3"),
            ("X3D-M", "x3d"),
        )
        for label_text, key in options:
            choice = QPushButton(label_text)
            choice.setCheckable(True)
            choice.setChecked(key == current_key)
            choice.setCursor(Qt.CursorShape.PointingHandCursor)
            choice.setMinimumHeight(36)
            choice.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            choice.setProperty("modelChoice", True)
            choice.clicked.connect(
                lambda _checked=False, selected_key=key:
                self.model_switch_requested.emit(selected_key)
            )
            choices.addWidget(choice, 1)
        ml.addLayout(choices)

        desc = QLabel("Select the temporal classifier used by live camera workers.")
        desc.setProperty("muted", True)
        desc.setWordWrap(True)
        ml.addWidget(desc)
        self._popup.body.addWidget(model)

        pipeline = QFrame()
        pipeline.setObjectName("popupSection")
        pl = QVBoxLayout(pipeline)
        pl.setContentsMargins(18, 16, 18, 16)
        pl.setSpacing(8)

        ptitle = QLabel("PIPELINE")
        ptitle.setObjectName("popupSectionTitle")
        pl.addWidget(ptitle)

        stages = (
            ("Person detection", "YOLO"),
            ("Tracking", "ByteTrack"),
            ("Pose analysis", "YOLO Pose"),
            ("Temporal classifier", model_names.get(current_key, "Spontim 1.0")),
            ("Event gate", "4-frame trigger / 6-frame release"),
        )
        for label_text, value_text in stages:
            self._popup_key_value(pl, label_text, value_text)
        self._popup.body.addWidget(pipeline)

        runtime = QFrame()
        runtime.setObjectName("popupSection")
        rl = QVBoxLayout(runtime)
        rl.setContentsMargins(18, 14, 18, 14)
        rl.setSpacing(6)

        rtitle = QLabel("RUNTIME")
        rtitle.setObjectName("popupSectionTitle")
        rl.addWidget(rtitle)

        status_text, status_tone = self._current_model_status()
        if status_text == "PARTIAL" and any(stats.status == "LIVE" for stats in self._stats.values()):
            status_text = "PARTIAL / ONLINE"
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
        live_rates = [
            float(stats.fps)
            for camera_id, stats in self._stats.items()
            if camera_id in self._cameras and stats.status == "LIVE" and stats.fps is not None
        ]
        average_fps = sum(live_rates) / len(live_rates) if live_rates else None
        self._popup_key_value(
            rl,
            "Frame processing rate",
            f"{average_fps:.1f} FPS average" if average_fps is not None else "Waiting for live frames",
        )
        self._popup_key_value(
            rl,
            "Average inference latency",
            "Not reported by current runtime",
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
            "Live operational status, priority distribution, and session health.",
            "server",
        )
        self._popup.clear_body()

        online_count = int(self.online_value.text() or "0")
        offline_count = int(self.offline_value.text() or "0")
        incident_count = int(self.incident_value.text() or "0")
        alert_count = int(self.alert_value.text() or "0")
        total_cameras = online_count + offline_count

        # Count only currently active (unacknowledged) alerts by the severity
        # stored on their linked incident records.
        priority_counts = {"high": 0, "medium": 0, "low": 0}
        for alert in self.repository.list_alerts(1000):
            if alert.get("acknowledged"):
                continue
            severity = str(alert.get("severity", "")).strip().lower()
            if severity in priority_counts:
                priority_counts[severity] += 1

        uptime_seconds = max(0, int(time.monotonic() - self._session_started_at))
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_text = f"{hours}h {minutes:02d}m {seconds:02d}s" if hours else f"{minutes}m {seconds:02d}s"

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        metrics = (
            ("video", "Connected cameras", str(total_cameras)),
            ("activity", "Active / Offline streams", f"{online_count} Active / {offline_count} Offline"),
            ("file-warning", "Open incidents", str(incident_count)),
            ("shield-alert", "Active alerts", str(alert_count)),
        )
        for index, (icon, caption, value_text) in enumerate(metrics):
            tile, value = self._stat_tile(icon, "muted", caption)
            value.setText(value_text)
            value.setWordWrap(True)
            value.setMinimumHeight(34)
            grid.addWidget(tile, index // 2, index % 2)

        self._popup.body.addLayout(grid)

        state_box = QFrame()
        state_box.setObjectName("popupSection")
        state_layout = QVBoxLayout(state_box)
        state_layout.setContentsMargins(18, 14, 18, 14)
        state_layout.setSpacing(10)

        state_title = QLabel("ALERT PRIORITY BREAKDOWN")
        state_title.setObjectName("popupSectionTitle")
        state_layout.addWidget(state_title)

        priority_row = QHBoxLayout()
        priority_row.setSpacing(12)
        for priority, tone in (("High", "bad"), ("Medium", "warn"), ("Low", "good")):
            item = QFrame()
            item.setObjectName("popupMetric")
            item_layout = QVBoxLayout(item)
            item_layout.setContentsMargins(14, 10, 14, 10)
            item_layout.setSpacing(4)
            value = QLabel(str(priority_counts[priority.lower()]))
            value.setObjectName("popupMetricValue")
            set_tone(value, tone)
            caption = QLabel(f"{priority} priority")
            caption.setObjectName("popupMetricCaption")
            item_layout.addWidget(value)
            item_layout.addWidget(caption)
            priority_row.addWidget(item, 1)
        state_layout.addLayout(priority_row)
        self._popup.body.addWidget(state_box)

        details = QFrame()
        details.setObjectName("popupSection")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(18, 15, 18, 15)
        details_layout.setSpacing(10)

        details_title = QLabel("OPERATIONAL DETAILS")
        details_title.setObjectName("popupSectionTitle")
        details_layout.addWidget(details_title)

        current_model = getattr(self._settings, "violence_model", "fdsc_mc3") if self._settings else "fdsc_mc3"
        model_names = {
            "fdsc_mc3": "Spontim 1.0",
            "mc3": "CampusGuard MC3-18",
            "x3d": "X3D-M",
            "r3d": "R3D-18",
        }
        rows = (
            ("Total connected cameras", str(total_cameras)),
            ("Stream availability", f"{online_count} Active / {offline_count} Offline"),
            ("Active detection model", model_names.get(current_model, "Spontim 1.0")),
            ("Incident queue", f"{incident_count} open" if incident_count else "Clear"),
            ("System uptime (this session)", uptime_text),
        )
        for key_text, value_text in rows:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(14)

            key_label = QLabel(key_text)
            key_label.setObjectName("popupKey")
            value_label = QLabel(value_text)
            value_label.setObjectName("popupValue")
            value_label.setWordWrap(True)
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            row_layout.addWidget(key_label, 1)
            row_layout.addWidget(value_label, 2)
            details_layout.addWidget(row_widget)

        self._popup.body.addWidget(details)
        self._popup.body.addStretch(1)

    def _populate_notifications_popup(self) -> None:
        self._popup.set_header(
            "All Notifications",
            "Recent camera, incident, and alert activity.",
            "bell",
        )
        self._popup.clear_body()

        rows = self.repository.list_notifications(100)
        if not rows:
            empty = QLabel("No notifications yet.")
            empty.setObjectName("popupKey")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(90)
            self._popup.body.addWidget(empty)
            return

        for row in rows:
            item = QFrame()
            item.setObjectName("popupSection")
            layout = QHBoxLayout(item)
            layout.setContentsMargins(16, 12, 16, 12)
            layout.setSpacing(12)

            dot = QLabel("●")
            tone = NOTIFICATION_TONES.get(row.get("kind", ""), "")
            if tone:
                set_tone(dot, tone)
            else:
                dot.setProperty("muted", True)
            layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)

            column = QVBoxLayout()
            column.setSpacing(4)
            message = QLabel(str(row.get("message", "Notification")))
            message.setObjectName("popupValue")
            message.setWordWrap(True)
            column.addWidget(message)

            created = QLabel(str(row.get("created_at", "")))
            created.setObjectName("popupKey")
            created.setWordWrap(True)
            column.addWidget(created)
            layout.addLayout(column, 1)
            self._popup.body.addWidget(item)

        self._popup.body.addStretch(1)

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

                elif widget.objectName() == "offlineCameraTile":
                    widget.deleteLater()

                else:
                    widget.setParent(
                        None
                    )

        # Always render two equal panes in the default wall. A missing
        # source is shown as an OFFLINE pane only; it is not a fake camera
        # configuration and does not start any capture worker.
        display_widgets: list[QWidget] = [
            self._tiles[camera.camera_id] for camera in cameras
        ]

        if len(cameras) <= 2:
            while len(display_widgets) < 2:
                display_widgets.append(
                    self._build_offline_tile(len(display_widgets) + 1)
                )

        for index, widget in enumerate(display_widgets):
            self._camera_grid.addWidget(
                widget,
                index // 2,
                index % 2,
            )

        if len(cameras) <= 2:
            self.feed_scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            self.feed_content.setMinimumHeight(0)
        else:
            self.feed_scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            self.feed_content.setMinimumHeight(
                max(
                    self.feed_scroll.viewport().height(),
                    ((len(cameras) + 1) // 2) * 260,
                )
            )

        count = len(
            cameras
        )

        self.camera_count_pill.setText(
            f"{count} camera"
            f"{'' if count == 1 else 's'}"
        )

        # The two default panes are the empty state, so no third empty
        # message is inserted into the camera grid.

    def _build_offline_tile(self, slot: int) -> QFrame:
        tile = QFrame()
        tile.setProperty("card", True)
        tile.setObjectName("offlineCameraTile")
        tile.setMinimumHeight(238)

        surface = QLabel("OFFLINE")
        surface.setAlignment(Qt.AlignmentFlag.AlignCenter)
        surface.setProperty("videoSurface", True)
        surface.setStyleSheet(
            "border-radius: 14px; font-size: 10pt; font-weight: 700;"
        )

        name = QLabel(f"Camera {slot}", tile)
        name.setStyleSheet(
            "background: rgba(5, 9, 12, 190); color: white; "
            "border-radius: 9px; padding: 5px 9px; font-weight: 700;"
        )
        status = QLabel("OFFLINE", tile)
        status.setStyleSheet(
            "background: rgba(5, 9, 12, 190); color: white; "
            "border-radius: 9px; padding: 5px 9px; font-size: 8pt; font-weight: 700;"
        )

        outer = QVBoxLayout(tile)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(0)
        outer.addWidget(surface, 1)

        def position():
            rect = surface.geometry()
            name.adjustSize()
            status.adjustSize()
            y = rect.bottom() - max(name.height(), status.height()) - 10
            name.move(rect.left() + 12, max(rect.top() + 8, y))
            status.move(max(rect.left() + 12, rect.right() - status.width() - 12), max(rect.top() + 8, y))
            name.raise_()
            status.raise_()

        tile.resizeEvent = lambda event: (QFrame.resizeEvent(tile, event), position())
        return tile


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
            ),
            state,
            confidence,
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

            # Surface failures directly on the live camera tile instead of
            # leaving the operator with a raw video and no explanation.
            tile = self._tiles.get(camera_id)
            if tile is not None:
                tile.set_model_status(message)

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

        model_names = {"fdsc_mc3": "Spontim 1.0", "mc3": "CampusGuard MC3-18", "x3d": "X3D-M"}
        model_key = getattr(settings, "violence_model", "fdsc_mc3")
        model_name = model_names.get(model_key, "Spontim 1.0")
        self._set_value("violence_model", model_name, "good", "Active production fight-detection engine")
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
            self._popup.prepare_for_display("stats")
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

        widget = QFrame()
        widget.setObjectName("notificationRow")

        outer = QHBoxLayout(
            widget
        )

        outer.setContentsMargins(
            0,
            7,
            0,
            7,
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