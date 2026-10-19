from __future__ import annotations

import sys
from pathlib import Path

from campusguard.updater import handle_update_arguments, maybe_update
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QMessageBox, QVBoxLayout, QWidget

from campusguard.ui.thinking_orb import ThinkingOrb


class StartupWindow(QWidget):
    """Instant lightweight startup surface shown before the full UI is built."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CampusGuard")
        self.setWindowIcon(QApplication.windowIcon())
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
                background: #090C0A;
                border: 1px solid rgba(200,255,82,0.16);
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
    asset_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    app_icon = QIcon(str(asset_root / "assets" / "campusguard-eye.svg"))
    app.setWindowIcon(app_icon)

    # Show a tiny, dependency-light surface first. The heavy MainWindow import
    # happens only after the event loop has painted this window, so the user
    # sees CampusGuard immediately instead of waiting on Python imports.
    startup = StartupWindow()
    startup.show()
    startup.raise_()
    startup.activateWindow()
    app.processEvents()

    # Import Qt UI modules on the GUI thread. Importing PySide6 widget modules
    # from a background Python thread can leave some Windows/Python builds
    # stuck on the animated splash indefinitely. The splash is painted first;
    # the import is then performed synchronously and any failure is shown.
    def finish_launch() -> None:
        try:
            from campusguard.ui.main_window import MainWindow

            window = MainWindow()
            window.show()
            startup.close()
            window.raise_()
            window.activateWindow()
            app._campusguard_window = window
        except Exception as error:
            startup.close()
            QMessageBox.critical(
                None,
                "CampusGuard could not start",
                f"The main interface failed to load.\n\n{type(error).__name__}: {error}",
            )
            app.exit(1)

    QTimer.singleShot(0, finish_launch)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
