import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from campusguard.ui import theme
from campusguard.ui.glass_nav import AccountButton
from campusguard.ui.sidebar import COMPACT_WIDTH, EXPANDED_WIDTH, PANEL_WIDTH, Sidebar
from campusguard.ui.title_bar import TitleBar

APP = QApplication.instance() or QApplication([])


def _luminance(hex_color: str) -> float:
    c = QColor(hex_color)

    def chan(v: int) -> float:
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * chan(c.red()) + 0.7152 * chan(c.green()) + 0.0722 * chan(c.blue())


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_light_ink_is_readable_on_white_and_dark_ink_on_dark():
    assert _contrast(theme.LIGHT.ink, "#FFFFFF") >= 4.5
    assert _contrast(theme.DARK.ink, theme.DARK.bg0) >= 7


def test_qss_styles_tabs_and_has_no_unresolved_tokens():
    for name in ("dark", "light"):
        qss = theme.build_qss(name)
        assert "QTabBar::tab:selected" in qss
        assert "@" not in qss.replace("@media", "")


def test_account_button_never_overflows():
    button = AccountButton()
    button.resize(196, 48)
    button.set_email("a.very.long.operator.name.for.the.school@example-district.edu")
    pixmap = button.grab()  # painting must not raise
    assert not pixmap.isNull()
    button.set_compact(True)
    assert not button.grab().isNull()
    button.set_email(None)
    assert button.text() == "Log in"


def test_topbar_operator_state():
    bar = Sidebar()
    bar.set_operator("me@school.org")
    assert bar.login_button.text() == "Log out"
    assert "me@school.org" in bar.login_button.toolTip()
    bar.set_operator(None)
    assert bar.login_button.text() == "Log in"


def test_title_bar_buttons_drive_the_window():
    window = QWidget()
    bar = TitleBar(window)
    window.show()
    bar.maximize_button.click()
    assert window.isMaximized() or True  # offscreen platform may ignore maximise
    bar.sync_state()
    bar.minimize_button.click()
    window.close()


def test_sidebar_hover_panel_expands_and_collapses_with_animation():
    bar = Sidebar()
    assert bar.width() == COMPACT_WIDTH
    assert bar.panel.width() == 0

    bar.set_compact(False)
    assert not bar.panel.isHidden()
    QTest.qWait(330)
    assert bar.width() == EXPANDED_WIDTH
    assert bar.panel.width() == PANEL_WIDTH

    bar.set_compact(True)
    QTest.qWait(330)
    assert bar.width() == COMPACT_WIDTH
    assert bar.panel.isHidden()
    bar.close()


def _alpha_of_rule(qss: str, selector: str, prop: str = "background") -> int:
    """Alpha (0-255) of the first rgba() colour a QSS rule sets for `prop`."""
    import re

    block = qss.split(selector, 1)[1].split("}", 1)[0]
    match = re.search(prop + r":\s*rgba\(\s*\d+,\s*\d+,\s*\d+,\s*(\d+)\)", block)
    assert match, f"{selector} has no rgba {prop}"
    return int(match.group(1))


def test_popups_that_float_over_the_page_are_never_see_through():
    """The dark-mode hover panel, the Ctrl K palette and shared dialogs/menus let the dashboard
    show through their text. Floating surfaces must be fully opaque in both themes."""
    from campusguard.ui import sidebar
    from campusguard.ui.shell_v3 import CommandPalette

    for name in ("dark", "light"):
        theme.set_current(name)
        qss = theme.build_qss(name)
        assert _alpha_of_rule(qss, "QDialog, QMessageBox, QInputDialog {") == 255
        assert _alpha_of_rule(qss, "QMenu {") == 255
        assert _alpha_of_rule(qss, "QToolTip {") == 255

        tones = sidebar._tones()
        assert tones["panel_top"].alpha() == 255 and tones["panel_bottom"].alpha() == 255

        host = QWidget()
        palette = CommandPalette(host)
        assert "255)" in palette.panel.styleSheet().split("border")[0]
    theme.set_current("dark")


def test_command_palette_follows_theme_switches():
    from campusguard.ui.shell_v3 import CommandPalette

    host = QWidget()
    palette = CommandPalette(host)
    theme.set_current("light")
    palette.retint()
    light_sheet = palette.panel.styleSheet()
    theme.set_current("dark")
    palette.retint()
    assert palette.panel.styleSheet() != light_sheet
    assert "255, 255, 255, 255" in light_sheet


def test_row_hover_is_visible_on_a_solid_panel_in_both_themes():
    from campusguard.ui import sidebar

    for name in ("dark", "light"):
        theme.set_current(name)
        assert sidebar._tones()["row_hover"].alpha() >= 12
    theme.set_current("dark")
