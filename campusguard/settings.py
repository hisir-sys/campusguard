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
    device: str = "auto"
    fight_positive_class: int = 1

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "AppSettings":
        allowed = {field.name for field in fields(cls)}
        cleaned = {key: value for key, value in values.items() if key in allowed}
        candidate = cls(**cleaned)

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
