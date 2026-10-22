"""Collect single requests from many camera threads into GPU-sized batches."""
from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import Future
from typing import Callable


class BatchClosed(RuntimeError):
    pass


class BatchRunner:
    """run_batch(items) -> results (same order). Callers block in submit().

    A batch is flushed when `max_batch` items are waiting or `max_wait` seconds
    after the first one, so one busy camera never waits long for others.
    `alive()` lets the worker exit by itself when the model it serves is gone.
    """

    def __init__(
        self,
        run_batch: Callable[[list], list],
        max_batch: int = 8,
        max_wait: float = 0.008,
        alive: Callable[[], bool] | None = None,
        name: str = "campusguard-batch",
    ) -> None:
        self._run_batch = run_batch
        self.max_batch = max(1, max_batch)
        self.max_wait = max_wait
        self._alive = alive or (lambda: True)
        self._queue: queue.Queue[tuple[object, Future]] = queue.Queue()
        self._closed = threading.Event()
        self.batch_sizes: list[int] = []  # recent sizes, for diagnostics/tests
        self._thread = threading.Thread(target=self._loop, name=name, daemon=True)
        self._thread.start()

    @property
    def usable(self) -> bool:
        return not self._closed.is_set() and self._thread.is_alive()

    def submit(self, item: object, timeout: float = 10.0):
        if not self.usable:
            raise BatchClosed("batch runner is not running")
        future: Future = Future()
        self._queue.put((item, future))
        return future.result(timeout=timeout)

    def close(self) -> None:
        self._closed.set()
        self._drain(BatchClosed("batch runner closed"))

    def _drain(self, error: Exception) -> None:
        while True:
            try:
                _, future = self._queue.get_nowait()
            except queue.Empty:
                return
            if not future.done():
                future.set_exception(error)

    def _loop(self) -> None:
        while not self._closed.is_set():
            try:
                first = self._queue.get(timeout=1.0)
            except queue.Empty:
                if not self._alive():
                    break
                continue
            batch = [first]
            deadline = time.monotonic() + self.max_wait
            while len(batch) < self.max_batch:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    batch.append(self._queue.get(timeout=remaining))
                except queue.Empty:
                    break
            self._dispatch(batch)
        self._closed.set()
        self._drain(BatchClosed("batch runner stopped"))

    def _dispatch(self, batch: list[tuple[object, Future]]) -> None:
        self.batch_sizes.append(len(batch))
        del self.batch_sizes[:-200]
        try:
            results = self._run_batch([item for item, _ in batch])
            if len(results) != len(batch):
                raise RuntimeError("batch function returned the wrong number of results")
        except Exception as error:
            for _, future in batch:
                if not future.done():
                    future.set_exception(error)
            return
        for (_, future), result in zip(batch, results):
            if not future.done():
                future.set_result(result)
