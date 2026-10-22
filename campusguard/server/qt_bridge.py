"""Run a callable on the Qt main thread and wait for its result (for API threads)."""
from __future__ import annotations

from concurrent.futures import Future
from typing import Callable

from PySide6.QtCore import QObject, QThread, Qt, Signal


class MainThreadInvoker(QObject):
    _requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._requested.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def _run(self, task) -> None:
        function, future = task
        try:
            future.set_result(function())
        except BaseException as error:  # delivered to the waiting API thread
            future.set_exception(error)

    def call(self, function: Callable[[], object], timeout: float = 30.0):
        if QThread.currentThread() is self.thread():
            return function()
        future: Future = Future()
        self._requested.emit((function, future))
        return future.result(timeout=timeout)
