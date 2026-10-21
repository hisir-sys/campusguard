"""Model file aliases.

``models/model_16_m3_0.8888.pth`` and ``models/fight_mc3_18.pth`` are the same
checkpoint (byte-identical, same SHA-256). The Windows build ships only one
copy to save ~46 MB, so when the alias is missing the other name is used.
The fallback applies only when the requested file does not exist, so a user's
own file or a different checkpoint is never replaced.
"""

from __future__ import annotations

from pathlib import Path

DUPLICATE_MODEL_ALIASES = {
    "model_16_m3_0.8888.pth": "fight_mc3_18.pth",
}


def with_aliases(raw: Path) -> list[Path]:
    """The requested path first, then its identical-checkpoint alias (if any)."""
    candidates = [raw]
    alias = DUPLICATE_MODEL_ALIASES.get(raw.name)
    if alias:
        candidates.append(raw.with_name(alias))
    return candidates
