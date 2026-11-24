# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
"""The two newer fight models (SlowFast, R(2+1)D) can be loaded and swapped in."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from campusguard.model_adapters import get_model_input_adapter
from campusguard.model_registry import MODEL_PROFILES, VideoClassifier
from campusguard.settings import AppSettings

HAS_PYTORCHVIDEO = importlib.util.find_spec("pytorchvideo") is not None


def frames(count: int, height: int = 90, width: int = 160) -> list[np.ndarray]:
    rng = np.random.default_rng(1)
    return [rng.integers(0, 255, (height, width, 3), dtype=np.uint8) for _ in range(count)]


class ExtraModelTests(unittest.TestCase):
    def test_settings_accept_each_model_and_reject_unknown(self):
        for key in ("fdsc_mc3", "slowfast", "r2plus1d"):
            self.assertEqual(AppSettings.from_dict({"violence_model": key}).violence_model, key)
        self.assertEqual(AppSettings.from_dict({"violence_model": "nope"}).violence_model, "fdsc_mc3")

    def test_fight_is_class_one_for_the_new_models(self):
        for key in ("slowfast", "r2plus1d"):
            profile = MODEL_PROFILES[key]
            self.assertEqual(profile.class_labels, ("noFight", "fight"))
            self.assertEqual(profile.fight_class, 1)
            self.assertTrue(profile.semantic_verified)
        self.assertEqual(MODEL_PROFILES["fdsc_mc3"].fight_class, 0)

    def test_r2plus1d_input(self):
        adapter = get_model_input_adapter("r2plus1d")
        tensor = adapter.prepare(frames(16), torch.device("cpu"))
        self.assertEqual(tuple(tensor.shape), (1, 3, 16, 224, 224))

    def test_slowfast_input_is_two_pathways(self):
        adapter = get_model_input_adapter("slowfast")
        self.assertEqual(adapter.span_frames, 64)
        slow, fast = adapter.prepare(frames(64), torch.device("cpu"))
        self.assertEqual(tuple(fast.shape), (1, 3, 32, 224, 224))
        self.assertEqual(tuple(slow.shape), (1, 3, 8, 224, 224))

    def test_clip_buffer_keeps_small_frames(self):
        adapter = get_model_input_adapter("slowfast")
        big = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.assertEqual(min(adapter.shrink(big).shape[:2]), 256)
        self.assertEqual(adapter.shrink(np.zeros((100, 200, 3), dtype=np.uint8)).shape, (100, 200, 3))

    def _classifier(self, key: str, state: dict) -> VideoClassifier:
        folder = tempfile.mkdtemp()
        path = Path(folder) / "model.pth"
        torch.save({k: v.half() if v.is_floating_point() else v for k, v in state.items()}, path)
        messages: list[str] = []
        classifier = VideoClassifier(MODEL_PROFILES[key], str(path), torch.device("cpu"), 0.65, lambda _k, m: messages.append(m))
        self.assertTrue(classifier.ready, messages)
        return classifier

    def test_r2plus1d_loads_and_predicts(self):
        from campusguard.model_registry import VideoClassifier as V
        model = V._build_architecture("r2plus1d")
        state = {"backbone." + k: v for k, v in model.state_dict().items()}   # the training notebooks saved this prefix
        classifier = self._classifier("r2plus1d", state)
        result = None
        for i, frame in enumerate(frames(16)):
            result = classifier.add_frame(frame, timestamp=i / 15) or result
        self.assertIsNotNone(result)
        self.assertTrue(0.0 <= result[1] <= 1.0)

    @unittest.skipUnless(HAS_PYTORCHVIDEO, "pytorchvideo is not installed")
    def test_slowfast_loads_and_predicts(self):
        from campusguard.model_registry import VideoClassifier as V
        model = V._build_architecture("slowfast")
        state = {"backbone." + k: v for k, v in model.state_dict().items()}
        classifier = self._classifier("slowfast", state)
        self.assertAlmostEqual(classifier.MAX_CLIP_SECONDS, 6.4, places=1)
        result = None
        for i, frame in enumerate(frames(64)):
            result = classifier.add_frame(frame, timestamp=i / 15) or result
        self.assertIsNotNone(result)
        self.assertTrue(0.0 <= result[1] <= 1.0)

    def test_busy_pc_still_gets_evenly_spaced_clips(self):
        """A 30 fps camera analysed only every 4th frame: skipped frames still reach the clip buffer."""
        from campusguard.model_registry import VideoClassifier as V
        model = V._build_architecture("r2plus1d")
        state = {"backbone." + k: v for k, v in model.state_dict().items()}
        classifier = self._classifier("r2plus1d", state)
        seen: list[float] = []
        classifier._classify_clip = lambda clip: seen.append(classifier.frame_times[-1] - classifier.frame_times[0]) or ("NORMAL", 0.1)
        frame = frames(1)[0]
        for i in range(150):                    # 5 seconds at 30 fps
            t = i / 30.0
            if i % 4 == 0:
                classifier.add_frame(frame, timestamp=t)
            else:
                classifier.buffer_frame(frame, timestamp=t)
        self.assertTrue(seen, "no check ran")
        self.assertFalse(classifier.behind)
        for span in seen:                       # 16 frames at 15 fps = 1.0 s, never stretched
            self.assertLess(span, 1.3)

    def test_gap_in_the_stream_restarts_the_clip(self):
        from campusguard.model_registry import VideoClassifier as V
        model = V._build_architecture("r2plus1d")
        state = {"backbone." + k: v for k, v in model.state_dict().items()}
        classifier = self._classifier("r2plus1d", state)
        classifier._classify_clip = lambda clip: ("NORMAL", 0.1)
        frame = frames(1)[0]
        for i in range(10):
            classifier.buffer_frame(frame, timestamp=i / 15.0)
        classifier.buffer_frame(frame, timestamp=5.0)       # a long stall (a check was running)
        self.assertEqual(len(classifier.frames), 1)

    def test_missing_file_reports_not_loaded(self):
        messages: list[str] = []
        classifier = VideoClassifier(MODEL_PROFILES["r2plus1d"], "does/not/exist.pth", torch.device("cpu"), 0.65, lambda _k, m: messages.append(m))
        self.assertFalse(classifier.ready)
        self.assertTrue(any("MODEL NOT LOADED" in m for m in messages))


if __name__ == "__main__":
    unittest.main()
