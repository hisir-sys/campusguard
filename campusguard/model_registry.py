from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import torch
from torch import nn

Status = Callable[[str, str], None]

@dataclass(frozen=True)
class ModelProfile:
    key: str
    name: str
    description: str
    path: str
    architecture: str

MODEL_PROFILES = {
    "mc3": ("MC3-18", "Current CampusGuard MC3-18 classifier", "mc3"),
    "fdsc_mc3": ("FDSC MC3-18", "Fine-tuned surveillance fight classifier", "mc3"),
    "r3d": ("FDSC R3D-18", "3D ResNet surveillance classifier", "r3d"),
    "x3d": ("X3D-M", "Realtime X3D violence classifier", "x3d"),
}

class VideoClassifier:
    CLIP_LENGTH = 16
    STRIDE = 8
    INPUT_SIZE = (112, 112)

    def __init__(self, path: str, architecture: str, device: torch.device,
                 positive_class: int, threshold: float, status: Status, label: str):
        self.path = path
        self.architecture = architecture
        self.device = device
        self.positive_class = positive_class
        self.threshold = threshold
        self.status = status
        self.label = label
        self.model: nn.Module | None = None
        self.class_count = 0
        self.frames: list[np.ndarray] = []
        self.frame_count = 0
        self.last_probability = 0.0
        self.last_state = "MODEL NOT LOADED"
        self._load()

    def _load(self) -> None:
        path = Path(self.path).expanduser()
        if not self.path.strip() or not path.is_file():
            self.status(self.label, f"MODEL NOT LOADED — file not found: {path}")
            return
        try:
            if self.architecture == "mc3":
                from torchvision.models.video import mc3_18
                model = mc3_18(weights=None)
            elif self.architecture == "r3d":
                from torchvision.models.video import r3d_18
                model = r3d_18(weights=None)
            elif self.architecture == "x3d":
                try:
                    from pytorchvideo.models.x3d import create_x3d
                except ImportError as exc:
                    raise RuntimeError("X3D requires optional package 'pytorchvideo'.") from exc
                model = create_x3d(
                    input_clip_length=self.CLIP_LENGTH,
                    input_crop_size=112,
                    model_num_class=2,
                    norm=torch.nn.BatchNorm3d,
                    activation=torch.nn.ReLU,
                )
            else:
                raise ValueError(f"Unsupported architecture: {self.architecture}")

            checkpoint = torch.load(path, map_location="cpu", weights_only=True)
            state = checkpoint
            if isinstance(checkpoint, dict):
                state = checkpoint.get("state_dict", checkpoint.get("model_state_dict", checkpoint))
            if not isinstance(state, dict):
                raise ValueError("Checkpoint does not contain a state dictionary.")

            cleaned = {}
            for key, value in state.items():
                key = str(key)
                for prefix in ("module.", "model.", "backbone."):
                    if key.startswith(prefix):
                        key = key[len(prefix):]
                cleaned[key] = value

            classifier_key = next(
                (k for k in ("fc.weight", "blocks.5.proj.weight", "blocks.5.proj.classifier.weight")
                 if k in cleaned),
                None,
            )
            if classifier_key is None:
                classifier_key = next((k for k in cleaned if k.endswith(".weight") and getattr(cleaned[k], "ndim", 0) == 2), None)
            if classifier_key is None:
                raise ValueError("Could not locate a classifier weight in checkpoint.")

            self.class_count = int(cleaned[classifier_key].shape[0])
            if self.class_count not in (2, 3):
                raise ValueError(f"Expected 2 or 3 output classes, got {self.class_count}.")

            if hasattr(model, "fc"):
                model.fc = nn.Linear(model.fc.in_features, self.class_count)

            model.load_state_dict(cleaned, strict=False)
            model.to(self.device)
            model.eval()
            self.model = model
            self.last_state = "NORMAL"
            self.status(self.label, f"READY — {path.name}")
        except Exception as exc:
            self.model = None
            self.status(self.label, f"MODEL NOT LOADED — {exc}")

    def reset(self) -> None:
        self.frames.clear()
        self.frame_count = 0

    def update(self, threshold: float, positive_class: int) -> None:
        self.threshold = threshold
        self.positive_class = positive_class

    def add_frame(self, frame: np.ndarray) -> tuple[str, float] | None:
        if self.model is None:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb = cv2.resize(rgb, self.INPUT_SIZE, interpolation=cv2.INTER_AREA)
        self.frames.append(rgb)
        if len(self.frames) > self.CLIP_LENGTH:
            self.frames.pop(0)
        self.frame_count += 1
        if len(self.frames) < self.CLIP_LENGTH or self.frame_count % self.STRIDE:
            return None

        clip = np.stack(self.frames, axis=0)
        tensor = torch.from_numpy(clip).permute(3, 0, 1, 2).unsqueeze(0).float().to(self.device) / 255.0
        mean = torch.tensor((0.43216, 0.394666, 0.37645), device=self.device).view(1,3,1,1,1)
        std = torch.tensor((0.22803, 0.22145, 0.216989), device=self.device).view(1,3,1,1,1)
        tensor = (tensor - mean) / std
        with torch.inference_mode():
            probabilities = torch.softmax(self.model(tensor), dim=1)[0].detach().cpu().numpy()

        if self.class_count == 3:
            index = int(np.argmax(probabilities))
            confidence = float(probabilities[index])
            state = ("NORMAL", "POSSIBLE ALTERCATION", "FIGHT DETECTED")[index]
            if confidence < self.threshold:
                state = "NORMAL"
        else:
            index = min(max(self.positive_class, 0), 1)
            confidence = float(probabilities[index])
            state = "FIGHT DETECTED" if confidence >= self.threshold else "NORMAL"
            if self.class_count == 2 and self.threshold <= confidence < 0.85:
                state = "POSSIBLE ALTERCATION"

        self.last_probability = confidence
        self.last_state = state
        return state, confidence

class EnhancedEnsemble:
    """CampusGuard Enhanced: weighted consensus across every loaded classifier."""

    def __init__(self, classifiers: list[VideoClassifier]):
        self.classifiers = classifiers

    def add_frame(self, frame: np.ndarray) -> tuple[str, float] | None:
        predictions = []
        for classifier in self.classifiers:
            result = classifier.add_frame(frame)
            if result is not None:
                predictions.append(result)
        if not predictions:
            return None
        fight_scores = [
            confidence if state != "NORMAL" else max(0.0, confidence - 0.5)
            for state, confidence in predictions
        ]
        score = float(np.mean(fight_scores))
        if any(state == "FIGHT DETECTED" for state, _ in predictions) and score >= 0.65:
            return "FIGHT DETECTED", score
        if score >= 0.65:
            return "POSSIBLE ALTERCATION", score
        return "NORMAL", score
