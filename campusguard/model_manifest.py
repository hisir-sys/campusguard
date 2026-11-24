# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelManifest:
    """Machine-readable contract for one temporal violence checkpoint."""

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


MODEL_MANIFESTS: dict[str, ModelManifest] = {
    "fdsc_mc3": ModelManifest(
        key="fdsc_mc3",
        name="Spontim 1.0",
        description="MohamedSebaie FDSC fine-tuned MC3-18 surveillance classifier; published 92.5% top-1 accuracy run.",
        architecture="mc3",
        path_setting="fdsc_mc3_model_path",
        class_labels=("fight", "noFight"),
        fight_class=0,
        preprocessing="RGB, 16 frames, 112x112; Kinetics-style normalization",
        semantic_status="verified",
        source_note=(
            "Verified against MohamedSebaie/Fight_Detection_From_Surveillance_Cameras-PyTorch_Project: "
            "the checkpoint is model_16_m3_0.8888.pth, uses a 16-frame sequence, "
            "and the project reports a 92.5% top-1 MC3-18 run with 0.90 fight recall."
        ),
    ),
    "slowfast": ModelManifest(
        key="slowfast",
        name="Spontim 2 (SlowFast)",
        description="CampusGuard-trained SlowFast R50 fight classifier. Most accurate on the first tests, heaviest on the CPU.",
        architecture="slowfast",
        path_setting="slowfast_model_path",
        class_labels=("noFight", "fight"),
        fight_class=1,
        preprocessing="RGB, 32 fast frames at gap 2 (+8 slow), 224x224; ImageNet-style normalisation",
        semantic_status="verified",
        source_note="Trained by the owner (class 1 = fight). Measured on two short clips only; see the model comparison sheet.",
    ),
    "r2plus1d": ModelManifest(
        key="r2plus1d",
        name="Spontim 3 (R(2+1)D)",
        description="CampusGuard-trained R(2+1)D-18 fight classifier. Lighter than SlowFast; fewer false alarms than misses on the first tests.",
        architecture="r2plus1d",
        path_setting="r2plus1d_model_path",
        class_labels=("noFight", "fight"),
        fight_class=1,
        preprocessing="RGB, 16 consecutive frames, 224x224; ImageNet-style normalisation",
        semantic_status="verified",
        source_note="Trained by the owner (class 1 = fight). Measured on two short clips only; see the model comparison sheet.",
    ),
}


def get_model_manifest(key: str) -> ModelManifest:
    try:
        return MODEL_MANIFESTS[key]
    except KeyError as exc:
        raise KeyError(f"Unknown violence model: {key}") from exc
