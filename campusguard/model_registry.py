from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import torch
from torch import nn

from campusguard.model_manifest import MODEL_MANIFESTS
from campusguard.model_adapters import get_model_input_adapter

Status = Callable[[str, str], None]

@dataclass(frozen=True)
class ModelProfile:
    key: str
    name: str
    description: str
    architecture: str
    path_setting: str
    class_labels: tuple[str, ...]
    fight_class: int | None
    preprocessing: str
    semantic_status: str
    source_note: str

    @property
    def class_count(self) -> int:
        return len(self.class_labels)

    @property
    def semantic_verified(self) -> bool:
        return self.fight_class is not None and self.semantic_status == "verified"


MODEL_PROFILES: dict[str, ModelProfile] = {
    key: ModelProfile(
        key=manifest.key,
        name=manifest.name,
        description=manifest.description,
        architecture=manifest.architecture,
        path_setting=manifest.path_setting,
        class_labels=manifest.class_labels,
        fight_class=manifest.fight_class,
        preprocessing=manifest.preprocessing,
        semantic_status=manifest.semantic_status,
        source_note=manifest.source_note,
    )
    for key, manifest in MODEL_MANIFESTS.items()
}

class VideoClassifier:
    CLIP_LENGTH = 16
    INFERENCE_STRIDE = 8
    INPUT_SIZE = (112, 112)

    def __init__(
        self,
        profile: ModelProfile,
        path: str,
        device: torch.device,
        threshold: float,
        status: Status,
        fight_class_override: int | None = None,
    ) -> None:
        self.profile, self.path, self.device = profile, path, device
        self.adapter = get_model_input_adapter(profile.key)
        self.threshold, self.status = threshold, status
        self.fight_class: int | None = (
            fight_class_override
            if fight_class_override is not None
            else profile.fight_class
        )
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

    @property
    def semantic_ready(self) -> bool:
        """True only when the checkpoint is loaded and its fight class is verified."""
        return self.ready and self.fight_class is not None

    @property
    def semantic_label(self) -> str:
        if self.fight_class is None:
            return "UNVERIFIED"
        if 0 <= self.fight_class < len(self.profile.class_labels):
            return self.profile.class_labels[self.fight_class]
        return f"class_{self.fight_class}"

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

            checkpoint = self._load_checkpoint(path)
            state = self._extract_state_dict(checkpoint)
            cleaned = self._clean_state_dict(state)

            classifier_key = self._find_classifier_key(cleaned)
            if classifier_key is None:
                raise ValueError("Could not locate a classifier weight in checkpoint.")
            classifier_weight = cleaned[classifier_key]
            if getattr(classifier_weight, "ndim", 0) != 2:
                raise ValueError(f"Classifier weight '{classifier_key}' is not a 2D tensor.")

            self.class_count = int(classifier_weight.shape[0])
            if self.class_count not in (2, 3):
                raise ValueError(f"Checkpoint has {self.class_count} output classes; expected 2 or 3.")

            if self.class_count != self.profile.class_count:
                raise ValueError(
                    f"Checkpoint has {self.class_count} classes, but the manifest expects {self.profile.class_count}."
                )
            if self.fight_class is not None and not (0 <= self.fight_class < self.class_count):
                raise ValueError(
                    f"Manifest fight class {self.fight_class} is outside the checkpoint's {self.class_count} classes."
                )

            self._resize_classifier(model, self.class_count)
            missing, unexpected = model.load_state_dict(cleaned, strict=False)
            if missing or unexpected:
                missing_text = ", ".join(missing[:8])
                unexpected_text = ", ".join(unexpected[:8])
                details = []
                if missing_text:
                    details.append(f"missing={missing_text}")
                if unexpected_text:
                    details.append(f"unexpected={unexpected_text}")
                raise ValueError("Checkpoint architecture mismatch (" + "; ".join(details) + ").")
            model.to(self.device)
            model.eval()
            self.model = model
            self.last_state = "NORMAL"
            semantic = f"fight class={self.fight_class}" if self.fight_class is not None else "fight class=UNVERIFIED"
            self.status(self.profile.key, f"READY — {self.profile.name}, {self.class_count} classes ({path.name}); {semantic}")
            if self.fight_class is None:
                self.status(self.profile.key, "SEMANTIC MAPPING NOT VERIFIED — model will not produce violence decisions.")
        except Exception as error:
            self.model = None
            self.last_state = "MODEL NOT LOADED"
            self.status(self.profile.key, f"MODEL NOT LOADED — {error}")


    @staticmethod
    def _load_checkpoint(path: Path):
        """Load trusted CampusGuard checkpoints with PyTorch's safe unpickler."""
        if torch.__version__ >= "2.6" and path.suffix.lower() == ".pt":
            try:
                from numpy._core.multiarray import scalar
            except ImportError:
                from numpy.core.multiarray import scalar

            # The verified X3D checkpoint contains NumPy scalar metadata.
            # Allowlist only that specific type instead of disabling PyTorch's
            # weights-only safety mechanism for arbitrary checkpoint objects.
            with torch.serialization.safe_globals([scalar]):
                return torch.load(path, map_location="cpu", weights_only=True)

        return torch.load(path, map_location="cpu", weights_only=True)

    @staticmethod
    def _extract_state_dict(checkpoint) -> dict:
        if not isinstance(checkpoint, dict):
            raise ValueError("Checkpoint does not contain a state dictionary.")

        for key in ("state_dict", "model_state_dict", "model"):
            candidate = checkpoint.get(key)
            if isinstance(candidate, dict):
                return candidate

        # A plain state_dict is itself a mapping of parameter names to tensors.
        if checkpoint and all(isinstance(value, torch.Tensor) for value in checkpoint.values()):
            return checkpoint

        raise ValueError("Checkpoint does not contain a usable state dictionary.")

    @staticmethod
    def _clean_state_dict(state: dict) -> dict[str, torch.Tensor]:
        cleaned: dict[str, torch.Tensor] = {}
        for raw_key, value in state.items():
            if not isinstance(value, torch.Tensor):
                continue
            key = str(raw_key)
            # Some exporters stack wrappers such as model.module.model.
            changed = True
            while changed:
                changed = False
                for prefix in ("module.", "model.", "state_dict."):
                    if key.startswith(prefix):
                        key = key[len(prefix):]
                        changed = True
            cleaned[key] = value

        if not cleaned:
            raise ValueError("Checkpoint state dictionary contains no tensor parameters.")
        return cleaned

    def _create_x3d(self):
        try:
            from pytorchvideo.models.x3d import create_x3d
        except ImportError as exc:
            raise RuntimeError("X3D requires pytorchvideo. Install dependencies from requirements.txt.") from exc
        return create_x3d(input_channel=3, input_clip_length=16, input_crop_size=224, model_num_class=2, width_factor=2.0)

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

    def update(self, threshold: float) -> None:
        self.threshold = threshold

    def _classify_clip(self, clip: np.ndarray) -> tuple[str, float]:
        tensor = self.adapter.prepare(clip, self.device)

        with torch.inference_mode():
            logits = self.model(tensor)
            if isinstance(logits, (tuple, list)):
                logits = logits[0]
            probabilities = torch.softmax(logits, dim=1)[0].detach().cpu().numpy()

        if self.fight_class is None:
            raise RuntimeError(
                f"{self.profile.name} has no verified fight-class mapping."
            )

        fight_probability = float(probabilities[self.fight_class])

        if self.class_count == 3:
            other_classes = [
                index for index in range(self.class_count)
                if index != self.fight_class
            ]
            non_fight_probability = float(probabilities[other_classes].sum())

            if fight_probability >= self.threshold:
                state = "FIGHT DETECTED"
            elif (
                fight_probability >= self.threshold * 0.80
                and non_fight_probability < fight_probability
            ):
                state = "POSSIBLE ALTERCATION"
            else:
                state = "NORMAL"
        else:
            if fight_probability >= self.threshold:
                state = "FIGHT DETECTED"
            elif fight_probability >= self.threshold * 0.80:
                state = "POSSIBLE ALTERCATION"
            else:
                state = "NORMAL"

        confidence = fight_probability

        self.last_probability, self.last_state = confidence, state
        return state, confidence

    def add_frame(self, frame: np.ndarray) -> tuple[str, float] | None:
        """Keep a legacy/global stream for callers that still need one."""
        if self.model is None or self.fight_class is None:
            return None
        # Keep frames in their original BGR form. The model adapter owns
        # color conversion, resizing, and normalization so every model uses
        # one consistent preprocessing path.
        self.frames.append(frame.copy())
        if len(self.frames) > self.CLIP_LENGTH:
            self.frames.pop(0)
        self.frame_count += 1
        if len(self.frames) < self.CLIP_LENGTH or self.frame_count % self.INFERENCE_STRIDE:
            return None
        return self._classify_clip(np.asarray(self.frames))

    def classify_clip(self, frames: list[np.ndarray]) -> tuple[str, float]:
        """Classify one temporal ROI clip for person-specific attribution."""
        if self.model is None or self.fight_class is None:
            raise ValueError("A loaded classifier with a verified fight-class mapping is required.")
        if len(frames) < self.CLIP_LENGTH:
            raise ValueError("A loaded classifier and 16-frame clip are required.")
        # The model adapter owns color conversion, resizing, and normalization.
        return self._classify_clip(np.asarray(frames[-self.CLIP_LENGTH:]))

class EnhancedEnsemble:
    """CampusGuard Enhanced combines every configured classifier that actually loads."""
    def __init__(self, classifiers: list[VideoClassifier], threshold: float) -> None:
        self.classifiers, self.threshold = classifiers, threshold
        self.last_state = "MODEL NOT LOADED"
        self.last_confidence: float | None = None

    @property
    def ready(self) -> bool:
        return any(model.ready for model in self.classifiers)

    def update(self, threshold: float) -> None:
        self.threshold = threshold
        for model in self.classifiers:
            model.update(threshold)

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
