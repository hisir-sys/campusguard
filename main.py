from __future__ import annotations

import sys

from campusguard.updater import handle_update_arguments, maybe_update
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget

from campusguard.ui.thinking_orb import ThinkingOrb


class StartupWindow(QWidget):
    """Instant lightweight startup surface shown before the full UI is built."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CampusGuard")
        self.setFixedSize(360, 360)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        panel = QFrame(self)
        panel.setGeometry(0, 0, 360, 360)
        panel.setStyleSheet(
            """
            QFrame {
                background: #0C1116;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 28px;
            }
            """
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        orb = ThinkingOrb(size=154)
        orb.setAccessibleName("CampusGuard startup animation")
        layout.addWidget(orb, 0, Qt.AlignmentFlag.AlignCenter)
        self.orb = orb

    def closeEvent(self, event) -> None:
        self.orb.stop()
        super().closeEvent(event)


def main() -> int:
    update_result = handle_update_arguments(sys.argv)
    if update_result is not None:
        return update_result

    if getattr(sys, "frozen", False) and maybe_update():
        return 0

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
