from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import torch


@dataclass(frozen=True)
class ModelInputAdapter:
    """Explicit input contract for one temporal violence model."""

    key: str
    clip_length: int
    input_size: tuple[int, int]
    mean: tuple[float, float, float]
    std: tuple[float, float, float]
    notes: str
    resize_size: tuple[int, int] | None = None

    def _prepare_frame(self, frame: np.ndarray) -> np.ndarray:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        if self.resize_size is None:
            return cv2.resize(
                rgb,
                self.input_size,
                interpolation=cv2.INTER_AREA,
            )

        resized = cv2.resize(
            rgb,
            self.resize_size,
            interpolation=cv2.INTER_AREA,
        )
        target_width, target_height = self.input_size
        height, width = resized.shape[:2]
        if width < target_width or height < target_height:
            raise ValueError(
                f"{self.key} preprocessing produced {width}x{height}, "
                f"smaller than required {target_width}x{target_height}."
            )

        left = (width - target_width) // 2
        top = (height - target_height) // 2
        return resized[top:top + target_height, left:left + target_width]

    def prepare(self, frames: list[np.ndarray] | np.ndarray, device: torch.device) -> torch.Tensor:
        if len(frames) < self.clip_length:
            raise ValueError(
                f"{self.key} requires {self.clip_length} frames; received {len(frames)}."
            )

        prepared: list[np.ndarray] = []
        for frame in list(frames)[-self.clip_length:]:
            if frame is None or frame.size == 0:
                raise ValueError(f"{self.key} received an empty video frame.")
            prepared.append(self._prepare_frame(frame))

        tensor = (
            torch.from_numpy(np.stack(prepared, axis=0))
            .permute(3, 0, 1, 2)
            .unsqueeze(0)
            .float()
            .to(device)
            / 255.0
        )

        mean = torch.tensor(self.mean, device=device).view(1, 3, 1, 1, 1)
        std = torch.tensor(self.std, device=device).view(1, 3, 1, 1, 1)
        return (tensor - mean) / std


KINETICS_MEAN = (0.43216, 0.394666, 0.37645)
KINETICS_STD = (0.22803, 0.22145, 0.216989)

MODEL_INPUT_ADAPTERS: dict[str, ModelInputAdapter] = {
    "mc3": ModelInputAdapter(
        key="mc3",
        clip_length=16,
        input_size=(112, 112),
        mean=KINETICS_MEAN,
        std=KINETICS_STD,
        notes="CampusGuard MC3-18 contract: RGB, 16 frames, 112x112, Kinetics-style normalization.",
    ),
    "fdsc_mc3": ModelInputAdapter(
        key="fdsc_mc3",
        clip_length=16,
        input_size=(112, 112),
        mean=KINETICS_MEAN,
        std=KINETICS_STD,
        resize_size=(171, 128),
        notes=(
            "FDSC MC3-18 published transform: RGB, resize to 171x128, "
            "center-crop 112x112, /255, Kinetics-style normalization."
        ),
    ),
    "r3d": ModelInputAdapter(
        key="r3d",
        clip_length=16,
        input_size=(112, 112),
        mean=KINETICS_MEAN,
        std=KINETICS_STD,
        resize_size=(171, 128),
        notes=(
            "FDSC R3D-18 published transform: RGB, resize to 171x128, "
            "center-crop 112x112, /255, Kinetics-style normalization."
        ),
    ),
    "x3d": ModelInputAdapter(
        key="x3d",
        clip_length=16,
        input_size=(224, 224),
        mean=(0.45, 0.45, 0.45),
        std=(0.225, 0.225, 0.225),
        notes="Verified X3D-M contract: 16 RGB frames, 224x224, mean=0.45, std=0.225.",
    ),
}


def get_model_input_adapter(key: str) -> ModelInputAdapter:
    try:
        return MODEL_INPUT_ADAPTERS[key]
    except KeyError as exc:
        raise KeyError(f"No input adapter registered for violence model: {key}") from exc
