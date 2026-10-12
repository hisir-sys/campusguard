from __future__ import annotations

import sys
import threading
from pathlib import Path

from campusguard.updater import handle_update_arguments, maybe_update
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon
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

    # Import the UI module away from the GUI thread. Its imports can pull in
    # OpenCV and other large dependencies; doing that on the GUI thread leaves
    # the startup surface frozen for minutes on some Windows installations.
    import_state = {"done": False, "module": None, "error": None}

    def import_main_window() -> None:
        try:
            from campusguard.ui import main_window
            import_state["module"] = main_window
        except Exception as error:
            import_state["error"] = error
        finally:
            import_state["done"] = True

    import_thread = threading.Thread(
        target=import_main_window,
        name="CampusGuard-UI-Import",
        daemon=True,
    )
    import_thread.start()

    launch_poll = QTimer()
    launch_poll.setInterval(100)

    def finish_launch() -> None:
        if not import_state["done"]:
            return
        launch_poll.stop()

        if import_state["error"] is not None:
            error = import_state["error"]
            startup.close()
            QMessageBox.critical(
                None,
                "CampusGuard could not start",
                f"The main interface failed to load.\n\n{type(error).__name__}: {error}",
            )
            app.exit(1)
            return

        try:
            window = import_state["module"].MainWindow()
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
                f"The main window failed to initialize.\n\n{type(error).__name__}: {error}",
            )
            app.exit(1)

    launch_poll.timeout.connect(finish_launch)
    launch_poll.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
