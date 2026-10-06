"""Colors and the app-wide stylesheet for CampusGuard (dark + light, glass look).

Two things live here:

* ``Palette`` objects (DARK / LIGHT). Custom-painted widgets (the glass bars,
  nav buttons, backdrop) read colors from ``get_palette()`` every time they paint,
  so switching theme only needs a repaint.
* ``build_qss(theme)``. Everything that is a normal Qt widget (cards, buttons,
  tables, inputs...) is styled by this one stylesheet.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class Palette:
    name: str
    # window backdrop
    bg0: str
    bg1: str
    glow1: str
    glow1_alpha: int
    glow2: str
    glow2_alpha: int
    # text
    text: str
    text_dim: str
    muted: str
    # accent + status colors
    accent: str
    accent_hover: str
    good: str
    warn: str
    bad: str
    # translucent surfaces: a base color plus an alpha (0-255)
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
    # misc
    edge: str  # color of the bright streak on the top edge of the glass bars
    sheen_alpha: int  # strength of the soft light on the upper half of the bars
    popup: str  # opaque color for dropdown lists and dialogs


DARK = Palette(
    name="dark",
    bg0="#050A12",
    bg1="#0B1220",
    glow1="#4F8CFF",
    glow1_alpha=28,
    glow2="#6E7F95",
    glow2_alpha=24,
    text="#F3F6FA",
    text_dim="#B5C0CC",
    muted="#7E8B99",
    accent="#4F8CFF",
    accent_hover="#6B9DFF",
    good="#4CCB8A",
    warn="#E5B94F",
    bad="#F06464",
    surface="#111A27",
    surface_alpha=155,
    line="#D9E2EC",
    line_alpha=24,
    veil="#FFFFFF",
    veil_alpha=8,
    glass="#101A28",
    glass_alpha=155,
    field="#08101B",
    field_alpha=155,
    edge="#4F8CFF",
    sheen_alpha=14,
    popup="#111A27",
)

LIGHT = Palette(
    name="light",
    bg0="#F3F6FA",
    bg1="#E8EDF3",
    glow1="#4F8CFF",
    glow1_alpha=24,
    glow2="#8EA0B5",
    glow2_alpha=44,
    text="#14202D",
    text_dim="#425466",
    muted="#68798A",
    accent="#2F6FE4",
    accent_hover="#245FCB",
    good="#187A52",
    warn="#9A6A08",
    bad="#C43D3D",
    surface="#FFFFFF",
    surface_alpha=190,
    line="#25364A",
    line_alpha=24,
    veil="#14202D",
    veil_alpha=7,
    glass="#FFFFFF",
    glass_alpha=190,
    field="#FFFFFF",
    field_alpha=225,
    edge="#2F6FE4",
    sheen_alpha=42,
    popup="#FFFFFF",
)

_current: Palette = DARK


def set_current(name: str) -> None:
    """Remember which palette painted widgets should use."""
    global _current
    _current = LIGHT if name == "light" else DARK


def get_palette() -> Palette:
    return _current


def qcolor(hex_color: str, alpha: int = 255) -> QColor:
    color = QColor(hex_color)
    color.setAlpha(max(0, min(255, int(alpha))))
    return color


def mix_colors(a: QColor, b: QColor, t: float) -> QColor:
    """Blend from color a (t=0) to color b (t=1)."""
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def rgba(hex_color: str, alpha: int) -> str:
    """A CSS-style rgba(...) string, alpha 0-255, for use inside stylesheets."""
    color = QColor(hex_color)
    alpha = max(0, min(255, int(alpha)))
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"


# The stylesheet uses @name@ placeholders (filled in by build_qss) so the CSS
# braces do not have to be escaped.
_QSS = """
QWidget { color: @text@; font-family: "Segoe UI", "Inter", sans-serif; font-size: 10pt; }
QMainWindow { background: @bg1@; }
QDialog { background: @popup@; }
QStackedWidget { background: transparent; border: none; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QStatusBar { background: @bg1@; color: @muted@; }
QStatusBar::item { border: none; }
QToolTip {
  background: @popup@; color: @text@; border: 1px solid @line_strong@;
  padding: 4px 7px; border-radius: 6px;
}

QFrame[card="true"] {
  background: @glass@;
  border: 1px solid @glass_line@;
  border-radius: 18px;
}
QFrame[tile="true"] {
  background: @veil@;
  border: 1px solid @line_soft@;
  border-radius: 12px;
}

QLabel { background: transparent; }
QLabel[muted="true"] { color: @muted@; }
QLabel[eyebrow="true"] { color: @muted@; font-size: 8pt; font-weight: 700; }
QLabel[cardtitle="true"] { font-size: 11pt; font-weight: 700; }
QLabel[kvlabel="true"] { color: @muted@; }
QLabel[kvvalue="true"] { font-weight: 600; }
QLabel[pill="true"] {
  background: @veil@; border: 1px solid @line_soft@; border-radius: 10px;
  padding: 2px 10px; color: @text_dim@; font-size: 8pt; font-weight: 600;
}
QLabel[tone="good"] { color: @good@; }
QLabel[tone="warn"] { color: @warn@; }
QLabel[tone="bad"] { color: @bad@; }

QPushButton {
  background: @veil@; color: @text@; border: 1px solid @line@;
  border-radius: 9px; padding: 7px 14px;
}
QPushButton:hover { background: @veil_hover@; border-color: @line_strong@; }
QPushButton:pressed { background: @veil_press@; }
QPushButton:disabled { color: @muted@; }
QPushButton[primary="true"] { background: @accent@; border-color: @accent@; color: #ffffff; }
QPushButton[primary="true"]:hover { background: @accent_hover@; border-color: @accent_hover@; }
QPushButton[danger="true"] { color: @bad@; border-color: @bad_line@; }
QPushButton[link="true"] {
  background: transparent; border: none; color: @accent@;
  padding: 0 2px; font-weight: 600;
}
QPushButton[link="true"]:hover { background: transparent; color: @accent_hover@; }

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
  background: @field@; border: 1px solid @line@; border-radius: 8px;
  padding: 7px; selection-background-color: @accent@; selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
  border: 1px solid @accent_line@;
}
QComboBox QAbstractItemView {
  background: @popup@; border: 1px solid @line@;
  selection-background-color: @accent@; selection-color: #ffffff; outline: 0;
}

QTableWidget {
  background: @table@; alternate-background-color: @table_alt@;
  gridline-color: @line_soft@; border: 1px solid @line@; border-radius: 12px;
}
QTableWidget::item:selected { background: @select@; color: @text@; }
QTableCornerButton::section { background: transparent; border: none; }
QHeaderView::section {
  background: @veil@; color: @text_dim@; border: 0;
  border-bottom: 1px solid @line@; padding: 8px; font-weight: 700;
}

QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 15px; height: 15px; }
QCheckBox::indicator:checked { background: @accent@; border: 1px solid @accent@; border-radius: 4px; }
QCheckBox::indicator:unchecked { background: @field@; border: 1px solid @line_strong@; border-radius: 4px; }

QSlider::groove:horizontal { height: 4px; background: @line_strong@; border-radius: 2px; }
QSlider::handle:horizontal { background: @accent@; width: 14px; margin: -5px 0; border-radius: 7px; }

QScrollBar:vertical { background: transparent; width: 6px; margin: 3px 0; }
QScrollBar::handle:vertical { background: @handle@; border-radius: 3px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: @handle_hover@; }
QScrollBar:horizontal { background: transparent; height: 6px; margin: 0 3px; }
QScrollBar::handle:horizontal { background: @handle@; border-radius: 3px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: @handle_hover@; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


def build_qss(theme: str) -> str:
    p = LIGHT if theme == "light" else DARK
    values = {
        "text": p.text,
        "text_dim": p.text_dim,
        "muted": p.muted,
        "accent": p.accent,
        "accent_hover": p.accent_hover,
        "good": p.good,
        "warn": p.warn,
        "bad": p.bad,
        "bg1": p.bg1,
        "popup": p.popup,
        "surface": rgba(p.surface, p.surface_alpha),
        "glass": rgba(p.glass, p.glass_alpha),
        "glass_line": rgba(p.line, min(255, int(p.line_alpha * 1.35))),
        "line": rgba(p.line, p.line_alpha),
        "line_soft": rgba(p.line, int(p.line_alpha * 0.6)),
        "line_strong": rgba(p.line, int(p.line_alpha * 2.4)),
        "veil": rgba(p.veil, p.veil_alpha),
        "veil_hover": rgba(p.veil, int(p.veil_alpha * 2.2)),
        "veil_press": rgba(p.veil, int(p.veil_alpha * 3.2)),
        "field": rgba(p.field, p.field_alpha),
        "table": rgba(p.surface, max(0, p.surface_alpha - 30)),
        "table_alt": rgba(p.veil, int(p.veil_alpha * 0.6)),
        "select": rgba(p.accent, 70),
        "handle": rgba(p.text, 70),
        "handle_hover": rgba(p.text, 130),
        "bad_line": rgba(p.bad, 110),
        "accent_line": rgba(p.accent, 170),
    }
    qss = _QSS
    for key, value in values.items():
        qss = qss.replace(f"@{key}@", value)
    return qss
