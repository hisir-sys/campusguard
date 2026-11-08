"""Shared pytest cleanup for Qt widgets and native inference workers."""
from __future__ import annotations


def pytest_sessionfinish(session, exitstatus):
    """Stop background workers and dispose Qt widgets without forced process exit."""
    cleanup_errors: list[str] = []

    try:
        from campusguard.ai_pipeline import shutdown_detector_batchers

        shutdown_detector_batchers(timeout=15.0)
    except Exception as error:
        cleanup_errors.append(f"detector workers: {type(error).__name__}: {error}")

    try:
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            from campusguard.ui.dashboard_page import DashboardPage

            for widget in app.allWidgets():
                if isinstance(widget, DashboardPage):
                    try:
                        widget._detach_card_event_filters()
                    except RuntimeError as error:
                        cleanup_errors.append(f"dashboard filters: {error}")

            for widget in app.topLevelWidgets():
                try:
                    widget.close()
                    widget.deleteLater()
                except RuntimeError as error:
                    cleanup_errors.append(f"Qt widget cleanup: {error}")

            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
    except Exception as error:
        cleanup_errors.append(f"Qt application cleanup: {type(error).__name__}: {error}")

    if cleanup_errors:
        # A teardown failure is a real validation failure, not something to
        # hide by terminating the process with os._exit().
        session.exitstatus = 3
        terminal = session.config.pluginmanager.get_plugin("terminalreporter")
        if terminal is not None:
            terminal.write_sep("=", "CampusGuard cleanup errors")
            for message in cleanup_errors:
                terminal.write_line(message)
