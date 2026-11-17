"""Popups: repeated or simultaneous camera problems become one notice, and toasts never stack duplicates."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from campusguard.camera_notices import OPERATOR_STOP_MESSAGE, describe_problems, is_problem
from campusguard.ui.main_window import MainWindow
from campusguard.ui.notify import MAX_TOASTS, ToastStack

UNREACHABLE = "Camera stream could not be opened. Check the address and credentials."


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_only_real_problems_are_reported():
    assert is_problem("OFFLINE", UNREACHABLE) and is_problem("ERROR", "bad address")
    assert not is_problem("OFFLINE", OPERATOR_STOP_MESSAGE)  # the operator stopped it on purpose
    assert not is_problem("LIVE", "") and not is_problem("CONNECTING", "") and not is_problem("OFFLINE", "")


def test_notice_wording_for_one_few_and_many_cameras():
    assert describe_problems([]) == ""
    assert describe_problems([("Gate", UNREACHABLE)]) == f"Gate: {UNREACHABLE}"
    two = describe_problems([("Gate", "x"), ("Hall", "y")])
    assert two.startswith("2 cameras need attention: Gate, Hall.") and "Cameras" in two
    many = describe_problems([(f"Cam {i}", "x") for i in range(1, 8)])
    assert many.startswith("7 cameras need attention: Cam 1, Cam 2, Cam 3 and 4 more.")


class _Host(QWidget):
    """Just enough of the main window to run the camera-problem notice."""

    _track_camera_problem = MainWindow._track_camera_problem
    _forget_camera_problem = MainWindow._forget_camera_problem
    _announce_camera_problems = MainWindow._announce_camera_problems

    def __init__(self, names: list[str]) -> None:
        super().__init__()
        self.resize(900, 600)
        self.show()
        self.cameras = {f"CAM-{i}": SimpleNamespace(name=name) for i, name in enumerate(names, 1)}
        self._camera_problems: dict[str, str] = {}
        self._camera_unannounced: set[str] = set()
        self._camera_notice_timer = QTimer(self)
        self._camera_notice_timer.setSingleShot(True)
        self._camera_notice_timer.setInterval(5)
        self._camera_notice_timer.timeout.connect(self._announce_camera_problems)
        self._toasts = ToastStack(self)


def _wait(milliseconds: int) -> None:
    from PySide6.QtCore import QEventLoop

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def test_one_camera_retrying_for_a_minute_shows_one_toast():
    _app()
    host = _Host(["Gate"])
    for _ in range(12):  # twelve retries
        host._track_camera_problem("CAM-1", "OFFLINE", UNREACHABLE)
        _wait(8)
    assert len(host._toasts._toasts) == 1
    assert host._toasts._toasts[0].label.text() == f"Gate: {UNREACHABLE}"


def test_many_cameras_failing_together_share_one_toast():
    _app()
    host = _Host([f"Cam {i}" for i in range(1, 9)])
    for camera_id in host.cameras:
        host._track_camera_problem(camera_id, "OFFLINE", UNREACHABLE)
    _wait(40)
    assert len(host._toasts._toasts) == 1
    assert "8 cameras need attention" in host._toasts._toasts[0].label.text()


def test_a_later_failure_updates_the_same_toast_instead_of_adding_one():
    _app()
    host = _Host(["Gate", "Hall"])
    host._track_camera_problem("CAM-1", "OFFLINE", UNREACHABLE)
    _wait(40)
    first = host._toasts._toasts[0]
    host._track_camera_problem("CAM-2", "ERROR", "Bad address.")
    _wait(40)
    assert host._toasts._toasts == [first]
    assert first.label.text().startswith("2 cameras need attention: Gate, Hall")


def test_a_camera_that_recovers_can_be_announced_again_later():
    _app()
    host = _Host(["Gate"])
    host._track_camera_problem("CAM-1", "OFFLINE", UNREACHABLE)
    _wait(40)
    host._toasts._toasts[0].close_now()
    assert not host._toasts._toasts
    host._track_camera_problem("CAM-1", "OFFLINE", UNREACHABLE)  # still down: no new notice
    _wait(40)
    assert not host._toasts._toasts
    host._track_camera_problem("CAM-1", "LIVE", "")  # recovered
    host._track_camera_problem("CAM-1", "OFFLINE", "Camera stopped returning frames.")  # a new outage
    _wait(40)
    assert [toast.label.text() for toast in host._toasts._toasts] == ["Gate: Camera stopped returning frames."]


def test_stopping_or_removing_a_camera_is_not_a_problem_and_clears_it():
    _app()
    host = _Host(["Gate"])
    host._track_camera_problem("CAM-1", "OFFLINE", OPERATOR_STOP_MESSAGE)
    _wait(40)
    assert not host._toasts._toasts and not host._camera_problems
    host._track_camera_problem("CAM-1", "OFFLINE", UNREACHABLE)
    host._forget_camera_problem("CAM-1")  # removed before the notice fired
    _wait(40)
    assert not host._toasts._toasts


def test_identical_toasts_do_not_stack_and_the_timer_restarts():
    _app()
    host = QWidget()
    host.resize(900, 600)
    host.show()
    stack = ToastStack(host)
    first = stack.show_toast("Test alert sent.", ms=50)
    for _ in range(5):
        assert stack.show_toast("Test alert sent.", ms=400) is first
    assert len(stack._toasts) == 1
    _wait(120)  # the first 50 ms would have closed it, but repeats extended its life
    assert stack._toasts == [first]
    _wait(500)
    assert not stack._toasts


def test_keyed_toast_updates_text_and_different_text_still_stacks():
    _app()
    host = QWidget()
    host.resize(900, 600)
    host.show()
    stack = ToastStack(host)
    one = stack.show_toast("Importing 1", key="import")
    assert stack.show_toast("Importing 2", key="import") is one and one.label.text() == "Importing 2"
    other = stack.show_toast("Something else")
    assert other is not one and len(stack._toasts) == 2
    for i in range(MAX_TOASTS + 3):
        stack.show_toast(f"Different {i}")
    assert len(stack._toasts) == MAX_TOASTS


def test_toasts_with_undo_are_never_merged():
    _app()
    host = QWidget()
    host.resize(900, 600)
    host.show()
    stack = ToastStack(host)
    undone = []
    first = stack.show_toast("Removed", undo=lambda: undone.append("a"))
    second = stack.show_toast("Removed", undo=lambda: undone.append("b"))
    assert first is not second
    second.findChild(QPushButton, "toastUndo").click()
    assert undone == ["b"]


def test_a_closed_toast_can_be_shown_again_and_wraps_long_text():
    _app()
    host = QWidget()
    host.resize(900, 600)
    host.show()
    stack = ToastStack(host)
    toast = stack.show_toast("Saved")
    toast.close_now()
    assert not stack._toasts and not stack._keys
    again = stack.show_toast("Saved")
    assert again is not toast
    long_text = "A long notice that needs more than one line to read properly on a narrow corner of the window. " * 2
    again.update_message(long_text)
    assert again.label.wordWrap() and again.label.width() == 340
