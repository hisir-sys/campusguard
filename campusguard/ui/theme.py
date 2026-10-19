"""CampusGuard visual system: restrained indigo glass, 8pt spacing, dark/light parity."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class Palette:
    name: str
    bg0: str
    bg1: str
    glow1: str
    glow1_alpha: int
    glow2: str
    glow2_alpha: int
    text: str
    text_dim: str
    muted: str
    accent: str
    accent_hover: str
    good: str
    warn: str
    bad: str
    surface: str
    surface_alpha: int
    line: str
    line_alpha: int
    veil: str
    veil_alpha: int
    glass: str
    glass_alpha: int
    field: str
    field_alpha: int
    edge: str
    sheen_alpha: int
    popup: str


DARK = Palette(
    "dark",
    "#090C0A", "#090C0A",
    "#C8FF52", 14, "#879080", 8,
    "#F7F8F4", "#D2D8CE", "#8D958B",
    "#C8FF52", "#D8FF83",
    "#6DD6A0", "#E5B85C", "#F06B70",
    "#111512", 224,
    "#F7F8F4", 25,
    "#F7F8F4", 12,
    "#111512", 224,
    "#0D100E", 245,
    "#C8FF52",
    8,
    "#111512",
)

LIGHT = Palette(
    "light",
    "#F7F8F4", "#F7F8F4",
    "#C8FF52", 22, "#171B16", 5,
    "#171B16", "#3D443B", "#6D746B",
    "#C8FF52", "#D8FF83",
    "#277A4C", "#986D0C", "#C74752",
    "#FFFFFF", 225,
    "#171B16", 22,
    "#171B16", 8,
    "#FFFFFF", 225,
    "#FFFFFF", 245,
    "#91C82A",
    18,
    "#FFFFFF",
)

_current: Palette = DARK


def set_current(name: str) -> None:
    global _current
    _current = LIGHT if name == "light" else DARK


def get_palette() -> Palette:
    return _current


def qcolor(hex_color: str, alpha: int = 255) -> QColor:
    color = QColor(hex_color)
    color.setAlpha(max(0, min(255, int(alpha))))
    return color


def mix_colors(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def rgba(hex_color: str, alpha: int) -> str:
    color = QColor(hex_color)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {max(0, min(255, int(alpha)))})"


_QSS = """
QWidget {
  color: @text@;
  font-family: "DM Sans", "Segoe UI", sans-serif;
  font-size: 10pt;
}
QMainWindow { background: @bg1@; }\nQWidget#centralContent { background: transparent; }
QDialog, QMessageBox, QInputDialog {
  background: @popup@;
  color: @text@;
  border: 1px solid @glass_line@;
  border-radius: 20px;
}
QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel {
  color: @text@;
  background: transparent;
}
QDialog QPushButton, QMessageBox QPushButton, QInputDialog QPushButton {
  background: @veil@;
  color: @text@;
  border: 1px solid @line@;
  border-radius: 10px;
  padding: 8px 16px;
}
QDialog QPushButton:hover, QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {
  background: @veil_hover@;
  border-color: @accent_line@;
}
QStackedWidget, QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QStatusBar { background: transparent; color: @muted@; }
QStatusBar::item { border: none; }

QToolTip {
  background: @popup@; color: @text@;
  border: 1px solid @line_strong@;
  padding: 6px 9px; border-radius: 8px;
}

QFrame[card="true"] {
  background: @glass@;
  border: 1px solid @glass_line@;
  border-radius: 16px;
}
QFrame[tile="true"] {
  background: @veil@;
  border: 1px solid @line_soft@;
  border-radius: 10px;
}
QFrame#dashboardModelTile {
  background: @veil@;
  border: 1px solid @line_soft@;
  border-radius: 11px;
}
QFrame#dashboardStatTile {
  background: @veil@;
  border: 1px solid @line_soft@;
  border-radius: 11px;
}
QFrame#notificationRow {
  background: transparent;
  border: none;
  border-bottom: 1px solid @line_soft@;
}
QFrame#cameraPreview {
  background: @glass@;
  border: 1px solid @glass_line@;
  border-radius: 18px;
}
QLabel[videoSurface="true"] {
  background: @field@;
  border: 1px solid @line_soft@;
  color: @muted@;
}
QFrame#cameraPreview:hover {
  border-color: @line_strong@;
}
QFrame#dashboardStatTile:hover,
QFrame#dashboardModelTile:hover {
  border-color: @line_soft@;
  background: @veil_hover@;
}

QLabel { background: transparent; }
QLabel[muted="true"] { color: @muted@; }
QLabel[eyebrow="true"] {
  color: @muted@; font-size: 8pt; font-weight: 600;
}
QLabel[cardtitle="true"] {
  color: @text@; font-size: 10.5pt; font-weight: 600;
}
QLabel[kvlabel="true"] { color: @muted@; font-size: 9pt; font-weight: 500; }
QLabel[kvvalue="true"] { color: @text@; font-size: 10pt; font-weight: 700; }
QLabel[pill="true"] {
  background: @veil@; border: 1px solid @line_soft@;
  border-radius: 9px; padding: 3px 9px;
  color: @text_dim@; font-size: 8pt; font-weight: 600;
}
QLabel[tone="good"] { color: @good@; }
QLabel[tone="warn"] { color: @warn@; }
QLabel[tone="bad"] { color: @bad@; }

QPushButton {
  background: @veil@; color: @text@;
  border: 1px solid @line@; border-radius: 9px;
  padding: 8px 14px; font-weight: 500;
}
QPushButton:hover {
  background: @veil_hover@; border-color: @accent_line@;
}
QPushButton:pressed { background: @veil_press@; }
QPushButton:focus {
  border: 1px solid @line@;
  padding: 8px 14px;
}
QPushButton:disabled { color: @muted@; }
QPushButton[primary="true"] {
  background: @accent@; border-color: @accent@; color: #090C0A; font-weight: 700;
}
QPushButton[primary="true"]:hover {
  background: @accent_hover@; border-color: @accent_hover@;
}
QPushButton[danger="true"] { color: @bad@; border-color: @bad_line@; }
QPushButton[link="true"] {
  background: transparent; border: none; color: @accent@;
  padding: 2px 4px; font-weight: 600;
}
QPushButton[link="true"]:hover { color: @accent_hover@; }

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
  background: @field@; color: @text@;
  border: 1px solid @line@; border-radius: 9px;
  padding: 8px 9px;
  selection-background-color: @accent@; selection-color: #090C0A;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {
  border-color: @line_strong@;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
  border: 1px solid @line_strong@; padding: 8px 9px;
}
QComboBox QAbstractItemView {
  background: @popup@; color: @text@;
  border: 1px solid @line@;
  selection-background-color: @accent@; selection-color: #090C0A;
  outline: 0;
}

QCheckBox { spacing: 8px; font-weight: 500; }
QCheckBox::indicator {
  width: 16px; height: 16px; border-radius: 5px;
}
QCheckBox::indicator:checked {
  background: @accent@; border: 1px solid @accent@;
}
QCheckBox::indicator:unchecked {
  background: @field@; border: 1px solid @line_strong@;
}

QSlider::groove:horizontal {
  height: 4px; background: @line_strong@; border-radius: 2px;
}
QSlider::handle:horizontal {
  background: @accent@; width: 14px; margin: -5px 0; border-radius: 7px;
}

QTableWidget {
  background: @table@; alternate-background-color: @table_alt@;
  gridline-color: @line_soft@; border: 1px solid @line@; border-radius: 12px;
}
QTableWidget::item { padding: 7px; }
QTableWidget::item:selected { background: @select@; color: @text@; }
QTableCornerButton::section { background: transparent; border: none; }
QHeaderView::section {
  background: @veil@; color: @text_dim@; border: none;
  border-bottom: 1px solid @line@;
  padding: 10px 9px; font-size: 8pt; font-weight: 600;
}

QScrollBar:vertical { background: transparent; width: 7px; margin: 4px 0; }
QScrollBar::handle:vertical {
  background: @handle@; border-radius: 3px; min-height: 32px;
}
QScrollBar::handle:vertical:hover { background: @handle_hover@; }
QScrollBar:horizontal { background: transparent; height: 7px; margin: 0 4px; }
QScrollBar::handle:horizontal {
  background: @handle@; border-radius: 3px; min-width: 32px;
}
QScrollBar::handle:horizontal:hover { background: @handle_hover@; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


def build_qss(theme: str) -> str:
    p = LIGHT if theme == "light" else DARK
    values = {
        "text": p.text, "text_dim": p.text_dim, "muted": p.muted,
        "accent": p.accent, "accent_hover": p.accent_hover,
        "good": p.good, "warn": p.warn, "bad": p.bad,
        "bg1": p.bg1, "popup": rgba(p.glass, 188 if p.name == "dark" else 196),
        "glass": rgba(p.glass, p.glass_alpha),
        "glass_line": rgba(p.line, 14),
        "line": rgba(p.line, 18),
        "line_soft": rgba(p.line, 11),
        "line_strong": rgba(p.line, 32),
        "veil": rgba(p.veil, p.veil_alpha),
        "veil_hover": rgba(p.accent, 14),
        "veil_press": rgba(p.accent, 22),
        "field": rgba(p.field, p.field_alpha),
        "table": rgba(p.surface, max(210, p.surface_alpha - 24)),
        "table_alt": rgba(p.veil, 4),
        "select": rgba(p.accent, 58),
        "handle": rgba(p.text, 62),
        "handle_hover": rgba(p.text, 110),
        "bad_line": rgba(p.bad, 100),
        "accent_line": rgba(p.accent, 190),
    }
    qss = _QSS
    for key, value in values.items():
        qss = qss.replace(f"@{key}@", value)
    return qss
