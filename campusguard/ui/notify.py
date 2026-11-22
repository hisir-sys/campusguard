# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
"""v3 toasts: small glass pills that slide up in the bottom-right corner, with an optional Undo."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QTimer, QVariantAnimation, Qt
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget, QFrame

from campusguard.ui.theme import get_palette, rgba

MAX_TOASTS = 4
MARGIN = 16


class Toast(QFrame):
    def __init__(self, parent: QWidget, message: str, undo=None, tone: str = "", on_gone=None) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._on_gone = on_gone
        self._gone = False
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 10, 12 if undo else 16, 10)
        row.setSpacing(12)
        self._dot: QLabel | None = None
        if tone:
            self._dot = QLabel()
            self._dot.setObjectName("toastDot")
            self._dot.setProperty("tone", tone)
            self._dot.setFixedSize(8, 8)
            row.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self.label = QLabel(message)
        self.label.setObjectName("toastText")
        self.restyle()
        self.label.ensurePolished()
        self._fit_label(message)
        row.setSizeConstraint(QHBoxLayout.SizeConstraint.SetFixedSize)
        row.addWidget(self.label, 1)
        if undo is not None:
            button = QPushButton("Undo")
            button.setObjectName("toastUndo")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedHeight(28)
            button.clicked.connect(lambda: (undo(), self.close_now()))
            row.addWidget(button)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._slide = QVariantAnimation(self)
        self._slide.setDuration(450)
        self._slide.setEasingCurve(QEasingCurve.Type.OutBack)
        self._slide.setStartValue(0.0)
        self._slide.setEndValue(1.0)
        self._slide.valueChanged.connect(self._on_slide)
        self._lifetime = QTimer(self)
        self._lifetime.setSingleShot(True)
        self._lifetime.timeout.connect(self.close_now)

    def _fit_label(self, message: str) -> None:
        """Long messages wrap at 340px; short ones stay on one line."""
        wrap = self.label.fontMetrics().horizontalAdvance(message) > 340
        self.label.setWordWrap(wrap)
        if wrap:
            self.label.setFixedSize(340, self.label.heightForWidth(340))
        else:
            self.label.setMinimumSize(0, 0)
            self.label.setMaximumSize(16777215, 16777215)
            self.label.adjustSize()

    def update_message(self, message: str, tone: str = "") -> None:
        """Replace the text of a toast that is already on screen (no second toast)."""
        self.label.setText(message)
        self._fit_label(message)
        if self._dot is not None:
            self._dot.setProperty("tone", tone)
            self._dot.style().unpolish(self._dot)
            self._dot.style().polish(self._dot)
        self.adjustSize()

    def keep_for(self, ms: int) -> None:
        """(Re)start the countdown after which the toast closes itself."""
        self._lifetime.start(ms)

    def restyle(self) -> None:
        p = get_palette()
        self.setStyleSheet(
            f"""
            QFrame#toast {{ background: {rgba(p.glass, 242)}; border: 1px solid {rgba(p.text, 36)}; border-radius: 18px; }}
            QLabel#toastText {{ color: {p.text}; font-weight: 500; background: transparent; }}
            QLabel#toastDot {{ background: {p.muted}; border-radius: 4px; }}
            QLabel#toastDot[tone="bad"] {{ background: {p.bad}; }}
            QLabel#toastDot[tone="good"] {{ background: {p.good}; }}
            QPushButton#toastUndo {{ background: transparent; color: {p.text}; border: 1px solid {rgba(p.text, 50)};
                border-radius: 14px; padding: 0 14px; font-weight: 500; }}
            QPushButton#toastUndo:hover {{ background: {rgba(p.text, 26)}; }}
            """
        )

    def _on_slide(self, value) -> None:
        self._effect.setOpacity(min(1.0, float(value) * 1.6))
        self.update()

    def start(self) -> None:
        self._slide.start()

    def close_now(self) -> None:
        if self._gone:
            return
        self._gone = True
        self._lifetime.stop()
        self._slide.stop()
        self.hide()
        self.setParent(None)
        if self._on_gone is not None:
            self._on_gone(self)
        self.deleteLater()


class ToastStack(QWidget):
    """Sits above the page content; only as big as its toasts so it never blocks clicks."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._toasts: list[Toast] = []
        self._keys: dict[Toast, str] = {}
        self.hide()

    def show_toast(self, message: str, undo=None, tone: str = "", ms: int = 4000, key: str | None = None) -> Toast:
        """Show a toast. The same `key` (or, without one, the same text) never stacks: the toast that is
        already on screen is updated and kept a little longer, so repeats don't pile up."""
        if undo is not None:
            ms = max(ms, 6000)
        identity = key if key is not None else (message if undo is None else None)
        if identity is not None:
            for existing in self._toasts:
                if self._keys.get(existing) == identity:
                    existing.update_message(message, tone)
                    existing.keep_for(ms)
                    self._reposition()
                    return existing
        while len(self._toasts) >= MAX_TOASTS:
            self._toasts[0].close_now()
        toast = Toast(self, message, undo, tone, self._forget)
        self._toasts.append(toast)
        if identity is not None:
            self._keys[toast] = identity
        self._layout.addWidget(toast, 0, Qt.AlignmentFlag.AlignRight)
        toast.keep_for(ms)
        self.show()
        self._reposition()
        self.raise_()
        toast.show()
        toast.start()
        return toast

    def _forget(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        self._keys.pop(toast, None)
        self._layout.removeWidget(toast)
        if not self._toasts:
            self.hide()
        else:
            self._reposition()

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        sizes = [toast.sizeHint() for toast in self._toasts]
        width = max(size.width() for size in sizes)
        height = sum(size.height() for size in sizes) + self._layout.spacing() * (len(sizes) - 1)
        self.resize(width, height)
        self.move(max(MARGIN, parent.width() - width - MARGIN), max(MARGIN, parent.height() - height - MARGIN))

    def reposition(self) -> None:
        if self._toasts:
            self._reposition()
