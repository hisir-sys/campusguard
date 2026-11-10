from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer, QVariantAnimation, Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from campusguard.ui.thinking_orb import ThinkingOrb


# The orb stays on screen at least this long after launch (5-7 seconds).
SPLASH_MIN_SECONDS = 6.0


def _asset_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _load_brand_fonts() -> None:
    """Register the bundled website fonts (DM Sans, Manrope) so the UI does not
    fall back to Segoe UI on machines that do not have them installed."""
    for font_file in sorted((_asset_root() / "assets" / "fonts").glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(font_file))


class StartupWindow(QWidget):
    """Launch screen: the CampusGuard mark slides in, the dot pops and ripples, the wordmark
    rises and a bar fills while the app loads. Colours follow the saved dark/light theme."""

    LOGO_SECONDS = 3.4

    def __init__(self) -> None:
        super().__init__()
        from campusguard.ui.brand_logo import SPLASH, LogoReveal, saved_theme
        from campusguard.ui.theme import set_current

        self.setWindowTitle("CampusGuard")
        self.setWindowIcon(QApplication.windowIcon())
        self.setFixedSize(480, 420)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        theme = saved_theme()
        set_current(theme)
        colors = SPLASH[theme]
        panel = QFrame(self)
        panel.setObjectName("startupPanel")
        panel.setGeometry(0, 0, 480, 420)
        panel.setStyleSheet(
            f"""
            QFrame#startupPanel {{
                background: {colors["bg"]};
                border: 1px solid {colors["line"]};
                border-radius: 28px;
            }}
            QLabel {{ background: transparent; border: none; }}
            """
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 28, 24, 24)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.logo = LogoReveal(panel, size=104)
        self.logo.setAccessibleName("CampusGuard start-up animation")
        layout.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(4)

        self.status = QLabel("Starting")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet(f"color: {colors['mute']}; font-size: 10pt;")
        layout.addWidget(self.status)

        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            self.move(avail.x() + (avail.width() - self.width()) // 2, avail.y() + (avail.height() - self.height()) // 2)

    def set_status(self, text: str) -> None:
        self.status.setText(text.rstrip("…. "))

    def showEvent(self, event) -> None:
        self.logo.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self.logo.stop()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self.logo.stop()
        super().closeEvent(event)


class AppController:
    """Start-up sequence: splash -> sign in -> main window (cameras only after login)."""

    def __init__(self, app: QApplication, startup: StartupWindow) -> None:
        self.app = app
        self.startup = startup
        self.window = None
        self._workers: list = []
        self._closing_for_flow = False  # logout/update closes the window without quitting
        self._launched_at = time.monotonic()

    def _after_splash(self, func) -> None:
        """Run ``func`` once the orb has been shown for SPLASH_MIN_SECONDS since launch."""
        remaining = max(0.0, SPLASH_MIN_SECONDS - (time.monotonic() - self._launched_at))
        QTimer.singleShot(int(remaining * 1000), func)

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
        self.startup.set_status("Starting CampusGuard…")
        QTimer.singleShot(1200, lambda: self.startup.set_status("Checking your account…"))
        from campusguard import auth

        self._run(auth.resume, self._after_resume, lambda _error: self._after_splash(self.show_login))

    def _after_resume(self, session) -> None:
        if session is None:
            self._after_splash(self.show_login)
            return
        # Build the window now (the heavy part), then keep the orb animating until
        # the minimum splash time has passed before revealing it.
        self.startup.set_status("Preparing your workspace…")
        window = self._build_window(session)
        if window is not None:
            self._after_splash(lambda: self._present_window(window))

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
        """Build and show the main window right away (used after an interactive sign-in)."""
        self.startup.set_status("Loading CampusGuard…")
        self.app.processEvents()
        window = self._build_window(session)
        if window is not None:
            self._present_window(window)

    def _build_window(self, session):
        try:
            from campusguard.ui.main_window import MainWindow

            window = MainWindow(account_email=session.email)
            window.logout_requested.connect(lambda: self.logout(session.email))
            window.update_check_requested.connect(self._manual_update_check)
            window.rollback_requested.connect(self._rollback)
            window.closed.connect(self._on_window_closed)
            return window
        except Exception as error:
            self.startup.hide()
            QMessageBox.critical(
                None,
                "CampusGuard could not start",
                f"The main interface failed to load.\n\n{type(error).__name__}: {error}",
            )
            self.app.exit(1)
            return None

    def _present_window(self, window) -> None:
        window.show_fitted()
        self.startup.hide()
        window.raise_()
        window.activateWindow()
        self.window = window
        self._confirm_finished_update()
        self._begin_update_check()

    def _on_window_closed(self) -> None:
        if not self._closing_for_flow:
            self.app.quit()

    def _close_window_for_flow(self, window) -> bool:
        """Close a window for logout/update, reporting when its close was rejected."""
        self._closing_for_flow = True
        try:
            return bool(window.close())
        finally:
            self._closing_for_flow = False

    def logout(self, email: str) -> None:
        from campusguard import auth

        window = self.window
        self.startup.set_status("Signing out…")
        self.startup.show()  # keep a window visible so closing the main one does not quit
        self.app.processEvents()
        if window is not None and not self._close_window_for_flow(window):
            # MainWindow rejected close because a native worker is still active.
            # Keep the session and the live window; never delete a window whose
            # closeEvent deliberately refused to shut down safely.
            self.startup.hide()
            window.raise_()
            window.activateWindow()
            return

        self.window = None
        auth.clear_saved()
        if window is not None:
            window.deleteLater()
        QTimer.singleShot(0, lambda: self.show_login(prefill=email, notice="You have been signed out."))

    # ----- updates (background, never blocks start-up) -------------------

    def _begin_update_check(self) -> None:
        from campusguard import updater

        # Only the small version check runs first; the large installer is downloaded
        # after the user agrees, so the popup appears within seconds.
        self._run(updater.check_for_update, self._offer_update)

    def _confirm_finished_update(self) -> None:
        """After the installer relaunched us on the new build, say so once."""
        from campusguard import updater
        from campusguard.ui.update_dialog import UpdateDialog

        failed = updater.failed_update_marker()
        if failed and self.window is not None:
            self.window.statusBar().showMessage(
                "The last update did not install. You are still on the previous version; "
                "use Roll back or Check for updates to retry.", 15000)
        marker = updater.consume_update_marker()
        if marker and self.window is not None:
            dialog = UpdateDialog(str(marker["to"]), self.window, done=True)
            self._done_dialog = dialog
            dialog.open()

    def _manual_update_check(self) -> None:
        from campusguard import updater

        def finished(result) -> None:
            info, message = result
            if self.window is not None:
                self.window.settings_page.set_update_status(message)
            if info:
                self._offer_update(info)

        def failed(_error) -> None:
            if self.window is not None:
                self.window.settings_page.set_update_status("The update check failed. Try again in a moment.")

        self._run(updater.check_for_update_detailed, finished, failed)

    def _rollback(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from campusguard import updater

        if self.window is None:
            return
        candidate = updater.rollback_candidate()
        if candidate is None:
            self.window.statusBar().showMessage(
                "No earlier version is stored on this computer yet (one is kept after each update).", 8000)
            return
        answer = QMessageBox.question(
            self.window, "Roll back",
            f"Reinstall build {candidate[0]} and restart CampusGuard? Your cameras, incidents and settings are kept.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        if updater.launch_rollback() is None:
            self.window.statusBar().showMessage("Could not start the rollback installer.", 8000)
            return
        window, self.window = self.window, None
        if not self._close_window_for_flow(window):
            self.window = window
            return
        window.deleteLater()
        self.app.quit()

    def _offer_update(self, info) -> None:
        if not info or self.window is None or getattr(self, "_update_dialog", None) is not None:
            return
        from campusguard.ui.update_dialog import UpdateDialog

        dialog = UpdateDialog(str(info["version"]), self.window)
        self._update_dialog = dialog
        dialog.update_requested.connect(lambda: self._start_update(info))
        dialog.finished.connect(lambda _r: setattr(self, "_update_dialog", None))
        dialog.open()

    def _start_update(self, info) -> None:
        from campusguard import updater

        dialog = getattr(self, "_update_dialog", None)
        self._pending_version = str(info["version"])
        if dialog is not None:
            dialog.show_downloading()
        self._run(
            lambda: updater.download_installer(info["url"], info["checksum_url"]),
            self._install_update,
        )

    def _install_update(self, installer) -> None:
        if self.window is None:
            return
        from campusguard import updater

        dialog = getattr(self, "_update_dialog", None)
        if not installer:
            if dialog is not None:
                dialog.show_failed()
            return
        version = str(getattr(self, "_pending_version", ""))
        updater.archive_installer(installer, version)
        updater.mark_update_started(version)
        if not updater.launch_installer(installer):
            updater.consume_update_marker()
            if dialog is not None:
                dialog.show_failed()
            return
        window, self.window = self.window, None
        if dialog is not None:
            dialog.close()
        if not self._close_window_for_flow(window):
            self.window = window
            if dialog is not None:
                dialog.show_failed()
            return
        self.window = None
        window.deleteLater()
        self.app.quit()


def run_self_check(result_file: str | None) -> int:
    """Build smoke test: `CampusGuard.exe --self-check result.txt`.

    The release workflow runs this on the freshly built app so a bundle that is
    missing Qt plugins, fonts, models or AI libraries fails the build instead of
    reaching customers. It writes OK or FAIL lines to ``result_file``.
    """
    problems: list[str] = []

    def check(name: str, func) -> None:
        try:
            func()
        except BaseException as error:  # report everything, keep going
            problems.append(f"{name}: {type(error).__name__}: {error}")

    app = QApplication(sys.argv[:1])

    def fonts() -> None:
        _load_brand_fonts()
        families = set(QFontDatabase.families())
        for family in ("DM Sans", "Manrope"):
            if family not in families:
                raise RuntimeError(f"font {family} not registered")

    def svg() -> None:
        from campusguard.ui.icons import logo_pixmap

        if logo_pixmap(32).isNull():
            raise RuntimeError("logo SVG did not render")

    def models() -> None:
        from campusguard.ai_pipeline import resolve_model_path

        for name in ("yolo11n.pt", "yolo11n-pose.pt", "model_16_m3_0.8888.pth"):
            if not resolve_model_path(f"models/{name}").is_file():
                raise RuntimeError(f"model {name} not found in the bundle")

    def ui() -> None:
        import campusguard.ui.main_window  # noqa: F401
        import campusguard.ui.login_window  # noqa: F401

    def ai_stack() -> None:
        import campusguard.camera_runtime  # noqa: F401
        import cv2  # noqa: F401
        import torch  # noqa: F401
        import torchvision  # noqa: F401
        import ultralytics  # noqa: F401

    def engine() -> None:
        import numpy as np

        from campusguard.engine.batching import BatchRunner
        from campusguard.engine.gate import CameraScheduler
        from campusguard.engine.hardware import detect_hardware, resolve_profile

        profile = resolve_profile("auto", detect_hardware(), 1)
        plan = CameraScheduler(profile.smart_analysis).plan(np.zeros((90, 160, 3), np.uint8), True, False)
        if not plan.analyze:
            raise RuntimeError("engine scheduler did not schedule the first frame")
        runner = BatchRunner(lambda items: list(items))
        try:
            if runner.submit(7) != 7:
                raise RuntimeError("batch runner returned a wrong result")
        finally:
            runner.close()

    def server() -> None:
        import xml.etree.ElementTree as ET

        import campusguard.server.host  # noqa: F401
        from campusguard.server.cli import build_task_xml
        from campusguard.server.csv_import import parse_cameras_csv

        ET.fromstring(build_task_xml("C:\\x.exe", "--server", "A\\b").replace('encoding="UTF-16"', ""))
        plan = parse_cameras_csv("name,address\nA,rtsp://10.0.0.1/s\n")
        if len(plan.valid) != 1:
            raise RuntimeError("server camera import self-test failed")

    def vault() -> None:
        import keyring

        keyring.get_keyring()

    def version() -> None:
        from campusguard.build_info import BUILD_VERSION

        if getattr(sys, "frozen", False) and BUILD_VERSION == "dev":
            raise RuntimeError("build version was not baked into the app; auto-update would never trigger")

    for name, func in (("version", version), ("fonts", fonts), ("svg", svg), ("models", models), ("ui", ui), ("ai-stack", ai_stack), ("engine", engine), ("server", server), ("keyring", vault)):
        check(name, func)

    message = "OK" if not problems else "FAIL\n" + "\n".join(problems)
    if result_file:
        Path(result_file).write_text(message + "\n", encoding="utf-8")
    del app
    return 0 if not problems else 1


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-check":
        return run_self_check(sys.argv[2] if len(sys.argv) > 2 else None)
    from campusguard.server import cli

    server_exit = cli.handle(sys.argv[1:])
    if server_exit is not None:
        return server_exit
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
    from campusguard.ui.screen_fit import base_font_pt
    from campusguard.ui.theme import set_base_pt

    screen = QGuiApplication.primaryScreen()
    if screen is not None:
        avail = screen.availableGeometry()
        set_base_pt(base_font_pt(avail.width(), avail.height()))

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
