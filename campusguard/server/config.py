"""Server settings stored in server.json inside the CampusGuard data folder."""
from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"          # use "0.0.0.0" to let other PCs on the LAN connect
    port: int = 8765
    token: str = ""                   # generated on first run
    retention_days_footage: int = 30
    retention_days_incidents: int = 365
    max_footage_gb: float = 200.0     # oldest clips are removed first when exceeded
    recheck_hours: float = 6.0        # how often the licence/account is re-verified
    tls_cert_file: str = ""
    tls_key_file: str = ""


def _clamp_int(value, low, high, default):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _clamp_float(value, low, high, default):
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def normalise(values: dict) -> ServerConfig:
    base = ServerConfig()
    return ServerConfig(
        host=str(values.get("host", base.host)).strip() or base.host,
        port=_clamp_int(values.get("port"), 1, 65535, base.port),
        token=str(values.get("token", "")).strip(),
        retention_days_footage=_clamp_int(values.get("retention_days_footage"), 1, 3650, base.retention_days_footage),
        retention_days_incidents=_clamp_int(values.get("retention_days_incidents"), 1, 36500, base.retention_days_incidents),
        max_footage_gb=_clamp_float(values.get("max_footage_gb"), 1.0, 100000.0, base.max_footage_gb),
        recheck_hours=_clamp_float(values.get("recheck_hours"), 0.25, 168.0, base.recheck_hours),
        tls_cert_file=str(values.get("tls_cert_file", "")).strip(),
        tls_key_file=str(values.get("tls_key_file", "")).strip(),
    )


def load_config(data_dir: Path) -> ServerConfig:
    """Read server.json (creating it, with a fresh random token, on first run)."""
    path = data_dir / "server.json"
    values: dict = {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            values = loaded
    except (OSError, ValueError):
        values = {}
    config = normalise(values)
    if len(config.token) < 24:
        config.token = secrets.token_urlsafe(32)
        save_config(data_dir, config)
    elif not path.exists():
        save_config(data_dir, config)
    return config


def save_config(data_dir: Path, config: ServerConfig) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "server.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, path)
