"""Decides when to tell the IT contacts about a problem (offline cameras, low disk).

Pure logic, driven by the server's HealthTracker snapshot, so it can be tested with a fake clock.
It is built to avoid message floods: one message per outage, and when many cameras drop at once
(a switch, a cable, the NVR) that is ONE message, not one per camera.
"""
from __future__ import annotations

from dataclasses import dataclass

GROUP_AT = 5               # this many cameras in one go are reported as a single message
LISTED_NAMES = 6           # how many camera names a message spells out


@dataclass(frozen=True)
class Notice:
    kind: str              # camera_offline | cameras_recovered | disk_low | disk_ok
    title: str
    text: str


def _names(names: list[str]) -> str:
    shown = names[:LISTED_NAMES]
    more = len(names) - len(shown)
    return ", ".join(shown) + (f" and {more} more" if more > 0 else "")


class HealthWatch:
    def __init__(self, offline_after_seconds: float = 300.0, min_free_gb: float = 20.0, label: str = "") -> None:
        self.offline_after = float(offline_after_seconds)
        self.min_free_gb = float(min_free_gb)
        self.label = label.strip()
        self._bad_since: dict[str, float] = {}
        self._reported: set[str] = set()
        self._disk_low = False

    def configure(self, offline_after_seconds: float, min_free_gb: float) -> None:
        self.offline_after = float(offline_after_seconds)
        self.min_free_gb = float(min_free_gb)

    def _where(self) -> str:
        return f" ({self.label})" if self.label else ""

    def evaluate(
        self,
        snapshot: dict[str, dict],
        names: dict[str, str],
        disk_free_gb: float | None,
        now: float,
        ai_disabled: set[str] | None = None,
    ) -> list[Notice]:
        """snapshot: HealthTracker.snapshot(); names: camera_id -> name; now: monotonic seconds."""
        notices: list[Notice] = []
        skip = ai_disabled or set()
        present = set(snapshot)
        for gone in [camera_id for camera_id in self._bad_since if camera_id not in present]:
            self._bad_since.pop(gone, None)
            self._reported.discard(gone)

        newly_overdue: list[str] = []
        recovered: list[str] = []
        for camera_id, entry in snapshot.items():
            if camera_id in skip:
                self._bad_since.pop(camera_id, None)
                self._reported.discard(camera_id)
                continue
            if entry.get("health") == "ok":
                self._bad_since.pop(camera_id, None)
                if camera_id in self._reported:
                    self._reported.discard(camera_id)
                    recovered.append(names.get(camera_id, camera_id))
                continue
            since = self._bad_since.setdefault(camera_id, now)
            if camera_id not in self._reported and now - since >= self.offline_after:
                newly_overdue.append(camera_id)

        total = len(snapshot)
        if newly_overdue:
            self._reported.update(newly_overdue)
            labels = sorted(names.get(camera_id, camera_id) for camera_id in newly_overdue)
            minutes = max(1, int(round(self.offline_after / 60.0)))
            if len(labels) >= GROUP_AT:
                notices.append(Notice(
                    "camera_offline",
                    f"CampusGuard{self._where()}: {len(labels)} cameras offline",
                    f"{len(labels)} of {total} cameras have had no picture for over {minutes} min. "
                    f"This usually means a network switch, cable or recorder problem, not the cameras themselves. "
                    f"Affected: {_names(labels)}.",
                ))
            else:
                notices.append(Notice(
                    "camera_offline",
                    f"CampusGuard{self._where()}: camera offline",
                    f"No picture for over {minutes} min from: {_names(labels)}. Fights there are not being watched.",
                ))
        if recovered:
            labels = sorted(recovered)
            notices.append(Notice(
                "cameras_recovered",
                f"CampusGuard{self._where()}: back online",
                f"{len(labels)} camera{'s are' if len(labels) != 1 else ' is'} working again: {_names(labels)}.",
            ))

        if disk_free_gb is not None:
            if not self._disk_low and disk_free_gb < self.min_free_gb:
                self._disk_low = True
                notices.append(Notice(
                    "disk_low",
                    f"CampusGuard{self._where()}: disk space low",
                    f"Only {disk_free_gb:.0f} GB free where incident clips are saved. "
                    f"Old clips will be removed first, but free some space soon.",
                ))
            elif self._disk_low and disk_free_gb >= self.min_free_gb * 1.2:
                self._disk_low = False
                notices.append(Notice(
                    "disk_ok", f"CampusGuard{self._where()}: disk space OK",
                    f"{disk_free_gb:.0f} GB free again.",
                ))
        return notices
