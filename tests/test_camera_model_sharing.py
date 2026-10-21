import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch

from campusguard.ai_pipeline import VisionPipeline, _SHARED_YOLO_MODELS
from campusguard.model_registry import (
    MODEL_CACHE_LOCK,
    MODEL_PROFILES,
    VideoClassifier,
    _SHARED_VIDEO_MODELS,
    model_inference_lock,
)


class SharedCameraModelTests(unittest.TestCase):
    def test_video_classifier_weights_are_shared_but_stream_state_is_not(self):
        profile = MODEL_PROFILES["mc3"]
        path = "tests/test-shared-camera-classifier.pth"
        key = (profile.architecture, str(Path(path).resolve()), str(torch.device("cpu")), None)
        with MODEL_CACHE_LOCK:
            _SHARED_VIDEO_MODELS.pop(key, None)

        fake_model = torch.nn.Linear(1, 1)
        load_calls = []

        def fake_load(instance, _path=None):
            load_calls.append(instance)
            instance.model = fake_model
            instance.class_count = 2
            instance.last_state = "NORMAL"

        try:
            with patch.object(VideoClassifier, "_load_uncached", fake_load):
                first = VideoClassifier(profile, path, torch.device("cpu"), 0.65, lambda *_: None)
                second = VideoClassifier(profile, path, torch.device("cpu"), 0.65, lambda *_: None)

            self.assertIs(first.model, second.model)
            self.assertEqual(len(load_calls), 1)
            self.assertIs(model_inference_lock(first.model), model_inference_lock(second.model))

            first.frames.append(torch.zeros(1).numpy())
            first.last_probability = 0.91
            self.assertEqual(second.frames, [])
            self.assertEqual(second.last_probability, 0.0)
        finally:
            with MODEL_CACHE_LOCK:
                _SHARED_VIDEO_MODELS.pop(key, None)

    def test_yolo_weights_are_shared_for_identical_path_task_and_device(self):
        load_calls = []

        class FakeYOLO:
            def __init__(self, model_path, task):
                self.model_path = model_path
                self.task = task
                load_calls.append((model_path, task))

            def to(self, device):
                self.device = device
                return self

        with tempfile.TemporaryDirectory() as directory:
            model_file = Path(directory) / "fake-yolo.pt"
            model_file.write_bytes(b"test-only-placeholder")
            path = str(model_file.resolve())
            cache_key = ("detect", path, str(torch.device("cpu")), model_file.stat().st_mtime_ns)
            with MODEL_CACHE_LOCK:
                _SHARED_YOLO_MODELS.pop(cache_key, None)

            first_pipeline = object.__new__(VisionPipeline)
            first_pipeline.device = torch.device("cpu")
            first_pipeline.status = lambda *_: None
            second_pipeline = object.__new__(VisionPipeline)
            second_pipeline.device = torch.device("cpu")
            second_pipeline.status = lambda *_: None

            try:
                with patch.dict(sys.modules, {"ultralytics": SimpleNamespace(YOLO=FakeYOLO)}):
                    first = first_pipeline._load_yolo("detector", path, "detect")
                    second = second_pipeline._load_yolo("detector", path, "detect")

                self.assertIs(first, second)
                self.assertEqual(len(load_calls), 1)
            finally:
                with MODEL_CACHE_LOCK:
                    _SHARED_YOLO_MODELS.pop(cache_key, None)


if __name__ == "__main__":
    unittest.main()
