"""One place for how a severity (LOW/MEDIUM/HIGH/CRITICAL) is named and coloured in the UI.

Names match the pop-up alert: MEDIUM = ALERT, HIGH = CRITICAL ALERT, CRITICAL = DANGER.
"""
from __future__ import annotations

SEVERITY_TITLES = {"LOW": "LOW", "MEDIUM": "ALERT", "HIGH": "CRITICAL ALERT", "CRITICAL": "DANGER"}
SEVERITY_COLORS = {"LOW": "#8DB4A0", "MEDIUM": "#C4B085", "HIGH": "#C79A7E", "CRITICAL": "#C58790"}
URGENT = {"HIGH", "CRITICAL"}


def severity_title(severity: str) -> str:
    value = str(severity).upper()
    return SEVERITY_TITLES.get(value, value)


LIGHT_THEME_COLORS = {"LOW": "#3F6B57", "MEDIUM": "#75613A", "HIGH": "#85553A", "CRITICAL": "#8B4048"}


def _is_light_theme() -> bool:
    try:
        from PySide6.QtGui import QColor

        from campusguard.ui.theme import get_palette

        return QColor(get_palette().text).lightness() < 128      # dark text = light theme
    except Exception:
        return False


def severity_color(severity: str) -> str:
    table = LIGHT_THEME_COLORS if _is_light_theme() else SEVERITY_COLORS
    return table.get(str(severity).upper(), table["LOW"])
