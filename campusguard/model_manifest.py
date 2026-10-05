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
    "mc3": ModelManifest(
        key="mc3",
        name="Current MC3-18",
        description="CampusGuard's existing MC3-18 temporal fight classifier.",
        architecture="mc3",
        path_setting="fight_model_path",
        class_labels=("fight", "noFight"),
        fight_class=0,
        preprocessing="RGB, 16 frames, 112x112, /255, Kinetics-style normalization",
        semantic_status="verified",
        source_note=(
            "Verified from the original CampusGuard temporal_model.py: "
            "probs[0] is fight and probs[1] is noFight."
        ),
    ),
    "fdsc_mc3": ModelManifest(
        key="fdsc_mc3",
        name="FDSC MC3-18",
        description="FDSC fine-tuned MC3-18 surveillance classifier.",
        architecture="mc3",
        path_setting="fdsc_mc3_model_path",
        class_labels=("fight", "noFight"),
        fight_class=0,
        preprocessing="RGB, 16 frames, 112x112; Kinetics-style normalization",
        semantic_status="verified",
        source_note=(
            "Verified against the FDSC project's published inference contract: "
            "the checkpoint is model_16_m3_0.8888.pth, uses a 16-frame sequence, "
            "and the project defines CLASSES_LIST as ['fight', 'noFight']."
        ),
    ),
    "r3d": ModelManifest(
        key="r3d",
        name="FDSC R3D-18",
        description="FDSC R3D-18 3D ResNet surveillance classifier.",
        architecture="r3d",
        path_setting="r3d_model_path",
        class_labels=("class_0", "class_1"),
        fight_class=None,
        preprocessing="Checkpoint-specific preprocessing must be verified",
        semantic_status="unverified",
        source_note="Class-index semantics are not safely derivable from raw weights alone.",
    ),
    "x3d": ModelManifest(
        key="x3d",
        name="X3D-M",
        description="Realtime X3D-M violence classifier.",
        architecture="x3d",
        path_setting="x3d_model_path",
        class_labels=("non-violent", "violent"),
        fight_class=1,
        preprocessing="RGB, 16 frames, 224x224, /255, mean=0.45, std=0.225",
        semantic_status="verified",
        source_note=(
            "Verified contract for visionlab-ai/school-violence-detection-models "
            "final_x3d_realtime.pt: X3D-M, 16 RGB frames, 224x224, mean 0.45, "
            "std 0.225, labels non-violent/violent."
        ),
    ),
}


def get_model_manifest(key: str) -> ModelManifest:
    try:
        return MODEL_MANIFESTS[key]
    except KeyError as exc:
        raise KeyError(f"Unknown violence model: {key}") from exc
