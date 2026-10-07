from __future__ import annotations

from datetime import datetime, timezone
from collections import deque
from pathlib import Path

import cv2
import numpy as np


class FightFootageRecorder:
    """Records one complete latched detection into a single MP4 file."""

    NORMAL_RELEASE_FRAMES = 6
    PRE_EVENT_SECONDS = 2.0

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.writer: cv2.VideoWriter | None = None
        self.path: Path | None = None
        self.normal_frames = 0
        self.frame_size: tuple[int, int] | None = None
        self.fps = 25.0
        self.prebuffer: deque[np.ndarray] = deque(maxlen=60)

    @property
    def active(self) -> bool:
        return self.writer is not None

    def reset(self) -> None:
        self._close_writer()
        self.path = None
        self.normal_frames = 0
        self.frame_size = None
        self.prebuffer.clear()

    def update(
        self,
        frame: np.ndarray,
        state: str,
        event_started: bool,
        source_fps: float | None = None,
    ) -> Path | None:
        finished: Path | None = None

        # Keep a rolling lead-in so the saved evidence does not begin several
        # temporal predictions after the visible confrontation starts.
        if frame is not None and frame.size:
            self.prebuffer.append(frame.copy())

        if event_started and not self.active:
            self._start(frame, source_fps)
            if self.active and self.writer is not None and self.frame_size == (frame.shape[1], frame.shape[0]):
                for buffered in list(self.prebuffer)[:-1]:
                    if buffered.shape[1] == self.frame_size[0] and buffered.shape[0] == self.frame_size[1]:
                        self.writer.write(buffered)

        if self.active and self.writer is not None:
            if self.frame_size == (frame.shape[1], frame.shape[0]):
                self.writer.write(frame)

            if state == "NORMAL":
                self.normal_frames += 1
            else:
                self.normal_frames = 0

            if self.normal_frames >= self.NORMAL_RELEASE_FRAMES:
                finished = self._close_writer()

        return finished

    def stop(self) -> Path | None:
        return self._close_writer()

    def _start(self, frame: np.ndarray, source_fps: float | None) -> None:
        self._close_writer()

        height, width = frame.shape[:2]
        if width < 2 or height < 2:
            return

        self.frame_size = (width, height)
        self.fps = max(8.0, min(float(source_fps or 25.0), 60.0))

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        self.path = self.output_dir / f"FIGHT_{stamp}.mp4"

        writer = cv2.VideoWriter(
            str(self.path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            self.fps,
            self.frame_size,
        )

        if not writer.isOpened():
            writer.release()
            self.path = None
            self.frame_size = None
            return

        self.writer = writer
        self.normal_frames = 0

    def _close_writer(self) -> Path | None:
        writer = self.writer
        path = self.path

        self.writer = None
        self.path = None
        self.frame_size = None
        self.normal_frames = 0

        if writer is not None:
            writer.release()

        if path is not None and path.is_file() and path.stat().st_size > 0:
            return path

        return None


def clear_footage(output_dir: Path) -> int:
    """Delete saved MP4 footage and return the number of files removed."""
    if not output_dir.exists():
        return 0

    removed = 0
    for path in output_dir.glob("*.mp4"):
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def footage_exists(path_text: str | None) -> bool:
    return bool(path_text and Path(path_text).is_file())
