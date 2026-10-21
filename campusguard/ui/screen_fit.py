"""Pick a window size, minimum size and base font that suit the user's screen.

All numbers are in Qt's device-independent pixels, i.e. already divided by the
Windows display-scale (a 1920x1080 laptop at 150% reports 1280x720).
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_WIDTH = 1920
MAX_HEIGHT = 1200
MAX_ASPECT = 1.85  # keeps ultra-wide monitors from getting a stretched window
USABLE_FRACTION = 0.92


@dataclass(frozen=True)
class ScreenFit:
    width: int
    height: int
    min_width: int
    min_height: int
    maximize: bool  # small laptop screens: use every pixel
    base_pt: int  # base font size for the stylesheet


def base_font_pt(avail_width: int, avail_height: int) -> int:
    if avail_width < 1500 or avail_height < 860:
        return 9
    if avail_width >= 2300 and avail_height >= 1300:
        return 11
    return 10


def compute_fit(avail_width: int, avail_height: int) -> ScreenFit:
    avail_width = max(640, int(avail_width))
    avail_height = max(480, int(avail_height))
    usable_h = int(avail_height * USABLE_FRACTION)
    usable_w = int(avail_width * USABLE_FRACTION)
    height = min(usable_h, MAX_HEIGHT)
    width = min(usable_w, MAX_WIDTH, int(height * MAX_ASPECT))
    return ScreenFit(
        width=width,
        height=height,
        min_width=min(1080, width),
        min_height=min(700, height),
        maximize=avail_width <= 1400 or avail_height <= 800,
        base_pt=base_font_pt(avail_width, avail_height),
    )
