"""Server settings stored in server.json inside the CampusGuard data folder."""
from __future__ import annotations

import json
import os
import secrets
import uuid
from dataclasses import asdict, dataclass, field
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
    footage_dir: str = ""
    # Phase 6: identity inside one school ("one CampusGuard ID, several servers").
    server_id: str = ""               # generated once per installation
    server_name: str = ""             # shown to operators, e.g. "Server One"
    school_id: str = ""               # shared by every server of the school; empty = derive from the account
    peers: list = field(default_factory=list)   # [{"name", "address", "ca_file"}]; tokens live in Credential Manager


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


def normalise_peers(raw) -> list[dict]:
    """Keep well-formed peers only, one per address (address is the stable key)."""
    peers: list[dict] = []
    seen: set[str] = set()
    if not isinstance(raw, list):
        return peers
    for item in raw[:32]:
        if not isinstance(item, dict):
            continue
        address = str(item.get("address", "")).strip().rstrip("/")
        lowered = address.lower()
        if not lowered.startswith(("http://", "https://")) or lowered in seen:
            continue
        seen.add(lowered)
        peers.append({
            "name": str(item.get("name", "")).strip()[:60] or address,
            "address": address,
            "ca_file": str(item.get("ca_file", "")).strip(),
        })
    return peers


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
        footage_dir=str(values.get("footage_dir", "")).strip(),
        server_id=str(values.get("server_id", "")).strip()[:64],
        server_name=str(values.get("server_name", "")).strip()[:60],
        school_id=str(values.get("school_id", "")).strip()[:80],
        peers=normalise_peers(values.get("peers")),
    )


def load_config(data_dir: Path, vault=None) -> ServerConfig:
    """Load settings and migrate the API token into Windows Credential Manager."""
    path = data_dir / "server.json"
    values: dict = {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            values = loaded
    except (OSError, ValueError):
        values = {}
    config = normalise(values)
    if not config.server_id:
        config.server_id = uuid.uuid4().hex
    if not config.server_name:
        import socket
        config.server_name = (socket.gethostname() or "CampusGuard server")[:60]
    if vault is None:
        from campusguard.credentials import CredentialVault
        vault = CredentialVault()
    legacy_token = config.token
    try:
        stored_token = vault.load_api_token()
        if stored_token:
            config.token = stored_token
        elif len(legacy_token) >= 24:
            # Preserve existing installations by migrating their old JSON token once.
            vault.save_api_token(legacy_token)
            config.token = legacy_token
        else:
            config.token = secrets.token_urlsafe(32)
            vault.save_api_token(config.token)
    except Exception as error:
        raise RuntimeError(
            "Windows Credential Manager is unavailable; CampusGuard cannot safely load or save the server token."
        ) from error
    # Always rewrite normalized settings; save_config deliberately omits the token.
    save_config(data_dir, config)
    return config


def save_config(data_dir: Path, config: ServerConfig) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "server.json"
    temporary = path.with_suffix(".json.tmp")
    values = asdict(config)
    values.pop("token", None)
    temporary.write_text(json.dumps(values, indent=2), encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, path)
