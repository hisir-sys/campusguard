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
    ink: str  # accent for text/icons/lines drawn on surfaces (deep green in light mode)


DARK = Palette(
    "dark",
    "#090C0A", "#090C0A",
    "#C8FF52", 9, "#879080", 6,
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
    "#C8FF52",
)

LIGHT = Palette(
    "light",
    "#E8E8E6", "#E8E8E6",
    "#C8FF52", 14, "#171B16", 4,
    "#20211F", "#414340", "#747672",
    "#A6D84B", "#B9E56A",
    "#277A4C", "#986D0C", "#C74752",
    "#F0F0EE", 232,
    "#292B28", 30,
    "#20211F", 10,
    "#DADAD8", 232,
    "#E5E5E3", 245,
    "#A6D84B",
    12,
    "#F0F0EE",
    "#456A1C",
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
  font-size: @base_pt@pt;
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
  background: @card@;
  border: 1px solid @card_line@;
  border-radius: 18px;
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
QFrame#cameraPreview, QFrame#offlineCameraTile {
  background: transparent;
  border: none;
  border-radius: 14px;
}
QLabel[videoSurface="true"] {
  background: #0B0F0D;
  border: 1px solid @line_strong@;
  border-radius: 14px;
  color: #98A296;
}
QFrame#cameraPreview:hover QLabel[videoSurface="true"] {
  border-color: @accent_line@;
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
  background: transparent; border: none; color: @ink@;
  padding: 2px 4px; font-weight: 600;
}
QPushButton[link="true"]:hover { color: @text@; }

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
QComboBox::drop-down { border: none; width: 28px; background: transparent; }
QComboBox::down-arrow { image: url(@chev_down@); width: 12px; height: 12px; }
QSpinBox::up-button, QDoubleSpinBox::up-button {
  subcontrol-origin: border; subcontrol-position: top right;
  width: 22px; border: none; background: transparent; margin: 2px 2px 0 0;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
  subcontrol-origin: border; subcontrol-position: bottom right;
  width: 22px; border: none; background: transparent; margin: 0 2px 2px 0;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url(@chev_up@); width: 10px; height: 10px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url(@chev_down@); width: 10px; height: 10px; }
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
  background: @ink@; border: 1px solid @ink@; image: url(@check_icon@);
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

QTabWidget::pane {
  background: transparent; border: none; top: 6px;
}
QTabWidget > QWidget { background: transparent; }
QTabBar { background: transparent; qproperty-drawBase: 0; }
QTabBar::tab {
  background: @veil@; color: @text_dim@;
  border: 1px solid @line_soft@; border-radius: 9px;
  padding: 8px 18px; margin: 0 6px 0 0; font-weight: 600;
}
QTabBar::tab:hover { color: @text@; border-color: @line_strong@; }
QTabBar::tab:selected {
  background: @veil_hover@; color: @text@; border-color: @accent_line@;
}
QGroupBox {
  background: transparent; border: 1px solid @line@; border-radius: 12px;
  margin-top: 14px; padding: 14px 10px 10px 10px;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: @text_dim@; font-weight: 600; }
QListWidget, QListView, QTreeView, QTextEdit, QPlainTextEdit {
  background: @field@; color: @text@; border: 1px solid @line@; border-radius: 10px;
  selection-background-color: @select@; selection-color: @text@;
}
QListWidget::item { padding: 6px 8px; }
QListWidget::item:selected { background: @select@; color: @text@; }
QMenu {
  background: @popup@; color: @text@; border: 1px solid @line_strong@;
  border-radius: 10px; padding: 6px;
}
QMenu::item { padding: 7px 18px; border-radius: 6px; }
QMenu::item:selected { background: @veil_hover@; }
QProgressBar { background: @veil@; border: none; border-radius: 4px; text-align: center; color: @text@; }
QProgressBar::chunk { background: @ink@; border-radius: 4px; }

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


# Base font size in points; chosen from the screen size (see screen_fit.py).
_base_pt = 10


def set_base_pt(points: int) -> None:
    global _base_pt
    _base_pt = max(8, min(14, int(points)))


def set_compact(compact: bool) -> None:
    set_base_pt(9 if compact else 10)


def is_compact() -> bool:
    return _base_pt < 10


def _ui_assets(p: "Palette") -> dict[str, str]:
    """Write the small tick/chevron SVGs QSS needs (QSS can only reference files)."""
    import tempfile
    from pathlib import Path

    folder = Path(tempfile.gettempdir()) / "campusguard-ui"
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return {"check_icon": "", "chev_down": "", "chev_up": ""}

    def svg(name: str, body: str, color: str, width: float) -> str:
        path = folder / f"{name}-{p.name}.svg"
        text = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
        )
        try:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                path.write_text(text, encoding="utf-8")
        except OSError:
            return ""
        return path.as_posix()

    tick = "#090C0A" if p.name == "dark" else "#FFFFFF"
    return {
        "check_icon": svg("check", '<path d="m5 12.5 4.5 4.5L19 7.5"/>', tick, 3.2),
        "chev_down": svg("chev-down", '<path d="m6 9 6 6 6-6"/>', p.text_dim, 2.4),
        "chev_up": svg("chev-up", '<path d="m6 15 6-6 6 6"/>', p.text_dim, 2.4),
    }


def build_qss(theme: str) -> str:
    p = LIGHT if theme == "light" else DARK
    k = 20 if p.name == "light" else 10  # light surfaces need stronger hairlines
    values = {
        "text": p.text, "text_dim": p.text_dim, "muted": p.muted,
        "accent": p.accent, "accent_hover": p.accent_hover,
        "good": p.good, "warn": p.warn, "bad": p.bad,
        "bg1": p.bg1, "popup": rgba(p.glass, 188 if p.name == "dark" else 196),
        "glass": rgba(p.glass, p.glass_alpha),
        "card": p.surface,
        "card_line": rgba(p.line, 17 if p.name == "dark" else 44),
        "glass_line": rgba(p.line, 14 * k // 10),
        "line": rgba(p.line, 18 * k // 10),
        "line_soft": rgba(p.line, 11 * k // 10),
        "line_strong": rgba(p.line, 32 * k // 10),
        "veil": rgba(p.veil, p.veil_alpha),
        "veil_hover": rgba(p.ink, 14 if p.name == "dark" else 12),
        "veil_press": rgba(p.ink, 22 if p.name == "dark" else 20),
        "field": rgba(p.field, p.field_alpha),
        "table": rgba(p.surface, max(210, p.surface_alpha - 24)),
        "table_alt": rgba(p.veil, 4),
        "select": rgba(p.accent, 58 if p.name == "dark" else 120),
        "handle": rgba(p.text, 62),
        "handle_hover": rgba(p.text, 110),
        "bad_line": rgba(p.bad, 100),
        "accent_line": rgba(p.ink, 190)
        , "ink": p.ink,
        "base_pt": str(_base_pt),
        **_ui_assets(p),
    }
    qss = _QSS
    for key, value in values.items():
        qss = qss.replace(f"@{key}@", value)
    return qss
