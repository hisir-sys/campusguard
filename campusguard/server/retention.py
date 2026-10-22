"""Keep disk use bounded: delete old clips and over-budget footage."""
from __future__ import annotations

import time
from pathlib import Path


def _clips(directory: Path) -> list[Path]:
    try:
        return [p for p in directory.glob("*.mp4") if p.is_file()]
    except OSError:
        return []


def purge_old_footage(directory: Path, max_age_days: float, now: float | None = None) -> list[Path]:
    cutoff = (now if now is not None else time.time()) - max_age_days * 86400.0
    removed: list[Path] = []
    for clip in _clips(directory):
        try:
            if clip.stat().st_mtime < cutoff:
                clip.unlink()
                removed.append(clip)
        except OSError:
            continue
    return removed


def enforce_disk_budget(directory: Path, max_bytes: int) -> list[Path]:
    """Remove the oldest clips until the folder is within max_bytes."""
    entries = []
    for clip in _clips(directory):
        try:
            stat = clip.stat()
            entries.append((stat.st_mtime, stat.st_size, clip))
        except OSError:
            continue
    total = sum(size for _, size, _ in entries)
    removed: list[Path] = []
    for _mtime, size, clip in sorted(entries, key=lambda item: item[0]):
        if total <= max_bytes:
            break
        try:
            clip.unlink()
        except OSError:
            continue
        total -= size
        removed.append(clip)
    return removed
