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
