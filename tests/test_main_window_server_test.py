import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from campusguard.ui.main_window import MainWindow


class _Host(QWidget):
    _run_background = MainWindow._run_background


def test_run_background_delivers_success_and_failure():
    app = QApplication.instance() or QApplication([])
    host = _Host()
    results = []
    host._run_background(lambda: 7, results.append, results.append)
    host._bg_task.wait(3000)
    app.processEvents()
    app.processEvents()
    assert results == [7]
    assert host._bg_task is None

    def boom():
        raise RuntimeError("nope")

    host._run_background(boom, results.append, results.append)
    host._bg_task.wait(3000)
    app.processEvents()
    app.processEvents()
    assert results == [7, "nope"]
