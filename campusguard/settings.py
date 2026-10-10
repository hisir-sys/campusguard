from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields
from typing import Any


def _as_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return parsed if math.isfinite(parsed) else default


def _as_int(value: Any, default: int) -> int:
    try:
        if isinstance(value, float) and not value.is_integer():
            return default
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def _as_nonempty_string(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


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
    def from_dict(cls, values: dict[str, Any] | Any) -> "AppSettings":
        """Load persisted settings defensively; invalid values fall back to defaults."""
        if not isinstance(values, dict):
            values = {}

        defaults = cls()
        allowed = {field.name for field in fields(cls)}
        candidate_values = {key: value for key, value in values.items() if key in allowed}
        candidate = cls(**candidate_values)
        models = {"mc3", "fdsc_mc3", "r3d", "x3d"}

        threshold = _as_float(candidate.confidence_threshold, defaults.confidence_threshold)
        cooldown = _as_int(candidate.alert_cooldown_seconds, defaults.alert_cooldown_seconds)
        positive_class = _as_int(candidate.fight_positive_class, defaults.fight_positive_class)
        selected_model = _as_nonempty_string(candidate.violence_model, defaults.violence_model)
        if selected_model not in models:
            selected_model = defaults.violence_model
        theme = _as_nonempty_string(candidate.theme, defaults.theme)
        if theme not in {"dark", "light"}:
            theme = defaults.theme
        device = _as_nonempty_string(candidate.device, defaults.device)
        if device not in {"auto", "cpu", "cuda"}:
            device = defaults.device

        return cls(
            confidence_threshold=min(0.99, max(0.05, threshold)),
            detection_enabled=_as_bool(candidate.detection_enabled, defaults.detection_enabled),
            tracking_enabled=_as_bool(candidate.tracking_enabled, defaults.tracking_enabled),
            pose_enabled=_as_bool(candidate.pose_enabled, defaults.pose_enabled),
            alert_cooldown_seconds=max(0, cooldown),
            auto_reconnect=_as_bool(candidate.auto_reconnect, defaults.auto_reconnect),
            theme=theme,
            detector_model_path=_as_nonempty_string(candidate.detector_model_path, defaults.detector_model_path),
            pose_model_path=_as_nonempty_string(candidate.pose_model_path, defaults.pose_model_path),
            fight_model_path=_as_nonempty_string(candidate.fight_model_path, defaults.fight_model_path),
            fdsc_mc3_model_path=_as_nonempty_string(candidate.fdsc_mc3_model_path, defaults.fdsc_mc3_model_path),
            r3d_model_path=_as_nonempty_string(candidate.r3d_model_path, defaults.r3d_model_path),
            x3d_model_path=_as_nonempty_string(candidate.x3d_model_path, defaults.x3d_model_path),
            violence_model=selected_model,
            device=device,
            fight_positive_class=0 if positive_class == 0 else 1,
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
