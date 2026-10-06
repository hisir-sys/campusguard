from __future__ import annotations
from dataclasses import asdict, dataclass, fields
from typing import Any

@dataclass(frozen=True)
class AppSettings:
    confidence_threshold: float = 0.65
    detection_enabled: bool = True
    tracking_enabled: bool = True
    pose_enabled: bool = True
    alert_cooldown_seconds: int = 45
    auto_reconnect: bool = True
    theme: str = "dark"
    detector_model_path: str = "models/yolo11n.pt"
    pose_model_path: str = "models/yolo11n-pose.pt"
    fight_model_path: str = "models/fight_mc3_18.pth"
    fdsc_mc3_model_path: str = "models/model_16_m3_0.8888.pth"
    r3d_model_path: str = "models/fdsc_r3d_18.pth"
    x3d_model_path: str = "models/final_x3d_realtime.pt"
    violence_model: str = "fdsc_mc3"
    device: str = "auto"
    fight_positive_class: int = 0

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "AppSettings":
        allowed = {field.name for field in fields(cls)}
        candidate = cls(**{key: value for key, value in values.items() if key in allowed})
        models = {"mc3", "fdsc_mc3", "r3d", "x3d", "enhanced"}
        return cls(
            confidence_threshold=min(0.99, max(0.05, float(candidate.confidence_threshold))),
            detection_enabled=bool(candidate.detection_enabled),
            tracking_enabled=bool(candidate.tracking_enabled),
            pose_enabled=bool(candidate.pose_enabled),
            alert_cooldown_seconds=max(0, int(candidate.alert_cooldown_seconds)),
            auto_reconnect=bool(candidate.auto_reconnect),
            theme=candidate.theme if candidate.theme in {"dark", "light"} else "dark",
            detector_model_path=str(candidate.detector_model_path),
            pose_model_path=str(candidate.pose_model_path),
            fight_model_path=str(candidate.fight_model_path),
            fdsc_mc3_model_path=str(candidate.fdsc_mc3_model_path),
            r3d_model_path=str(candidate.r3d_model_path),
            x3d_model_path=str(candidate.x3d_model_path),
            # CampusGuard Enhanced is intentionally reserved for a future
            # ensemble release; never activate it from persisted settings.
            violence_model=(
                candidate.violence_model
                if candidate.violence_model in models and candidate.violence_model != "enhanced"
                else "fdsc_mc3"
            ),
            device=candidate.device if candidate.device in {"auto", "cpu", "cuda"} else "auto",
            fight_positive_class=0 if int(candidate.fight_positive_class) == 0 else 1,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class CameraConfig:
    camera_id: str
    name: str
    source_type: str
    source_address: str
    ai_enabled: bool
    created_at: str

@dataclass(frozen=True)
class CameraCredentials:
    username: str = ""
    password: str = ""

@dataclass(frozen=True)
class CameraStats:
    status: str = "CONNECTING"
    message: str = ""
    fps: float | None = None
    resolution: str = "N/A"
