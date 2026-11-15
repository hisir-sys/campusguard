"""One-time notice and choice before this PC sends anything to the CampusGuard website account."""

from __future__ import annotations

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from campusguard import auth_config
from campusguard.ui.common import apply_theme
from campusguard.ui.theme import get_palette, rgba

SENT = (
    "This PC's name and the app version",
    "How many cameras you have, and how many are online",
    "For each incident: the camera name, time, label, confidence, severity and status",
    "Whether a clip exists on this PC",
)
NEVER_SENT = "Video, images, file locations, or anyone's face or identity. Clips stay on this PC."


class SyncConsentDialog(QDialog):
    """Asks once. ``choice`` is "on" only after the user presses Turn on sync; everything
    else, including closing the window, is "off", because consent must be an explicit yes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.choice = "off"
        self.setObjectName("syncConsent")
        self.setWindowTitle("CampusGuard — Account sync")
        self.setModal(True)
        self.setFixedWidth(500)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 30, 32, 24)
        root.setSpacing(0)

        title = QLabel("Show this PC on your CampusGuard account?")
        title.setObjectName("syncTitle")
        title.setWordWrap(True)
        root.addWidget(title)
        root.addSpacing(10)
        intro = QLabel(
            "CampusGuard can send a small summary to your website account, so you can check on "
            "your campus from anywhere. It is optional, and nothing is sent until you choose."
        )
        intro.setObjectName("syncBody")
        intro.setWordWrap(True)
        root.addWidget(intro)
        root.addSpacing(18)

        root.addWidget(self._heading("What is sent"))
        root.addSpacing(8)
        for line in SENT:
            root.addLayout(self._bullet(line))
            root.addSpacing(6)
        root.addSpacing(10)
        root.addWidget(self._heading("What is never sent"))
        root.addSpacing(8)
        never = QLabel(NEVER_SENT)
        never.setObjectName("syncBody")
        never.setWordWrap(True)
        root.addWidget(never)
        root.addSpacing(18)

        divider = QFrame()
        divider.setObjectName("syncDivider")
        divider.setFixedHeight(1)
        root.addWidget(divider)
        root.addSpacing(12)
        note = QLabel(
            "You can change this at any time in Settings, under Storage. Turning it off stops anything "
            "new from being sent; the Privacy Policy explains how to remove what was already sent."
        )
        note.setObjectName("syncNote")
        note.setWordWrap(True)
        root.addWidget(note)
        root.addSpacing(18)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.policy_link = QPushButton("Privacy Policy ↗")
        self.policy_link.setObjectName("syncLink")
        self.policy_link.setFlat(True)
        self.policy_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.policy_link.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(auth_config.WEBSITE_URL + "/privacy"))
        )
        buttons.addWidget(self.policy_link)
        buttons.addStretch(1)
        self.decline_button = QPushButton("Not now")
        self.decline_button.setMinimumHeight(40)
        self.decline_button.clicked.connect(self._decline)
        buttons.addWidget(self.decline_button)
        self.accept_button = QPushButton("Turn on sync")
        self.accept_button.setProperty("primary", True)
        self.accept_button.setMinimumHeight(40)
        self.accept_button.setDefault(False)  # Enter must not be an accidental yes
        self.accept_button.setAutoDefault(False)
        self.accept_button.clicked.connect(self._accept)
        buttons.addWidget(self.accept_button)
        root.addLayout(buttons)
        self.decline_button.setDefault(True)

        apply_theme(self, get_palette().name)
        self._style()
        self.adjustSize()

    @staticmethod
    def _heading(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("syncHeading")
        return label

    @staticmethod
    def _bullet(text: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        dot = QFrame()
        dot.setObjectName("syncDot")
        dot.setFixedSize(6, 6)
        slot = QWidget()
        slot.setFixedSize(6, 20)
        QVBoxLayout(slot).setContentsMargins(0, 7, 0, 0)
        slot.layout().addWidget(dot)
        row.addWidget(slot, 0, Qt.AlignmentFlag.AlignTop)
        label = QLabel(text)
        label.setObjectName("syncBody")
        label.setWordWrap(True)
        row.addWidget(label, 1)
        return row

    def _style(self) -> None:
        pal = get_palette()
        self.setStyleSheet(
            self.styleSheet()
            + f"""
            QDialog#syncConsent {{ background: {pal.bg1}; border: none; border-radius: 0; }}
            QLabel {{ background: transparent; }}
            QLabel#syncTitle {{ font-family: 'Outfit', 'Inter'; font-size: 17pt; font-weight: 600; color: {pal.text}; }}
            QLabel#syncHeading {{ color: {pal.muted}; font-size: 9pt; font-weight: 600; }}
            QLabel#syncBody {{ color: {pal.text}; font-size: 10pt; }}
            QLabel#syncNote {{ color: {pal.muted}; font-size: 9pt; }}
            QFrame#syncDot {{ background: {pal.lens}; border: none; border-radius: 3px; }}
            QFrame#syncDivider {{ background: {rgba(pal.line, 22)}; border: none; }}
            QPushButton#syncLink {{ background: transparent; border: none; color: {pal.text_dim}; padding: 4px 0; }}
            QPushButton#syncLink:hover {{ color: {pal.text}; }}
            """
        )

    def _accept(self) -> None:
        self.choice = "on"
        self.accept()

    def _decline(self) -> None:
        self.choice = "off"
        self.reject()
