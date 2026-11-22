# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
"""Smooth incident clips, independent of how fast the AI keeps up.

The AI only looks at some frames (it skips quiet scenes and runs behind on a busy server), so
clips cut from the frames it sees look choppy. `EvidenceRing` is fed by the camera reader with
*every* frame, at a steady clip frame rate, compressed so a few seconds per camera stay cheap in
memory. `EvidenceRecorder` cuts a clip from it: a few seconds before the detection (pre-roll),
the incident itself, and a few seconds after it calms down (post-roll).

This is a short rolling buffer, not a 24/7 recorder: nothing is kept unless an incident fires.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from campusguard.tuning import MAX_POST_ROLL_SECONDS, MAX_PRE_ROLL_SECONDS

DEFAULT_CLIP_FPS = 20
DEFAULT_CLIP_WIDTH = 1280
DEFAULT_RING_BYTES = 40 * 1024 * 1024
JPEG_QUALITY = 82
MAX_CLIP_SECONDS = 120.0


class EvidenceRing:
    """Thread-safe rolling buffer of compressed frames. The camera reader calls `push`."""

    def __init__(
        self,
        fps: float = DEFAULT_CLIP_FPS,
        width: int = DEFAULT_CLIP_WIDTH,
        keep_seconds: float = MAX_PRE_ROLL_SECONDS + 3.0,
        max_bytes: int = DEFAULT_RING_BYTES,
    ) -> None:
        self._lock = threading.Lock()
        self._frames: deque[tuple[float, bytes]] = deque()
        self._bytes = 0
        self._next_due = -1e9
        self.fps = float(fps)
        self.width = int(width)
        self.keep_seconds = float(keep_seconds)
        self.max_bytes = int(max_bytes)

    def configure(self, fps: float | None = None, width: int | None = None) -> None:
        with self._lock:
            if fps is not None:
                self.fps = max(5.0, min(30.0, float(fps)))
            if width is not None:
                self.width = max(320, min(1920, int(width)))

    def set_max_bytes(self, max_bytes: int | None) -> None:
        if max_bytes and max_bytes > 0:
            with self._lock:
                self.max_bytes = int(max_bytes)

    def clear(self) -> None:
        with self._lock:
            self._frames.clear()
            self._bytes = 0
            self._next_due = -1e9

    def push(self, frame: np.ndarray, t: float | None = None) -> bool:
        """Keep this frame if it is due at the clip frame rate. Returns whether it was kept."""
        if frame is None or not getattr(frame, "size", 0):
            return False
        now = time.monotonic() if t is None else float(t)
        with self._lock:
            # Paced on a fixed schedule (not "time since the last kept frame"): a 25 fps camera into a
            # 20 fps clip then keeps 4 of every 5 frames instead of every other one.
            if now < self._next_due:
                return False
            interval = 1.0 / self.fps
            self._next_due = max(self._next_due + interval, now - interval)
            width = self.width
        height_px, width_px = frame.shape[:2]
        if width_px > width:
            scale = width / float(width_px)
            frame = cv2.resize(frame, (width, max(2, int(round(height_px * scale)))), interpolation=cv2.INTER_AREA)
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            return False
        data = encoded.tobytes()
        with self._lock:
            self._frames.append((now, data))
            self._bytes += len(data)
            self._trim(now)
        return True

    def _trim(self, now: float) -> None:
        horizon = now - self.keep_seconds
        # The newest frame always stays, even if one frame alone is bigger than the byte budget.
        while len(self._frames) > 1 and (self._frames[0][0] < horizon or self._bytes > self.max_bytes):
            _, data = self._frames.popleft()
            self._bytes -= len(data)

    def since(self, start: float, after: float | None = None) -> list[tuple[float, bytes]]:
        """Frames with time >= start and (if given) strictly newer than `after`, oldest first."""
        with self._lock:
            return [
                (t, data) for t, data in self._frames
                if t >= start and (after is None or t > after)
            ]

    def measured_fps(self, window: float = 3.0) -> float:
        """Real frame rate of what is stored (a slow camera gives fewer frames than the clip rate)."""
        with self._lock:
            if len(self._frames) < 2:
                return self.fps
            newest = self._frames[-1][0]
            recent = [t for t, _ in self._frames if t >= newest - window]
        if len(recent) < 2 or recent[-1] <= recent[0]:
            return self.fps
        return (len(recent) - 1) / (recent[-1] - recent[0])

    @property
    def frame_count(self) -> int:
        with self._lock:
            return len(self._frames)

    @property
    def byte_count(self) -> int:
        with self._lock:
            return self._bytes


class EvidenceRecorder:
    """Cuts one MP4 per incident from an `EvidenceRing`. Same shape as FightFootageRecorder."""

    def __init__(
        self,
        output_dir: Path,
        ring: EvidenceRing,
        pre_seconds: float = 5.0,
        post_seconds: float = 8.0,
        clock=time.monotonic,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ring = ring
        self.pre_seconds = float(pre_seconds)
        self.post_seconds = float(post_seconds)
        self._clock = clock
        self.writer: cv2.VideoWriter | None = None
        self.path: Path | None = None
        self._size: tuple[int, int] | None = None
        self._written_until: float | None = None
        self._started_at = 0.0
        self._last_activity = 0.0
        self._armed = False
        self._frames_written = 0

    def set_roll(self, pre_seconds: float, post_seconds: float) -> None:
        self.pre_seconds = max(1.0, min(MAX_PRE_ROLL_SECONDS, float(pre_seconds)))
        self.post_seconds = max(1.0, min(MAX_POST_ROLL_SECONDS, float(post_seconds)))

    @property
    def active(self) -> bool:
        return self._armed

    def reset(self) -> None:
        self._close()
        self._armed = False

    def update(self, state: str, event_started: bool) -> Path | None:
        """Call once per analysed frame. Returns the finished clip's path when one is complete."""
        now = self._clock()
        if event_started and not self._armed:
            self._armed = True
            self._started_at = now
            self._last_activity = now
            self._written_until = None
            self._frames_written = 0
            self._pending_start = now - self.pre_seconds
        if not self._armed:
            return None
        if state != "NORMAL":
            self._last_activity = now
        self._drain()
        if (now - self._last_activity >= self.post_seconds) or (now - self._started_at >= MAX_CLIP_SECONDS):
            return self._finish()
        return None

    def stop(self) -> Path | None:
        if not self._armed:
            self._close()
            return None
        self._drain()
        return self._finish()

    # ------------------------------------------------------------------ internals
    def _drain(self) -> None:
        start = self._pending_start if self._written_until is None else 0.0
        frames = self.ring.since(start, after=self._written_until)
        for t, data in frames:
            frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                continue
            if self.writer is None and not self._open(frame):
                return
            if self._size is not None and (frame.shape[1], frame.shape[0]) != self._size:
                frame = cv2.resize(frame, self._size, interpolation=cv2.INTER_AREA)
            if self.writer is not None:
                self.writer.write(frame)
                self._frames_written += 1
            self._written_until = t

    def _open(self, frame: np.ndarray) -> bool:
        height, width = frame.shape[:2]
        if width < 2 or height < 2:
            return False
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        path = self.output_dir / f"FIGHT_{stamp}.mp4"
        fps = max(8.0, min(30.0, self.ring.measured_fps()))
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        if not writer.isOpened():
            writer.release()
            return False
        self.writer, self.path, self._size = writer, path, (width, height)
        return True

    def _finish(self) -> Path | None:
        path = self._close()
        self._armed = False
        return path

    def _close(self) -> Path | None:
        writer, path = self.writer, self.path
        self.writer = None
        self.path = None
        self._size = None
        self._written_until = None
        if writer is not None:
            writer.release()
        if path is not None and path.is_file() and path.stat().st_size > 0 and self._frames_written > 0:
            return path
        if path is not None:
            try:
                path.unlink()
            except OSError:
                pass
        return None

    _pending_start = 0.0
