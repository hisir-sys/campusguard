"""Pipeline changes for the engine: batched detection and idle reset (stubs if no torch)."""
import importlib
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest


@pytest.fixture()
def ai(monkeypatch):
    try:
        import torch  # noqa: F401
    except ImportError:
        for name in ("torch", "torch.nn", "torch.nn.functional", "torch.jit", "torchvision",
                     "torchvision.models", "torchvision.models.video", "ultralytics"):
            monkeypatch.setitem(sys.modules, name, MagicMock())
    names = ("campusguard.ai_pipeline", "campusguard.model_registry", "campusguard.model_adapters")
    for name in names:
        monkeypatch.delitem(sys.modules, name, raising=False)
    module = importlib.import_module("campusguard.ai_pipeline")
    yield module
    for name in names:
        sys.modules.pop(name, None)


class Arr:
    def __init__(self, a): self.a = np.asarray(a, dtype=float)
    def detach(self): return self
    def cpu(self): return self
    def numpy(self): return self.a


def result_for(frame):
    h, w = frame.shape[:2]
    box = [[w * 0.2, h * 0.2, w * 0.4, h * 0.8]]
    return SimpleNamespace(boxes=SimpleNamespace(xyxy=Arr(box), conf=Arr([0.9]), id=None))


class FakeDetector:
    def __init__(self):
        self.calls = []
        self.fail_lists = False
    def predict(self, source, **kwargs):
        frames = source if isinstance(source, list) else [source]
        if isinstance(source, list) and self.fail_lists:
            raise RuntimeError("cuda out of memory")
        time.sleep(0.01)
        self.calls.append(len(frames))
        return [result_for(f) for f in frames]


def make_pipeline(ai, detector, batch):
    pipe = object.__new__(ai.VisionPipeline)
    pipe.detector = detector
    pipe.device = SimpleNamespace(type="cuda" if batch else "cpu", __str__=lambda s: "cuda:0")
    pipe.device = SimpleNamespace(type="cuda" if batch else "cpu")
    pipe.batch_detector = batch
    pipe.frame_index = 1
    pipe.fallback_tracks = {}
    pipe.next_fallback_track_id = -1
    pipe.display_ids = {}
    pipe.display_track_memory = {}
    pipe.next_display_id = 1
    return pipe


def test_detections_are_identical_batched_or_direct(ai):
    frame = np.zeros((360, 640, 3), np.uint8)
    direct = make_pipeline(ai, FakeDetector(), batch=False)
    batched = make_pipeline(ai, FakeDetector(), batch=True)
    a = direct._detect_people(frame, True, None)
    b = batched._detect_people(frame, True, None)
    assert [p.bbox for p in a] == [p.bbox for p in b] and len(a) == 1


def test_concurrent_cameras_share_one_gpu_batch(ai):
    detector = FakeDetector()
    pipes = [make_pipeline(ai, detector, batch=True) for _ in range(8)]
    frame = np.zeros((360, 640, 3), np.uint8)
    out = {}

    def run(i):
        out[i] = pipes[i]._detect_people(frame, True, None)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert all(len(v) == 1 for v in out.values())
    assert max(detector.calls) > 1                      # frames from several cameras in one call
    assert sum(detector.calls) == 8


def test_batch_failure_falls_back_to_single_frame(ai):
    detector = FakeDetector()
    detector.fail_lists = True
    pipe = make_pipeline(ai, detector, batch=True)
    people = pipe._detect_people(np.zeros((360, 640, 3), np.uint8), True, None)
    assert len(people) == 1 and detector.calls == [1]


def test_mixed_resolutions_in_one_batch(ai):
    detector = FakeDetector()
    pipes = [make_pipeline(ai, detector, batch=True) for _ in range(4)]
    frames = [np.zeros((360, 640, 3), np.uint8), np.zeros((720, 1280, 3), np.uint8)] * 2
    out = {}

    def run(i):
        out[i] = pipes[i]._detect_people(frames[i], True, None)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    for i in range(4):
        h, w = frames[i].shape[:2]
        assert out[i][0].bbox[2] == int(w * 0.4)          # each camera got its own frame's result


def test_enter_idle_clears_temporal_state(ai):
    pipe = object.__new__(ai.VisionPipeline)
    resets = []
    pipe.classifiers = {"fdsc_mc3": SimpleNamespace(reset=lambda: resets.append(1), ready=True)}
    pipe.settings = SimpleNamespace(violence_model="fdsc_mc3")
    pipe.decision = ai.FightDecision(0.65)
    pipe.interactions = ai.InteractionEngine()
    pipe.display_ids = {1: 1}; pipe.display_track_memory = {1: 1}; pipe.next_display_id = 5
    pipe.fallback_tracks = {1: 1}; pipe.next_fallback_track_id = -3
    pipe.person_buffers = {1: 1}; pipe.person_frame_counts = {1: 1}; pipe.person_scores = {1: 1}
    pipe.last_involved_ids = {1}; pipe.cached_people = [object()]
    pipe.last_state, pipe.last_confidence = "FIGHT DETECTED", 0.9
    assert pipe.fight_model_ready
    pipe.enter_idle()
    assert resets and pipe.cached_people == [] and pipe.person_buffers == {}
    assert pipe.last_state == "NORMAL" and pipe.last_confidence is None
    assert pipe.next_display_id == 1 and pipe.last_involved_ids == set()
    pipe.classifiers = {}
    assert not pipe.fight_model_ready
