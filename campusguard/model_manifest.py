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
        name="CampusGuard MC3-18 (baseline)",
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
        name="MohamedSebaie FDSC MC3-18 (92.5% reported)",
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
    "r3d": ModelManifest(
        key="r3d",
        name="FDSC R3D-18",
        description="FDSC R3D-18 3D ResNet surveillance classifier.",
        architecture="r3d",
        path_setting="r3d_model_path",
        class_labels=("class_0", "class_1"),
        fight_class=None,
        preprocessing="RGB, resize to 171x128, center-crop 112x112, /255, Kinetics-style normalization",
        semantic_status="technical_unavailable",
        source_note=(
            "The FDSC R3D-18 architecture and preprocessing contract are documented, "
            "but the original trained checkpoint is not currently available from the "
            "official FDSC repository/package. The model is therefore treated as a "
            "technical availability issue, not as a verified operational model."
        ),
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
