# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
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
    # Newer models: scale the SHORTER side to this many pixels (keeps the picture's shape), then crop.
    resize_short_side: int | None = None
    # Take every Nth analysed frame when building a clip (the model was trained with this gap).
    frame_step: int = 1
    # "single": one clip tensor. "slowfast": [slow, fast] where slow = every 4th frame of fast.
    pathway: str = "single"
    # Analysed frames between two checks; None = half a window (never rarer than the legacy 8).
    check_every: int | None = None
    # Normalisation constants above are on a 0..1 scale (0..255 values divided by 255).

    @property
    def span_frames(self) -> int:
        """How many consecutive analysed frames one check looks at."""
        return self.clip_length * self.frame_step

    @property
    def inference_stride(self) -> int:
        """Analysed frames between two checks: half a window, never rarer than the old 8."""
        if self.check_every is not None:
            return self.check_every
        return max(8, self.span_frames // 2) if self.frame_step > 1 else 8

    def shrink(self, frame: np.ndarray) -> np.ndarray:
        """Copy of a frame for the clip buffer. Newer models keep only a small version so 64 buffered
        frames of a 1080p camera do not cost hundreds of megabytes."""
        if self.resize_short_side is None:
            return frame.copy()
        height, width = frame.shape[:2]
        scale = self.resize_short_side / min(height, width)
        if scale >= 1.0:
            return frame.copy()
        return cv2.resize(frame, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)

    def _prepare_frame(self, frame: np.ndarray) -> np.ndarray:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        if self.resize_short_side is not None:
            height, width = rgb.shape[:2]
            scale = self.resize_short_side / min(height, width)
            if scale != 1.0:
                rgb = cv2.resize(rgb, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
            target_width, target_height = self.input_size
            height, width = rgb.shape[:2]
            left, top = (width - target_width) // 2, (height - target_height) // 2
            return rgb[top:top + target_height, left:left + target_width]

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

    def prepare(self, frames: list[np.ndarray] | np.ndarray, device: torch.device):
        if len(frames) < self.span_frames:
            raise ValueError(
                f"{self.key} requires {self.span_frames} frames; received {len(frames)}."
            )

        prepared: list[np.ndarray] = []
        chosen = list(frames)[-self.span_frames:][::self.frame_step]
        for frame in chosen:
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
        tensor = (tensor - mean) / std
        if self.pathway == "slowfast":
            return [tensor[:, :, ::4], tensor]
        return tensor


KINETICS_MEAN = (0.43216, 0.394666, 0.37645)
KINETICS_STD = (0.22803, 0.22145, 0.216989)

MODEL_INPUT_ADAPTERS: dict[str, ModelInputAdapter] = {
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
}


# The two newer checkpoints (CampusGuard's own training): 224 px, 0..255 statistics, class 1 = fight.
IMAGENET_255_MEAN = tuple(v / 255.0 for v in (123.675, 116.28, 103.53))
IMAGENET_255_STD = tuple(v / 255.0 for v in (58.395, 57.12, 57.375))

MODEL_INPUT_ADAPTERS["slowfast"] = ModelInputAdapter(
    key="slowfast",
    clip_length=32,
    input_size=(224, 224),
    mean=IMAGENET_255_MEAN,
    std=IMAGENET_255_STD,
    notes="SlowFast R50: 32 fast frames at a gap of 2; slow pathway = every 4th fast frame (8 frames). RGB, short side 256, centre crop 224.",
    resize_short_side=256,
    frame_step=2,
    pathway="slowfast",
)
MODEL_INPUT_ADAPTERS["r2plus1d"] = ModelInputAdapter(
    key="r2plus1d",
    clip_length=16,
    input_size=(224, 224),
    mean=IMAGENET_255_MEAN,
    std=IMAGENET_255_STD,
    notes="R(2+1)D-18: 16 consecutive frames. RGB, short side 256, centre crop 224.",
    resize_short_side=256,
    check_every=16,   # at 224 px one check costs ~5x the old model on a CPU, so windows do not overlap
)


def get_model_input_adapter(key: str) -> ModelInputAdapter:
    try:
        return MODEL_INPUT_ADAPTERS[key]
    except KeyError as exc:
        raise KeyError(f"No input adapter registered for violence model: {key}") from exc
