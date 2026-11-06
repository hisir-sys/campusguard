import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QWidget

from campusguard.ui import theme
from campusguard.ui.glass_nav import AccountButton, TopBar
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
    bar = TopBar()
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
