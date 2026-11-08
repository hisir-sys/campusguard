"""Render CampusGuard's redesigned dashboard in both themes with synthetic camera cards."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from campusguard.settings import CameraConfig
from campusguard.storage import Repository
from campusguard.ui.common import apply_theme
from campusguard.ui.dashboard_page import DashboardPage


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/ui-renders")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])

    cameras = [
        CameraConfig(
            camera_id=f"UI-CAM-{index:03d}",
            name=f"Campus camera {index:02d}",
            source_type="RTSP",
            source_address=f"rtsp://example.invalid/camera-{index:02d}",
            ai_enabled=True,
            created_at="2026-01-01T00:00:00Z",
        )
        for index in range(1, 3)
    ]

    with tempfile.TemporaryDirectory(prefix="campusguard-dashboard-render-") as temp:
        root = Path(temp)
        for theme in ("dark", "light"):
            repository = Repository(
                database_path=root / f"{theme}.sqlite3",
                footage_dir=root / f"{theme}-footage",
            )
            page = DashboardPage(repository)
            apply_theme(page, theme)
            page.sync_cameras(cameras)
            page.refresh_summary()
            page.resize(1440, 900)
            page.ensurePolished()
            page.show()
            app.processEvents()
            app.processEvents()

            image = page.grab()
            if image.isNull() or image.width() < 1100 or image.height() < 700:
                raise RuntimeError(
                    f"{theme} dashboard render is empty or undersized: "
                    f"{image.width()}x{image.height()}"
                )
            target = output / f"campusguard-dashboard-{theme}.png"
            if not image.save(str(target), "PNG"):
                raise RuntimeError(f"Could not save dashboard screenshot: {target}")
            if target.stat().st_size < 5_000:
                raise RuntimeError(f"Dashboard screenshot is unexpectedly small: {target}")
            print(f"DASHBOARD RENDER OK: {target} ({target.stat().st_size} bytes)")

            page.close()
            page.deleteLater()
            app.processEvents()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
