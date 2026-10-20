from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal


class Worker(QThread):
    """Runs one blocking call (network) off the UI thread and reports the outcome."""

    succeeded = Signal(object)
    failed = Signal(object)

    def __init__(self, func: Callable[[], object], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._func = func

    def run(self) -> None:
        try:
            result = self._func()
        except Exception as error:  # surfaced to the caller, never swallowed
            self.failed.emit(error)
        else:
            self.succeeded.emit(result)
