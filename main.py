from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget

from campusguard.ui.thinking_orb import ThinkingOrb


class StartupWindow(QWidget):
    """Instant lightweight startup surface shown before the full UI is built."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CampusGuard")
        self.setFixedSize(460, 360)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        panel = QFrame(self)
        panel.setGeometry(0, 0, 460, 360)
        panel.setStyleSheet(
            """
            QFrame {
                background: #0C1116;
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 24px;
            }
            QLabel#brand {
                color: #F3F6FA;
                font-size: 19pt;
                font-weight: 700;
                background: transparent;
                border: none;
            }
            QLabel#status {
                color: #778391;
                font-size: 9pt;
                background: transparent;
                border: none;
            }
            QLabel#hint {
                color: #526FD6;
                font-size: 8pt;
                font-weight: 600;
                background: transparent;
                border: none;
            }
            """
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        orb = ThinkingOrb(size=112)
        orb.setToolTip("CampusGuard AI engine")
        layout.addWidget(orb, 0, Qt.AlignmentFlag.AlignCenter)

        brand = QLabel("CampusGuard")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand)

        status = QLabel("Initializing security operations")
        status.setObjectName("status")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(status)

        hint = QLabel("AI ENGINE  •  READYING")
        hint.setObjectName("hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        self.orb = orb

    def closeEvent(self, event) -> None:
        self.orb.stop()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("CampusGuard")
    app.setOrganizationName("CampusGuard")
    app.setStyle("Fusion")

    # Show a tiny, dependency-light surface first. The heavy MainWindow import
    # happens only after the event loop has painted this window, so the user
    # sees CampusGuard immediately instead of waiting on Python imports.
    startup = StartupWindow()
    startup.show()
    startup.raise_()
    startup.activateWindow()
    app.processEvents()

    def launch_main_window() -> None:
        from campusguard.ui.main_window import MainWindow

        window = MainWindow()
        window.show()
        startup.close()
        window.raise_()
        window.activateWindow()
        app._campusguard_window = window

    QTimer.singleShot(80, launch_main_window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
