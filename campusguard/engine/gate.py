"""Cheap motion gate + per-camera scheduler.

Stage 1 of the two-stage analysis. Every camera runs a tiny motion check
(80x45 grey image, a fraction of a millisecond). The heavy detector / pose /
fight models only run while the scene is moving, plus a hangover afterwards.
Anything uncertain (first frame, global light change, camera that never stops
moving, a fight in progress) counts as motion, so the gate can only ever cause
*more* analysis, never silently skip a real event.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np

GATE_SIZE = (80, 45)
PIXEL_THRESHOLD = 18        # grey levels a pixel must change to count
AREA_FRACTION = 0.0015      # ~5 changed pixels of the 3600 -> small/far people still wake it


class MotionGate:
    def __init__(self, pixel_threshold: int = PIXEL_THRESHOLD, area_fraction: float = AREA_FRACTION) -> None:
        self.pixel_threshold = pixel_threshold
        self.area_fraction = area_fraction
        self._previous: np.ndarray | None = None

    def reset(self) -> None:
        self._previous = None

    def has_motion(self, frame: np.ndarray) -> bool:
        if frame is None or frame.size == 0:
            return True  # unknown -> analyse
        small = cv2.resize(frame, GATE_SIZE, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        previous, self._previous = self._previous, gray
        if previous is None or previous.shape != gray.shape:
            return True
        changed = cv2.absdiff(gray, previous) > self.pixel_threshold
        return float(changed.mean()) >= self.area_fraction


@dataclass(frozen=True)
class Plan:
    active: bool          # heavy analysis allowed for this frame
    analyze: bool         # run VisionPipeline.process on this frame
    entered_idle: bool    # camera just went quiet -> reset temporal state
    stride: int


class AdaptiveStride:
    """Raise the analysis stride only when a camera cannot keep up; never below base.

    ratio = processing time / time available between analyses. Above HIGH for a
    sustained period -> stride+1; below LOW -> back towards base. Under normal
    load the stride stays at base, so behaviour is unchanged.
    """

    HIGH = 0.85
    LOW = 0.40
    DWELL_SECONDS = 4.0

    def __init__(self, base: int = 2, maximum: int = 4, clock: Callable[[], float] = time.monotonic) -> None:
        self.base, self.maximum, self._clock = base, maximum, clock
        self.stride = base
        self._ema: float | None = None
        self._last_change = clock()
        self._frame_interval: float | None = None
        self._last_frame_time: float | None = None

    def observe_frame(self, now: float) -> None:
        if self._last_frame_time is not None:
            delta = now - self._last_frame_time
            if 0 < delta < 2.0:
                self._frame_interval = delta if self._frame_interval is None else 0.9 * self._frame_interval + 0.1 * delta
        self._last_frame_time = now

    def record(self, process_seconds: float) -> None:
        if not self._frame_interval:
            return
        ratio = process_seconds / (self.stride * self._frame_interval)
        self._ema = ratio if self._ema is None else 0.8 * self._ema + 0.2 * ratio
        now = self._clock()
        if now - self._last_change < self.DWELL_SECONDS:
            return
        if self._ema > self.HIGH and self.stride < self.maximum:
            self.stride += 1
            self._last_change, self._ema = now, None
        elif self._ema < self.LOW and self.stride > self.base:
            self.stride -= 1
            self._last_change, self._ema = now, None


class CameraScheduler:
    """Decides, frame by frame, whether the heavy pipeline should run."""

    def __init__(
        self,
        smart_analysis: bool = True,
        hangover_s: float = 5.0,
        gate_hz: float = 10.0,
        base_stride: int = 2,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self.smart_analysis = smart_analysis
        self.hangover_s = hangover_s
        self.gate_interval = 1.0 / max(gate_hz, 0.5)
        self.gate = MotionGate()
        self.strider = AdaptiveStride(base_stride, clock=clock)
        self._active_until = 0.0
        self._next_gate = 0.0
        self._was_active = True
        self._counter = 0

    def configure(self, smart_analysis: bool, hangover_s: float, gate_hz: float) -> None:
        self.smart_analysis = smart_analysis
        self.hangover_s = hangover_s
        self.gate_interval = 1.0 / max(gate_hz, 0.5)

    def plan(self, frame: np.ndarray, gate_allowed: bool, busy: bool) -> Plan:
        """gate_allowed: AI on and models ready. busy: an event/recording is in progress."""
        now = self._clock()
        self.strider.observe_frame(now)
        if not (self.smart_analysis and gate_allowed):
            active = True
        else:
            if now >= self._next_gate:
                self._next_gate = now + self.gate_interval
                if self.gate.has_motion(frame):
                    self._active_until = now + self.hangover_s
            active = busy or now < self._active_until
        entered_idle = self._was_active and not active
        self._was_active = active
        if not active:
            self._counter = 0
            return Plan(False, False, entered_idle, self.strider.stride)
        self._counter += 1
        analyze = self._counter == 1 or self._counter % self.strider.stride == 0
        return Plan(True, analyze, False, self.strider.stride)

    def record(self, process_seconds: float) -> None:
        self.strider.record(process_seconds)
