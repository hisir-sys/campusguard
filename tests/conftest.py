import os
import sys


def pytest_sessionfinish(session, exitstatus):
    """Release native workers and Qt event filters before process shutdown."""
    try:
        from campusguard.ai_pipeline import shutdown_detector_batchers

        shutdown_detector_batchers(timeout=5.0)
    except Exception:
        # Teardown must not mask the actual test result.
        pass

    try:
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            # Dashboard pages are often children of a top-level MainWindow,
            # so closing only top-level widgets would not invoke their
            # closeEvent. Detach their child filters explicitly first.
            from campusguard.ui.dashboard_page import DashboardPage

            for widget in app.allWidgets():
                if isinstance(widget, DashboardPage):
                    widget._detach_card_event_filters()

            for widget in app.topLevelWidgets():
                try:
                    widget.close()
                    widget.deleteLater()
                except RuntimeError:
                    pass
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
    except Exception:
        # Some non-UI test environments do not create a QApplication.
        pass

    if os.environ.get("CAMPUSGUARD_TEST_CLEAN_EXIT") == "1":
        return
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        # Keep the project's existing protection against late Qt/PyTorch
        # interpreter-finalization crashes, but only after orderly cleanup.
        os._exit(int(exitstatus))
