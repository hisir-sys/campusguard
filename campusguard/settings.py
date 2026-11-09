from __future__ import annotations
from dataclasses import asdict, dataclass, fields
from typing import Any

# Per-camera sensitivity: added to the global confidence threshold for that camera only.
SENSITIVITY_LEVELS = (
    ("Sensitive (more alerts)", -0.10),
    ("Default", 0.0),
    ("Cautious (fewer false alarms)", 0.10),
    ("Strict (very few alerts)", 0.20),
)


def effective_threshold(base: float, offset: float) -> float:
    """Global threshold plus a camera's offset, kept inside the valid 5%-99% range."""
    return min(0.99, max(0.05, float(base) + float(offset)))


START_PAGES = ("dashboard", "cameras", "incidents", "alerts")


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
    fdsc_mc3_model_path: str = "models/model_16_m3_0.8888.pth"
    violence_model: str = "fdsc_mc3"
    device: str = "auto"
    fight_positive_class: int = 0
    connection_mode: str = "local"
    server_address: str = ""
    alert_sound_enabled: bool = True
    start_page: str = "dashboard"
    sidebar_hover_open: bool = True
    # Phone alerts (see campusguard/notify.py). Secrets live in the credential vault, not here.
    alert_numbers: str = ""
    escalation_numbers: str = ""
    escalate_minutes: int = 3
    alert_min_severity: str = "MEDIUM"
    whatsapp_mode: str = "off"
    whatsapp_phone_id: str = ""
    whatsapp_template: str = ""
    country_code: str = "91"
    ntfy_topic: str = ""
    ntfy_server: str = "https://ntfy.sh"
    ntfy_attach_clip: bool = False
    auto_open_whatsapp: bool = False
    # How many consecutive "fight" readings (about 0.5 s apart) raise an incident.
    alert_confirm_predictions: int = 2
    gpu_video_decode: bool = False

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "AppSettings":
        allowed = {field.name for field in fields(cls)}
        candidate = cls(**{key: value for key, value in values.items() if key in allowed})
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
            fdsc_mc3_model_path=str(candidate.fdsc_mc3_model_path),
            # Spontim 1.0 is the only detection model.
            violence_model="fdsc_mc3",
            device=candidate.device if candidate.device in {"auto", "cpu", "cuda"} else "auto",
            fight_positive_class=0 if int(candidate.fight_positive_class) == 0 else 1,
            connection_mode=candidate.connection_mode if candidate.connection_mode in {"local", "server"} else "local",
            server_address=str(candidate.server_address).strip()[:2048],
            alert_sound_enabled=bool(candidate.alert_sound_enabled),
            start_page=candidate.start_page if candidate.start_page in START_PAGES else "dashboard",
            sidebar_hover_open=bool(candidate.sidebar_hover_open),
            alert_numbers=str(candidate.alert_numbers)[:600],
            escalation_numbers=str(candidate.escalation_numbers)[:600],
            escalate_minutes=min(60, max(0, int(candidate.escalate_minutes))),
            alert_min_severity=candidate.alert_min_severity if candidate.alert_min_severity in {"LOW", "MEDIUM", "HIGH", "CRITICAL"} else "MEDIUM",
            whatsapp_mode=candidate.whatsapp_mode if candidate.whatsapp_mode in {"off", "link", "cloud"} else "off",
            whatsapp_phone_id=str(candidate.whatsapp_phone_id).strip()[:40],
            whatsapp_template=str(candidate.whatsapp_template).strip()[:80],
            country_code="".join(ch for ch in str(candidate.country_code) if ch.isdigit())[:4],
            ntfy_topic="".join(ch for ch in str(candidate.ntfy_topic) if ch.isalnum() or ch in "_-")[:64],
            ntfy_server=str(candidate.ntfy_server).strip().rstrip("/")[:200] or "https://ntfy.sh",
            ntfy_attach_clip=bool(candidate.ntfy_attach_clip),
            auto_open_whatsapp=bool(candidate.auto_open_whatsapp),
            alert_confirm_predictions=min(6, max(2, int(candidate.alert_confirm_predictions))),
            gpu_video_decode=bool(candidate.gpu_video_decode),
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
    threshold_offset: float = 0.0
    group_name: str = ""

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
