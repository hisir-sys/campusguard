"""Detect the machine and choose an engine profile (Lite / Standard / Server)."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

PROFILE_NAMES = ("lite", "standard", "server")
# Above this many simultaneously running cameras a CUDA machine switches to the
# server profile when the operator left the profile on "auto".
SERVER_CAMERA_THRESHOLD = 16


@dataclass(frozen=True)
class HardwareInfo:
    cpu_count: int
    ram_gb: float | None
    cuda: bool
    gpu_name: str | None = None
    gpu_memory_gb: float | None = None


@dataclass(frozen=True)
class EngineProfile:
    name: str
    smart_analysis: bool          # skip the heavy models while a scene is still
    motion_hangover_s: float      # keep analysing this long after the last motion
    gate_hz: float                # how often the cheap motion check runs
    max_analysis_width: int | None  # downscale analysis frames wider than this
    preview_max_fps: float        # cap on live-preview frames (0 = unlimited)
    prebuffer_bytes: int | None   # memory cap for each camera's evidence lead-in
    batch_detector: bool          # batch person detection across cameras on GPU


PROFILES: dict[str, EngineProfile] = {
    "lite": EngineProfile(
        name="lite", smart_analysis=True, motion_hangover_s=5.0, gate_hz=8.0,
        max_analysis_width=None, preview_max_fps=0.0, prebuffer_bytes=None,
        batch_detector=False,
    ),
    "standard": EngineProfile(
        name="standard", smart_analysis=True, motion_hangover_s=5.0, gate_hz=10.0,
        max_analysis_width=None, preview_max_fps=0.0, prebuffer_bytes=None,
        batch_detector=False,
    ),
    "server": EngineProfile(
        name="server", smart_analysis=True, motion_hangover_s=6.0, gate_hz=6.0,
        max_analysis_width=960, preview_max_fps=10.0,
        prebuffer_bytes=48 * 1024 * 1024, batch_detector=True,
    ),
}

_cached_hardware: HardwareInfo | None = None


def _total_ram_gb() -> float | None:
    try:
        if sys.platform == "win32":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
                return status.ullTotalPhys / 1024 ** 3
            return None
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return pages * page_size / 1024 ** 3
    except (OSError, ValueError, AttributeError):
        return None


def detect_hardware(refresh: bool = False) -> HardwareInfo:
    global _cached_hardware
    if _cached_hardware is not None and not refresh:
        return _cached_hardware
    cuda, gpu_name, gpu_memory = False, None, None
    try:
        import torch

        cuda = bool(torch.cuda.is_available())
        if cuda:
            properties = torch.cuda.get_device_properties(0)
            gpu_name = str(properties.name)
            gpu_memory = float(properties.total_memory) / 1024 ** 3
    except Exception:  # no torch, broken driver, ... -> CPU
        cuda, gpu_name, gpu_memory = False, None, None
    _cached_hardware = HardwareInfo(os.cpu_count() or 1, _total_ram_gb(), cuda, gpu_name, gpu_memory)
    return _cached_hardware


def read_engine_override(config_dir: Path | None = None) -> str:
    """Operator override: CAMPUSGUARD_PROFILE env var, else engine.json, else 'auto'."""
    value = os.environ.get("CAMPUSGUARD_PROFILE", "").strip().lower()
    if not value and config_dir is not None:
        try:
            data = json.loads((config_dir / "engine.json").read_text(encoding="utf-8"))
            value = str(data.get("profile", "")).strip().lower()
        except (OSError, ValueError, AttributeError):
            value = ""
    return value if value in PROFILE_NAMES else "auto"


def smart_analysis_enabled(config_dir: Path | None = None) -> bool:
    """Smart analysis is on unless explicitly switched off (env or engine.json)."""
    raw = os.environ.get("CAMPUSGUARD_SMART_ANALYSIS", "").strip().lower()
    if not raw and config_dir is not None:
        try:
            data = json.loads((config_dir / "engine.json").read_text(encoding="utf-8"))
            raw = str(data.get("smart_analysis", "")).strip().lower()
        except (OSError, ValueError, AttributeError):
            raw = ""
    return raw not in {"0", "false", "off", "no"}


def resolve_profile(override: str, hardware: HardwareInfo, camera_count: int) -> EngineProfile:
    """Explicit choice wins; otherwise pick from the hardware and camera count."""
    if override in PROFILES:
        return PROFILES[override]
    if hardware.cuda:
        return PROFILES["server"] if camera_count > SERVER_CAMERA_THRESHOLD else PROFILES["standard"]
    weak = hardware.cpu_count <= 4 or (hardware.ram_gb is not None and hardware.ram_gb < 7.5)
    return PROFILES["lite" if weak else "standard"]
