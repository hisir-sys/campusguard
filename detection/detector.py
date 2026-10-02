"""Shared-model detection coordinator for CampusGuard."""
import threading
import time
from collections import deque
from pathlib import Path
from .preprocessing import make_clip
from .temporal_model import TemporalFightModel
from config import SEQUENCE_LENGTH, WARNING_THRESHOLD, CRITICAL_THRESHOLD, INFERENCE_INTERVAL, ENABLE_YOLO, YOLO_MODEL, TEMPORAL_MODEL


class CampusGuardDetector:
    _model_lock = threading.Lock()
    _temporal = None
    _yolo = None
    _load_error = None

    def __init__(self):
        self.frames = deque(maxlen=SEQUENCE_LENGTH)
        self.last_inference = 0.0
        self.last_result = {"label": "warming_up", "fight_probability": 0.0, "no_fight_probability": 1.0, "severity": "normal", "source": "temporal_mc3"}
        self._ensure_models()

    @classmethod
    def _ensure_models(cls):
        with cls._model_lock:
            if cls._temporal is None and Path(TEMPORAL_MODEL).exists():
                try:
                    cls._temporal = TemporalFightModel(TEMPORAL_MODEL)
                except Exception as exc:
                    cls._load_error = str(exc)
                    print(f"[CampusGuard] Temporal model failed: {exc}")
            if ENABLE_YOLO and cls._yolo is None and Path(YOLO_MODEL).exists():
                try:
                    from .yolo_detector import YOLOViolenceDetector
                    cls._yolo = YOLOViolenceDetector(YOLO_MODEL)
                except Exception as exc:
                    print(f"[CampusGuard] YOLO disabled: {exc}")

    def reset(self):
        self.frames.clear()
        self.last_inference = 0.0
        self.last_result = {"label": "warming_up", "fight_probability": 0.0, "no_fight_probability": 1.0, "severity": "normal", "source": "temporal_mc3"}

    def process(self, frame):
        self.frames.append(frame)
        now = time.time()
        if self._temporal and len(self.frames) == SEQUENCE_LENGTH and now - self.last_inference >= INFERENCE_INTERVAL:
            self.last_inference = now
            clip = make_clip(list(self.frames))
            with self._model_lock:
                result = self._temporal.predict(clip)
            p = result["fight_probability"]
            severity = "critical" if p >= CRITICAL_THRESHOLD else "warning" if p >= WARNING_THRESHOLD else "normal"
            self.last_result = {**result, "severity": severity, "source": "temporal_mc3"}

        if self._yolo:
            try:
                with self._model_lock:
                    self.last_result["yolo_detections"] = self._yolo.predict(frame)
            except Exception:
                self.last_result["yolo_detections"] = []
        return dict(self.last_result)

    @classmethod
    def model_status(cls):
        cls._ensure_models()
        return {
            "temporal_loaded": cls._temporal is not None,
            "yolo_loaded": cls._yolo is not None,
            "device": str(cls._temporal.device) if cls._temporal else "unavailable",
            "error": cls._load_error,
        }
