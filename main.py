from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from campusguard.ui.thinking_orb import ThinkingOrb


def _asset_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _load_brand_fonts() -> None:
    """Register the bundled website fonts (DM Sans, Manrope) so the UI does not
    fall back to Segoe UI on machines that do not have them installed."""
    for font_file in sorted((_asset_root() / "assets" / "fonts").glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(font_file))


class StartupWindow(QWidget):
    """Instant lightweight start-up surface: the CampusGuard orb and a status line."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CampusGuard")
        self.setWindowIcon(QApplication.windowIcon())
        self.setFixedSize(380, 420)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        panel = QFrame(self)
        panel.setObjectName("startupPanel")
        panel.setGeometry(0, 0, 380, 420)
        panel.setStyleSheet(
            """
            QFrame#startupPanel {
                background: #090C0A;
                border: 1px solid rgba(200,255,82,0.18);
                border-radius: 28px;
            }
            QLabel { background: transparent; border: none; }
            """
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 36, 24, 30)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.orb = ThinkingOrb(size=210)
        self.orb.setAccessibleName("CampusGuard start-up animation")
        layout.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(18)

        brand = QLabel('CAMPUS<span style="color:#C8FF52;">GUARD</span>')
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setStyleSheet(
            "color: #F7F8F4; font-family: 'Manrope', 'DM Sans', 'Segoe UI'; "
            "font-size: 17pt; font-weight: 800; letter-spacing: 4px;"
        )
        layout.addWidget(brand)
        layout.addSpacing(8)

        self.status = QLabel("Starting…")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet("color: #8D958B; font-size: 10pt; letter-spacing: 1px;")
        layout.addWidget(self.status)

        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            self.move(avail.x() + (avail.width() - self.width()) // 2, avail.y() + (avail.height() - self.height()) // 2)

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def showEvent(self, event) -> None:
        self.orb.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self.orb.stop()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self.orb.stop()
        super().closeEvent(event)


class AppController:
    """Start-up sequence: splash -> sign in -> main window (cameras only after login)."""

    def __init__(self, app: QApplication, startup: StartupWindow) -> None:
        self.app = app
        self.startup = startup
        self.window = None
        self._workers: list = []
        self._closing_for_flow = False  # logout/update closes the window without quitting

    # ----- helpers -------------------------------------------------------

    def _run(self, func, on_ok, on_fail=None) -> None:
        from campusguard.ui.workers import Worker

        worker = Worker(func, self.app)
        worker.succeeded.connect(on_ok)
        if on_fail is not None:
            worker.failed.connect(on_fail)

        def cleanup() -> None:
            if worker in self._workers:
                self._workers.remove(worker)
            worker.deleteLater()

        worker.finished.connect(cleanup)
        self._workers.append(worker)
        worker.start()

    # ----- sequence ------------------------------------------------------

    def start(self) -> None:
        self.startup.set_status("Checking your account…")
        from campusguard import auth

        self._run(auth.resume, self._after_resume, lambda _error: self.show_login())

    def _after_resume(self, session) -> None:
        if session is not None:
            self.launch_main(session)
        else:
            self.show_login()

    def show_login(self, prefill: str = "", notice: str = "") -> None:
        from campusguard import auth
        from campusguard.ui.login_window import LoginDialog

        if not prefill:
            saved = auth.load_saved()
            prefill = str(saved.get("email", "")) if saved else ""
        self.startup.hide()
        dialog = LoginDialog(prefill, notice)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        session = dialog.session
        dialog.deleteLater()
        if accepted and session is not None:
            self.startup.show()
            self.launch_main(session)
        else:
            self.app.quit()

    def launch_main(self, session) -> None:
        self.startup.set_status("Loading CampusGuard…")
        self.app.processEvents()
        try:
            from campusguard.ui.main_window import MainWindow

            window = MainWindow(account_email=session.email)
            window.logout_requested.connect(lambda: self.logout(session.email))
            window.closed.connect(self._on_window_closed)
            window.show()
            self.startup.hide()
            window.raise_()
            window.activateWindow()
            self.window = window
        except Exception as error:
            self.startup.hide()
            QMessageBox.critical(
                None,
                "CampusGuard could not start",
                f"The main interface failed to load.\n\n{type(error).__name__}: {error}",
            )
            self.app.exit(1)
            return
        self._begin_update_check()

    def _on_window_closed(self) -> None:
        if not self._closing_for_flow:
            self.app.quit()

    def _close_window_for_flow(self, window) -> None:
        self._closing_for_flow = True
        try:
            window.close()
        finally:
            self._closing_for_flow = False

    def logout(self, email: str) -> None:
        from campusguard import auth

        window, self.window = self.window, None
        self.startup.set_status("Signing out…")
        self.startup.show()  # keep a window visible so closing the main one does not quit
        self.app.processEvents()
        auth.clear_saved()
        if window is not None:
            self._close_window_for_flow(window)
            window.deleteLater()
        QTimer.singleShot(0, lambda: self.show_login(prefill=email, notice="You have been signed out."))

    # ----- updates (background, never blocks start-up) -------------------

    def _begin_update_check(self) -> None:
        from campusguard import updater

        self._run(updater.prepare_update, self._offer_update)

    def _offer_update(self, result) -> None:
        if not result or self.window is None:
            return
        info, installer = result
        from campusguard import updater

        answer = QMessageBox.question(
            self.window,
            "CampusGuard update ready",
            f"CampusGuard update {info['version']} has been downloaded and verified.\n\n"
            "Install it now? CampusGuard will close and reopen automatically.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not updater.launch_installer(installer):
            QMessageBox.warning(self.window, "Update", "The installer could not be started. Please try again later.")
            return
        window, self.window = self.window, None
        self._close_window_for_flow(window)
        self.app.quit()


def main() -> int:
    # Fractional display scaling (125%, 150%) stays sharp instead of being rounded.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("CampusGuard")
    app.setOrganizationName("CampusGuard")
    app.setStyle("Fusion")
    # Windows are shown/hidden in sequence (splash, sign-in, main); quit explicitly
    # when the main window is closed rather than whenever no window is visible.
    app.setQuitOnLastWindowClosed(False)
    _load_brand_fonts()
    app.setWindowIcon(QIcon(str(_asset_root() / "assets" / "campusguard-eye.svg")))

    # Smaller screens get a slightly smaller base font so more fits on screen.
    from campusguard.ui.theme import set_compact

    screen = QGuiApplication.primaryScreen()
    if screen is not None:
        avail = screen.availableGeometry()
        set_compact(avail.width() < 1500 or avail.height() < 860)

    # Paint the splash first; everything else happens after the event loop starts.
    startup = StartupWindow()
    startup.show()
    startup.raise_()
    startup.activateWindow()
    app.processEvents()

    controller = AppController(app, startup)
    app._campusguard_controller = controller  # keep alive for the app's lifetime
    QTimer.singleShot(0, controller.start)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
