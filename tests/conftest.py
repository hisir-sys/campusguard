"""Shared pytest cleanup for Qt widgets and native inference workers."""
from __future__ import annotations


def pytest_sessionfinish(session, exitstatus):
    """Stop camera QThreads, dispose Qt widgets, then join shared AI workers."""
    cleanup_errors: list[str] = []

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

            top_level = list(app.topLevelWidgets())
            blocked_close: set[int] = set()
            # Camera QThreads must stop before shared detector batch workers.
            for widget in top_level:
                manager = getattr(widget, "camera_manager", None)
                if manager is not None:
                    try:
                        manager.stop_all(timeout_ms=15000)
                    except Exception as error:
                        blocked_close.add(id(widget))
                        cleanup_errors.append(
                            f"camera workers: {type(error).__name__}: {error}"
                        )

            for widget in top_level:
                if id(widget) in blocked_close:
                    continue
                try:
                    widget.close()
                    widget.deleteLater()
                except RuntimeError as error:
                    cleanup_errors.append(f"Qt widget cleanup: {error}")

            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
    except Exception as error:
        cleanup_errors.append(f"Qt application cleanup: {type(error).__name__}: {error}")

    # Camera analysis workers are now stopped; it is safe to stop the shared
    # detector workers. close() verifies the join and reports a timeout.
    try:
        from campusguard.ai_pipeline import shutdown_detector_batchers

        shutdown_detector_batchers(timeout=15.0)
    except Exception as error:
        cleanup_errors.append(f"detector workers: {type(error).__name__}: {error}")

    if cleanup_errors:
        # A teardown failure is a real validation failure, not something to
        # hide by terminating the process with os._exit().
        session.exitstatus = 3
        terminal = session.config.pluginmanager.get_plugin("terminalreporter")
        if terminal is not None:
            terminal.write_sep("=", "CampusGuard cleanup errors")
            for message in cleanup_errors:
                terminal.write_line(message)
