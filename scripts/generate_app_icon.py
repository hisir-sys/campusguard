from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "campusguard-eye.svg"
PNG = ROOT / "assets" / "campusguard-eye.png"
ICO = ROOT / "assets" / "campusguard.ico"

image = QImage(1024, 1024, QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
renderer = QSvgRenderer(str(SOURCE))
if not renderer.isValid():
    raise SystemExit(f"Could not render SVG icon: {SOURCE}")
painter = QPainter(image)
renderer.render(painter)
painter.end()
if not image.save(str(PNG), "PNG"):
    raise SystemExit(f"Could not create PNG icon: {PNG}")

with Image.open(PNG) as rendered:
    rendered.save(ICO, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"Created {ICO}")
