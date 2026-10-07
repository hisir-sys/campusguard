"""Small built-in SVG line-icon set, tinted to match the current theme.

No image files are needed: every icon is a few lines of SVG drawn here.
``IconLabel`` shows one in a layout, ``icon_pixmap`` returns a pixmap for custom
painting (used by the glass nav buttons).
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel, QPushButton

from campusguard.ui import theme

# Each value is the inside of a 24x24 SVG that is drawn with stroke only.
_ICONS: dict[str, str] = {
    "search": '<circle cx="11" cy="11" r="7"/><path d="M16.5 16.5 21 21"/>',
    "sun": (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41'
        'M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>'
    ),
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "shield": '<path d="M12 3 4 6v6c0 4.5 3.2 7.8 8 9 4.8-1.2 8-4.5 8-9V6z"/>',
    "layers": (
        '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 12 9 5 9-5"/>'
        '<path d="m3 16 9 5 9-5"/>'
    ),
    "info": (
        '<circle cx="12" cy="12" r="9"/>'
        '<path d="M12 11v6M12 7.5h.01"/>'
    ),
    "wrench": (
        '<path d="m14.7 6.3 3-3a5 5 0 0 0-6.4 6.4L4 17a2.8 2.8 0 1 0 4 4l7.3-7.3a5 5 0 0 0 6.4-6.4l-3 3z"/>'
    ),
    "route": (
        '<circle cx="6" cy="5" r="2"/><circle cx="18" cy="19" r="2"/>'
        '<path d="M6 7v3c0 2 2 3 4 3h4c2 0 4 1 4 3v1"/>'
    ),
    "shield-alert": (
        '<path d="M12 3 4 6v6c0 4.5 3.2 7.8 8 9 4.8-1.2 8-4.5 8-9V6z"/>'
        '<path d="M12 8v4M12 15.5h.01"/>'
    ),
    "bell": (
        '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>'
        '<path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>'
    ),
    "activity": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    "video": '<rect x="2" y="6" width="14" height="12" rx="2"/><path d="m22 8-6 4 6 4z"/>',
    "video-off": (
        '<rect x="2" y="6" width="14" height="12" rx="2"/>'
        '<path d="m22 8-6 4 6 4z"/><path d="M2 2l20 20"/>'
    ),
    "cpu": (
        '<rect x="5" y="5" width="14" height="14" rx="2"/>'
        '<rect x="9" y="9" width="6" height="6"/>'
        '<path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>'
    ),
    "server": (
        '<rect x="3" y="3" width="18" height="7" rx="2"/>'
        '<rect x="3" y="14" width="18" height="7" rx="2"/>'
        '<path d="M7 6.5h.01M7 17.5h.01"/>'
    ),
    "file-warning": (
        '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 3v5h5"/><path d="M12 11v4M12 18h.01"/>'
    ),
    "layout-dashboard": (
        '<rect x="3" y="3" width="7" height="9" rx="1"/>'
        '<rect x="14" y="3" width="7" height="5" rx="1"/>'
        '<rect x="14" y="12" width="7" height="9" rx="1"/>'
        '<rect x="3" y="16" width="7" height="5" rx="1"/>'
    ),
    "settings": (
        '<path d="M3 6h10M19 6h2M3 12h4M13 12h8M3 18h12"/>'
        '<circle cx="16" cy="6" r="2.5"/>'
        '<circle cx="10" cy="12" r="2.5"/>'
        '<circle cx="18" cy="18" r="2.5"/>'
    ),
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7"/>',
}

_STROKE_WIDTH = 2.0


def set_icon_theme(name: str) -> None:
    """Switch the icon tint (and the shared painted-widget palette) to dark or light."""
    theme.set_current(name)
    _render.cache_clear()


def tone_color(tone: str) -> str:
    """Map a tone name used in the UI to a hex color of the current palette."""
    p = theme.get_palette()
    return {
        "text": p.text,
        "dim": p.text_dim,
        "muted": p.muted,
        "accent": p.accent,
        "good": p.good,
        "warn": p.warn,
        "bad": p.bad,
    }.get(tone, p.text)


def _device_ratio() -> float:
    screen = QGuiApplication.primaryScreen()
    ratio = screen.devicePixelRatio() if screen is not None else 1.0
    return max(2.0, float(ratio))  # render at least 2x so icons stay sharp when scaled


@lru_cache(maxsize=512)
def _render(name: str, size: int, color: str, ratio: float) -> QPixmap:
    body = _ICONS.get(name, _ICONS["shield"])
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="{_STROKE_WIDTH}" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixels = max(1, int(round(size * ratio)))
    pixmap = QPixmap(pixels, pixels)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def icon_pixmap(name: str, size: int, tone_or_color: str = "text") -> QPixmap:
    """A pixmap of the named icon. Pass a tone name ("accent") or a "#rrggbb" color."""
    color = tone_or_color if tone_or_color.startswith("#") else tone_color(tone_or_color)
    return _render(name, int(size), color, _device_ratio())


class IconLabel(QLabel):
    """A fixed-size label that shows one icon and re-tints itself on theme change."""

    def __init__(
        self,
        name: str,
        size: int = 18,
        tone: str = "text",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        self._size = int(size)
        self._tone = tone
        self.setFixedSize(self._size, self._size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.retint()

    def set_icon(self, name: str, tone: str | None = None) -> None:
        self._name = name
        if tone is not None:
            self._tone = tone
        self.retint()

    def retint(self) -> None:
        self.setPixmap(icon_pixmap(self._name, self._size, self._tone))


class IconButton(QPushButton):
    """A flat push button with an icon that re-tints itself on theme change."""

    def __init__(self, name: str, size: int = 18, tone: str = "text", parent=None) -> None:
        super().__init__(parent)
        self._name = name
        self._size = int(size)
        self._tone = tone
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retint()

    def retint(self) -> None:
        self.setIcon(QIcon(icon_pixmap(self._name, self._size, self._tone)))
        self.setIconSize(QSize(self._size, self._size))
