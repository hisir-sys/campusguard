"""Simple machine health checks used by the Settings page and the background monitor.

No extra dependencies: disk use via ``shutil`` and an optional GPU read via torch.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

GB = 1024 ** 3
DISK_WARN_PERCENT = 10.0   # warn when less than this much of the drive is free
DISK_WARN_BYTES = 10 * GB  # ...or less than this many bytes
DISK_CRITICAL_BYTES = 3 * GB


@dataclass
class HealthReport:
    disk_total: int = 0
    disk_free: int = 0
    footage_bytes: int = 0
    footage_clips: int = 0
    gpu_name: str | None = None
    gpu_free_mb: int | None = None
    gpu_total_mb: int | None = None
    problems: list[tuple[str, str]] = field(default_factory=list)   # (level, message)

    @property
    def disk_free_percent(self) -> float:
        return 100.0 * self.disk_free / self.disk_total if self.disk_total else 0.0

    @property
    def level(self) -> str:
        levels = {level for level, _ in self.problems}
        return "critical" if "critical" in levels else "warning" if "warning" in levels else "ok"


def footage_usage(directory: Path) -> tuple[int, int]:
    total = clips = 0
    try:
        for clip in directory.glob("*.mp4"):
            try:
                total += clip.stat().st_size
                clips += 1
            except OSError:
                continue
    except OSError:
        pass
    return total, clips


def _gpu() -> tuple[str | None, int | None, int | None]:
    try:
        import torch
        if not torch.cuda.is_available():
            return None, None, None
        free, total = torch.cuda.mem_get_info()
        return torch.cuda.get_device_name(0), int(free // (1024 ** 2)), int(total // (1024 ** 2))
    except Exception:
        return None, None, None


def evaluate_disk(disk_free: int, disk_total: int) -> list[tuple[str, str]]:
    """Problems for a given amount of free disk space (pure, easy to test)."""
    if disk_total <= 0:
        return [("warning", "Could not read the disk where footage is stored.")]
    free_gb = disk_free / GB
    percent = 100.0 * disk_free / disk_total
    if disk_free < DISK_CRITICAL_BYTES:
        return [("critical", f"Only {free_gb:.1f} GB left on the footage drive. New clips may fail to save.")]
    if disk_free < DISK_WARN_BYTES or percent < DISK_WARN_PERCENT:
        return [("warning", f"Footage drive is running low: {free_gb:.1f} GB free ({percent:.0f}%).")]
    return []


def collect(footage_dir: Path, with_gpu: bool = True) -> HealthReport:
    report = HealthReport()
    try:
        usage = shutil.disk_usage(footage_dir if footage_dir.exists() else footage_dir.anchor or ".")
        report.disk_total, report.disk_free = int(usage.total), int(usage.free)
    except OSError:
        pass
    report.footage_bytes, report.footage_clips = footage_usage(footage_dir)
    if with_gpu:
        report.gpu_name, report.gpu_free_mb, report.gpu_total_mb = _gpu()
    report.problems.extend(evaluate_disk(report.disk_free, report.disk_total))
    if report.gpu_free_mb is not None and report.gpu_free_mb < 300:
        report.problems.append(("warning", f"GPU memory is almost full ({report.gpu_free_mb} MB free)."))
    return report


def camera_problems(statuses: dict[str, str]) -> list[tuple[str, str]]:
    """Problems from camera states: {camera_id: STATUS}. Pure, easy to test."""
    problems: list[tuple[str, str]] = []
    if not statuses:
        return problems
    bad = [cid for cid in statuses if statuses[cid] not in {"LIVE", "CONNECTING"}]
    if bad and len(bad) == len(statuses) and len(statuses) > 1:
        problems.append(("critical", f"All {len(statuses)} cameras are offline. Check the network or power."))
    elif bad:
        problems.append(("warning", f"{len(bad)} of {len(statuses)} cameras are offline."))
    return problems
