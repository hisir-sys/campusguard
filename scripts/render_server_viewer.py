"""Render the remote viewer in test-fixture layouts for visual regression review.

The generated screenshots are explicitly marked as synthetic UI fixtures, never live data.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Running a script by file path sets scripts/ as sys.path[0], not the repo root.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from campusguard.ui.icons import set_icon_theme
from campusguard.ui.server_viewer import ServerViewerPage
from campusguard.ui.common import apply_theme


def camera_fixture(index: int) -> dict:
    return {
        "camera_id": f"TEST-CAM-{index:03d}",
        "name": f"UI fixture camera {index:03d}",
        "type": "RTSP",
        "address": "rtsp://example.invalid/not-a-live-camera",
        "health": "connecting",
        "status": "CONNECTING",
        "message": "Synthetic layout fixture — not connected",
        "fps": None,
        "resolution": "N/A",
        "ai_enabled": True,
    }


def render(app: QApplication, output: Path, theme: str, count: int) -> float:
    set_icon_theme(theme)
    page = ServerViewerPage(lambda: (_ for _ in ()).throw(RuntimeError("Rendering never contacts a server.")))
    apply_theme(page, theme)
    page._closing = True  # suppress showEvent polling; rendering never contacts a server
    banner = QLabel("UI RENDER TEST  ·  SYNTHETIC FIXTURES  ·  NOT LIVE CAMERA DATA")
    banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
    banner.setWordWrap(True)
    banner.setStyleSheet("font-weight: 800; padding: 7px; border: 1px solid #C8FF52; border-radius: 8px;")
    page.layout().insertWidget(0, banner)
    page.connection_status.setText(f"UI TEST DATA — NOT LIVE · Layout size: {count} camera cards")
    started = time.perf_counter()
    page._sync_camera_cards([camera_fixture(i + 1) for i in range(count)])
    app.processEvents()
    page.resize(1280, 820)
    page.show()
    app.processEvents()
    page.grab().save(str(output))
    elapsed = time.perf_counter() - started
    page.shutdown()
    page.close()
    app.processEvents()
    return elapsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/ui-renders")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    for theme in ("dark", "light"):
        for count in (0, 5, 120):
            path = output / f"server-viewer-{theme}-{count:03d}-test-fixtures.png"
            elapsed = render(app, path, theme, count)
            if not path.exists() or path.stat().st_size < 10_000:
                raise RuntimeError(f"Screenshot was not written correctly: {path}")
            print(f"RENDER OK: {path} ({path.stat().st_size} bytes, {elapsed:.2f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
