from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from campusguard.ui.theme import get_palette, rgba


class UpdateDialog(QDialog):
    """Start-up popup: 'Update now' installs, 'Not now' dismisses until the next launch."""

    update_requested = Signal()

    def __init__(self, version: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("updateDialog")
        self.setWindowTitle("CampusGuard update")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.version = version
        p = get_palette()
        self.setStyleSheet(
            f"""
            QDialog#updateDialog {{ background: {p.popup}; border: 1px solid {rgba(p.accent, 90)}; border-radius: 14px; }}
            QLabel#updateTitle {{ color: {p.text}; font-size: 18pt; font-weight: 700; }}
            QLabel#updateBody {{ color: {p.text_dim}; }}
            QPushButton#updateNow {{ background: {p.accent}; color: #0A0D08; border: none; border-radius: 9px; padding: 10px 22px; font-weight: 700; }}
            QPushButton#updateNow:hover {{ background: {p.accent_hover}; }}
            QPushButton#updateNow:disabled {{ background: {rgba(p.accent, 90)}; }}
            QPushButton#updateLater {{ background: transparent; color: {p.text}; border: 1px solid {rgba(p.text, 60)}; border-radius: 9px; padding: 10px 22px; }}
            QPushButton#updateLater:hover {{ border-color: {p.accent}; }}
            QProgressBar {{ background: {rgba(p.text, 25)}; border: none; border-radius: 3px; max-height: 6px; }}
            QProgressBar::chunk {{ background: {p.accent}; border-radius: 3px; }}
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(12)
        title = QLabel("A new CampusGuard update is available")
        title.setObjectName("updateTitle")
        title.setWordWrap(True)
        self.body = QLabel(
            f"Version {version} is ready to install.\n\n"
            "Choose “Update now” and CampusGuard will download it, install it and reopen by itself."
        )
        self.body.setObjectName("updateBody")
        self.body.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.later_button = QPushButton("Not now")
        self.later_button.setObjectName("updateLater")
        self.now_button = QPushButton("Update now")
        self.now_button.setObjectName("updateNow")
        self.now_button.setDefault(True)
        buttons.addWidget(self.later_button)
        buttons.addWidget(self.now_button)
        layout.addWidget(title)
        layout.addWidget(self.body)
        layout.addWidget(self.progress)
        layout.addLayout(buttons)
        self.later_button.clicked.connect(self.reject)
        self.now_button.clicked.connect(self.update_requested)

    def show_downloading(self) -> None:
        self.body.setText("Downloading and verifying the update… CampusGuard will close and reopen when it is installed.")
        self.progress.show()
        self.now_button.setEnabled(False)
        self.later_button.setEnabled(False)

    def show_failed(self) -> None:
        self.body.setText("The update could not be downloaded or verified. Please check the internet connection and try again.")
        self.progress.hide()
        self.now_button.setText("Try again")
        self.now_button.setEnabled(True)
        self.later_button.setEnabled(True)
