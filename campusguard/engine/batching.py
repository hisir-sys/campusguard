"""Collect requests from camera threads into bounded, GPU-sized batches."""
from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import Future, TimeoutError as FutureTimeout
from typing import Callable

from concurrent.futures import CancelledError


class BatchClosed(RuntimeError):
    """Raised when a request is submitted after a batch worker has stopped."""


_STOP = object()


class BatchRunner:
    """Run batches on one worker while making submission and shutdown atomic.

    A submitter and close() share one state lock. Therefore every accepted
    request is queued before the stop marker, and every later request is
    rejected. close() waits for the worker and raises if it cannot terminate.
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
        self.max_batch = max(1, int(max_batch))
        self.max_wait = max(0.0, float(max_wait))
        self._alive = alive or (lambda: True)
        self._queue: queue.Queue = queue.Queue()
        self._state_lock = threading.Lock()
        self._closed = threading.Event()
        self.batch_sizes: list[int] = []
        self._thread = threading.Thread(target=self._loop, name=name, daemon=True)
        self._thread.start()

    @property
    def usable(self) -> bool:
        with self._state_lock:
            return not self._closed.is_set() and self._thread.is_alive()

    @property
    def worker_alive(self) -> bool:
        return self._thread.is_alive()

    def submit(self, item: object, timeout: float = 10.0):
        future: Future = Future()
        with self._state_lock:
            if self._closed.is_set() or not self._thread.is_alive():
                raise BatchClosed("batch runner is not running")
            # Queue insertion happens under the same lock as close() so the
            # stop marker can never overtake an accepted request.
            self._queue.put_nowait((item, future))
        try:
            return future.result(timeout=timeout)
        except FutureTimeout:
            # A timed-out caller must not keep an unobserved result alive.
            future.cancel()
            raise

    def close(self, timeout: float = 5.0) -> None:
        """Reject new work, drain accepted work, and verify worker termination."""
        with self._state_lock:
            if not self._closed.is_set():
                self._closed.set()
                self._queue.put_nowait(_STOP)
        if self._thread is threading.current_thread():
            return
        self._thread.join(timeout=max(0.0, float(timeout)))
        if self._thread.is_alive():
            raise TimeoutError(
                f"batch worker {self._thread.name!r} did not stop within {timeout:.1f}s"
            )

    def _fail_pending(self, message: str) -> None:
        error = BatchClosed(message)
        while True:
            try:
                entry = self._queue.get_nowait()
            except queue.Empty:
                return
            if entry is _STOP:
                continue
            _, future = entry
            if not future.done():
                future.set_exception(error)

    def _stop_if_model_released(self) -> None:
        # Close the submission gate before draining, so no caller can enqueue
        # between the last queue read and the worker exit.
        with self._state_lock:
            self._closed.set()
        self._fail_pending("batch worker stopped because its model was released")

    def _loop(self) -> None:
        while True:
            try:
                first = self._queue.get(timeout=0.1)
            except queue.Empty:
                if not self._alive():
                    self._stop_if_model_released()
                    return
                continue

            if first is _STOP:
                break

            batch = [first]
            stop_after_batch = False
            deadline = time.monotonic() + self.max_wait
            while len(batch) < self.max_batch:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    entry = self._queue.get(timeout=remaining)
                except queue.Empty:
                    break
                if entry is _STOP:
                    stop_after_batch = True
                    break
                batch.append(entry)

            self._dispatch(batch)
            if stop_after_batch:
                break

        self._fail_pending("batch runner closed")

    def _dispatch(self, batch: list[tuple[object, Future]]) -> None:
        active = [(item, future) for item, future in batch if not future.cancelled()]
        if not active:
            return
        self.batch_sizes.append(len(active))
        del self.batch_sizes[:-200]
        try:
            results = self._run_batch([item for item, _ in active])
            if len(results) != len(active):
                raise RuntimeError("batch function returned the wrong number of results")
        except Exception as error:
            for _, future in active:
                if not future.done():
                    future.set_exception(error)
            return
        for (_, future), result in zip(active, results):
            if not future.done():
                future.set_result(result)
