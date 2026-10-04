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
    architecture: str
    path_setting: str | None

MODEL_PROFILES: dict[str, ModelProfile] = {
    "mc3": ModelProfile("mc3", "Current MC3-18", "CampusGuard's existing MC3-18 temporal fight classifier.", "mc3", "fight_model_path"),
    "fdsc_mc3": ModelProfile("fdsc_mc3", "FDSC MC3-18", "FDSC fine-tuned MC3-18 surveillance classifier.", "mc3", "fdsc_mc3_model_path"),
    "r3d": ModelProfile("r3d", "FDSC R3D-18", "FDSC R3D-18 3D ResNet surveillance classifier.", "r3d", "r3d_model_path"),
    "x3d": ModelProfile("x3d", "X3D-M", "Realtime X3D-M violence classifier.", "x3d", "x3d_model_path"),
}

class VideoClassifier:
    CLIP_LENGTH = 16
    INFERENCE_STRIDE = 8
    INPUT_SIZE = (112, 112)

    def __init__(self, profile: ModelProfile, path: str, device: torch.device, positive_class: int, threshold: float, status: Status) -> None:
        self.profile, self.path, self.device = profile, path, device
        self.positive_class, self.threshold, self.status = positive_class, threshold, status
        self.model: nn.Module | torch.jit.ScriptModule | None = None
        self.class_count = 0
        self.frames: list[np.ndarray] = []
        self.frame_count = 0
        self.last_probability = 0.0
        self.last_state = "MODEL NOT LOADED"
        self._load()

    @property
    def ready(self) -> bool:
        return self.model is not None

    def _load(self) -> None:
        path = Path(self.path).expanduser()
        if not self.path.strip() or not path.is_file():
            self.status(self.profile.key, f"MODEL NOT LOADED — file not found: {path}")
            return
        try:
            if self.profile.architecture == "mc3":
                from torchvision.models.video import mc3_18
                model = mc3_18(weights=None)
            elif self.profile.architecture == "r3d":
                from torchvision.models.video import r3d_18
                model = r3d_18(weights=None)
            elif self.profile.architecture == "x3d":
                model = self._create_x3d()
            else:
                raise ValueError(f"Unsupported architecture: {self.profile.architecture}")

            checkpoint = torch.load(path, map_location="cpu", weights_only=True)
            state = checkpoint.get("state_dict", checkpoint.get("model_state_dict", checkpoint)) if isinstance(checkpoint, dict) else checkpoint
            if not isinstance(state, dict):
                raise ValueError("Checkpoint does not contain a state dictionary.")

            cleaned: dict[str, torch.Tensor] = {}
            for key, value in state.items():
                key = str(key)
                for prefix in ("module.", "model."):
                    if key.startswith(prefix):
                        key = key[len(prefix):]
                cleaned[key] = value

            classifier_key = self._find_classifier_key(cleaned)
            if classifier_key is None:
                raise ValueError("Could not locate a classifier weight in checkpoint.")
            self.class_count = int(cleaned[classifier_key].shape[0])
            if self.class_count not in (2, 3):
                raise ValueError(f"Checkpoint has {self.class_count} output classes; expected 2 or 3.")

            self._resize_classifier(model, self.class_count)
            model.load_state_dict(cleaned, strict=False)
            model.to(self.device)
            model.eval()
            self.model = model
            self.last_state = "NORMAL"
            self.status(self.profile.key, f"READY — {self.profile.name}, {self.class_count} classes ({path.name})")
        except Exception as error:
            self.model = None
            self.last_state = "MODEL NOT LOADED"
            self.status(self.profile.key, f"MODEL NOT LOADED — {error}")

    def _create_x3d(self):
        try:
            from pytorchvideo.models.x3d import create_x3d
        except ImportError as exc:
            raise RuntimeError("X3D requires pytorchvideo. Install dependencies from requirements.txt.") from exc
        return create_x3d(input_channel=3, input_clip_length=16, input_crop_size=112, model_num_class=2, width_factor=2.0)

    @staticmethod
    def _find_classifier_key(state: dict[str, torch.Tensor]) -> str | None:
        for key in ("fc.weight", "blocks.5.proj.weight", "blocks.5.proj.classifier.weight", "blocks.6.proj.weight"):
            if key in state and getattr(state[key], "ndim", 0) == 2:
                return key
        candidates = [key for key, value in state.items() if key.endswith(".weight") and getattr(value, "ndim", 0) == 2]
        return candidates[-1] if candidates else None

    @staticmethod
    def _resize_classifier(model: nn.Module, class_count: int) -> None:
        if hasattr(model, "fc") and isinstance(model.fc, nn.Linear):
            model.fc = nn.Linear(model.fc.in_features, class_count)
            return
        if hasattr(model, "blocks"):
            for block in reversed(model.blocks):
                if hasattr(block, "proj") and isinstance(block.proj, nn.Linear):
                    block.proj = nn.Linear(block.proj.in_features, class_count)
                    return
        raise ValueError("Unsupported classifier head for this checkpoint architecture.")

    def reset(self) -> None:
        self.frames.clear()
        self.frame_count = 0
        self.last_probability = 0.0
        self.last_state = "NORMAL" if self.ready else "MODEL NOT LOADED"

    def update(self, threshold: float, positive_class: int) -> None:
        self.threshold, self.positive_class = threshold, positive_class

    def _classify_clip(self, clip: np.ndarray) -> tuple[str, float]:
        tensor_clip = np.stack(clip, axis=0)
        tensor = torch.from_numpy(tensor_clip).permute(3, 0, 1, 2).unsqueeze(0).float().to(self.device) / 255.0
        mean = torch.tensor((0.43216, 0.394666, 0.37645), device=self.device).view(1, 3, 1, 1, 1)
        std = torch.tensor((0.22803, 0.22145, 0.216989), device=self.device).view(1, 3, 1, 1, 1)
        tensor = (tensor - mean) / std

        with torch.inference_mode():
            logits = self.model(tensor)
            if isinstance(logits, (tuple, list)):
                logits = logits[0]
            probabilities = torch.softmax(logits, dim=1)[0].detach().cpu().numpy()

        if self.class_count == 3:
            # The classifier's confidence is exposed as a violence score:
            # possible-altercation probability contributes half, while fight
            # probability is the primary positive signal.
            possible_probability = float(probabilities[1])
            fight_probability = float(probabilities[2])
            confidence = min(1.0, possible_probability + fight_probability)
            if fight_probability >= self.threshold:
                state = "FIGHT DETECTED"
            elif confidence >= self.threshold:
                state = "POSSIBLE ALTERCATION"
            else:
                state = "NORMAL"
        else:
            index = min(max(self.positive_class, 0), 1)
            confidence = float(probabilities[index])
            state = "FIGHT DETECTED" if confidence >= self.threshold else "NORMAL"
            if self.threshold <= confidence < 0.85:
                state = "POSSIBLE ALTERCATION"

        self.last_probability, self.last_state = confidence, state
        return state, confidence

    def add_frame(self, frame: np.ndarray) -> tuple[str, float] | None:
        """Keep a legacy/global stream for callers that still need one."""
        if self.model is None:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self.frames.append(cv2.resize(rgb, self.INPUT_SIZE, interpolation=cv2.INTER_AREA))
        if len(self.frames) > self.CLIP_LENGTH:
            self.frames.pop(0)
        self.frame_count += 1
        if len(self.frames) < self.CLIP_LENGTH or self.frame_count % self.INFERENCE_STRIDE:
            return None
        return self._classify_clip(np.asarray(self.frames))

    def classify_clip(self, frames: list[np.ndarray]) -> tuple[str, float]:
        """Classify one temporal ROI clip for person-specific attribution."""
        if self.model is None or len(frames) < self.CLIP_LENGTH:
            raise ValueError("A loaded classifier and 16-frame clip are required.")
        prepared = []
        for frame in frames[-self.CLIP_LENGTH:]:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            prepared.append(cv2.resize(rgb, self.INPUT_SIZE, interpolation=cv2.INTER_AREA))
        return self._classify_clip(np.asarray(prepared))

class EnhancedEnsemble:
    """CampusGuard Enhanced combines every configured classifier that actually loads."""
    def __init__(self, classifiers: list[VideoClassifier], threshold: float) -> None:
        self.classifiers, self.threshold = classifiers, threshold
        self.last_state = "MODEL NOT LOADED"
        self.last_confidence: float | None = None

    @property
    def ready(self) -> bool:
        return any(model.ready for model in self.classifiers)

    def update(self, threshold: float, positive_class: int) -> None:
        self.threshold = threshold
        for model in self.classifiers:
            model.update(threshold, positive_class)

    def add_frame(self, frame: np.ndarray) -> tuple[str, float] | None:
        predictions = []
        for classifier in self.classifiers:
            result = classifier.add_frame(frame)
            if result is not None:
                predictions.append(result)
        if not predictions:
            return None
        scores = [confidence if state == "FIGHT DETECTED" else confidence * 0.75 if state == "POSSIBLE ALTERCATION" else max(0.0, confidence * 0.25) for state, confidence in predictions]
        score = float(np.mean(scores))
        if score >= max(0.65, self.threshold) and any(state == "FIGHT DETECTED" for state, _ in predictions):
            state = "FIGHT DETECTED"
        elif score >= self.threshold:
            state = "POSSIBLE ALTERCATION"
        else:
            state = "NORMAL"
        self.last_state, self.last_confidence = state, score
        return state, score
