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
    page.resize(1280, 820)
    page.ensurePolished()
    page.show()
    # Process layout/paint events after showing and sizing; otherwise some Qt
    # platforms can grab a not-yet-laid-out top-level widget (a tiny PNG).
    for _ in range(3):
        app.processEvents()
    image = page.grab()
    if image.isNull() or image.width() < 1000 or image.height() < 600:
        raise RuntimeError(
            "Viewer grab is empty or undersized: "
            f"{image.width()}x{image.height()}"
        )
    if not image.save(str(output), "PNG"):
        raise RuntimeError(f"Qt could not save viewer screenshot: {output}")
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
            # PNG compression varies by OS/Qt version and theme. Validate that
            # the saved file is a real, nontrivial PNG instead of assuming 10 KB.
            if not path.is_file() or path.stat().st_size < 1_000:
                size = path.stat().st_size if path.exists() else 0
                raise RuntimeError(
                    f"Screenshot was not written correctly: {path} ({size} bytes)"
                )
            print(f"RENDER OK: {path} ({path.stat().st_size} bytes, {elapsed:.2f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
