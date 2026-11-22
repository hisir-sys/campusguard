# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
"""Automatic clean-up of old incident clips and records on a single PC (local mode).

The school decides how long it needs them (Settings > Storage); 0 keeps everything until it is
deleted by hand, so nothing is ever removed unless a period was chosen.
"""
from __future__ import annotations

from campusguard.server.retention import purge_old_footage


def apply_retention(repository, footage_days: int, incident_days: int) -> dict:
    """Remove clips and incident records older than the chosen periods; returns what was removed."""
    clips = 0
    incidents = 0
    if footage_days > 0:
        removed = purge_old_footage(repository.footage_dir, footage_days)
        repository.forget_footage_paths([str(path) for path in removed])
        clips = len(removed)
    if incident_days > 0:
        incidents = repository.purge_incidents_older_than(incident_days)
    return {"clips_removed": clips, "incidents_removed": incidents}
