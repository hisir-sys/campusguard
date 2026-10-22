"""End-to-end check of FrameAnalysisThread's gating (fake AI pipeline, real threads).

torch/ultralytics are replaced by stubs when they are not installed, so this
runs anywhere; with a real torch it uses the real import and only the pipeline
is faked.
"""
import importlib
import sys
import threading
import time
from types import ModuleType
from unittest.mock import MagicMock

import numpy as np
import pytest

from campusguard.engine.hardware import PROFILES
from dataclasses import replace


@pytest.fixture()
def runtime(monkeypatch, tmp_path):
    try:
        import torch  # noqa: F401
    except ImportError:
        for name in ("torch", "torch.nn", "torch.nn.functional", "torch.jit", "torchvision",
                     "torchvision.models", "torchvision.models.video", "ultralytics"):
            monkeypatch.setitem(sys.modules, name, MagicMock())
    for name in ("campusguard.camera_runtime", "campusguard.ai_pipeline",
                 "campusguard.model_registry", "campusguard.model_adapters"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setenv("CAMPUSGUARD_PROFILE", "")
    module = importlib.import_module("campusguard.camera_runtime")
    monkeypatch.setattr(module, "application_data_dir", lambda: tmp_path)
    yield module
    for name in ("campusguard.camera_runtime", "campusguard.ai_pipeline",
                 "campusguard.model_registry", "campusguard.model_adapters"):
        sys.modules.pop(name, None)


class FakePipeline:
    instances: list = []

    def __init__(self, settings, status):
        self.calls = 0
        self.idle_calls = 0
        self.batch_detector = None
        self.fight_model_ready = True
        FakePipeline.instances.append(self)

    def process(self, frame, settings, ai_enabled, tracking, pose):
        self.calls += 1
        return frame.copy(), "NORMAL", 0.1, None

    def enter_idle(self):
        self.idle_calls += 1

    def render_cached(self, frame, state=None, confidence=None):
        return frame.copy()


def frame(offset=None, size=(180, 320)):
    f = np.full((*size, 3), 90, np.uint8)
    if offset is not None:
        f[50:110, offset:offset + 40] = 220
    return f


def run_thread(runtime, monkeypatch, tmp_path, profile, script):
    FakePipeline.instances.clear()
    monkeypatch.setattr(runtime, "VisionPipeline", FakePipeline)
    monkeypatch.setattr(runtime, "resolve_profile", lambda *a: profile)
    mailbox = runtime.LatestFrameMailbox()
    options = runtime.RuntimeOptions(runtime.AppSettings(), True)
    thread = runtime.FrameAnalysisThread(mailbox, options, tmp_path / "footage")
    shown = []
    from PySide6.QtCore import Qt
    thread.frame_ready.connect(
        lambda image, state, conf: shown.append((image.width(), state)),
        Qt.ConnectionType.DirectConnection,
    )
    thread.start()
    script(mailbox, options)
    mailbox.close()
    thread.requestInterruption()
    assert thread.wait(5000)
    return FakePipeline.instances[0], shown, thread


def feed(mailbox, seconds, still=True, hz=60):
    end = time.monotonic() + seconds
    i = 0
    while time.monotonic() < end:
        mailbox.publish(frame(None if still else (i * 23) % 250))
        i += 1
        time.sleep(1.0 / hz)


FAST = replace(PROFILES["standard"], motion_hangover_s=0.3, gate_hz=60.0)


def test_still_scene_stops_heavy_work_and_motion_resumes_it(runtime, monkeypatch, tmp_path):
    marks = {}

    def script(mailbox, options):
        feed(mailbox, 1.0, still=True)
        marks["after_still"] = FakePipeline.instances[0].calls
        feed(mailbox, 0.6, still=False)
        marks["after_motion"] = FakePipeline.instances[0].calls

    pipeline, shown, _ = run_thread(runtime, monkeypatch, tmp_path, FAST, script)
    # ~60 frames/s for 1 s: only the first ~0.3 s (+ gate lag) is analysed
    assert 1 <= marks["after_still"] <= 14
    assert pipeline.idle_calls == 1
    assert marks["after_motion"] - marks["after_still"] >= 10
    assert len(shown) > 60                         # preview kept flowing while idle
    assert {state for _, state in shown} == {"NORMAL"}


def test_smart_analysis_switched_off_analyses_every_other_frame(runtime, monkeypatch, tmp_path):
    monkeypatch.setenv("CAMPUSGUARD_SMART_ANALYSIS", "0")

    def script(mailbox, options):
        feed(mailbox, 1.0, still=True)

    pipeline, shown, _ = run_thread(runtime, monkeypatch, tmp_path, FAST, script)
    assert pipeline.idle_calls == 0
    assert pipeline.calls >= 25                    # ~half of ~60 frames, never gated


def test_server_profile_downscales_throttles_preview_and_enables_batching(runtime, monkeypatch, tmp_path):
    server = replace(PROFILES["server"], motion_hangover_s=0.3, gate_hz=60.0)

    def script(mailbox, options):
        end = time.monotonic() + 1.0
        while time.monotonic() < end:
            mailbox.publish(frame(None, size=(1080, 1920)))
            time.sleep(1 / 60)

    pipeline, shown, _ = run_thread(runtime, monkeypatch, tmp_path, server, script)
    assert pipeline.batch_detector is True
    assert shown and all(width == 960 for width, _ in shown)      # analysed/previewed at 960 wide
    assert len(shown) <= 14                                       # ~10 fps preview cap
    # evidence prebuffer capped (48 MB / 6 MB per 1080p frame) and original resolution
    # is what the recorder keeps


def test_preview_can_be_disabled_per_camera(runtime, monkeypatch, tmp_path):
    def script(mailbox, options):
        options.set_preview_enabled(False)
        feed(mailbox, 0.5, still=False)

    pipeline, shown, _ = run_thread(runtime, monkeypatch, tmp_path, FAST, script)
    assert pipeline.calls > 0 and shown == []


def test_camera_counter_is_balanced(runtime, monkeypatch, tmp_path):
    from campusguard.engine.registry import ACTIVE_CAMERAS
    before = ACTIVE_CAMERAS.count
    run_thread(runtime, monkeypatch, tmp_path, FAST, lambda m, o: feed(m, 0.2))
    time.sleep(0.2)
    assert ACTIVE_CAMERAS.count == before
