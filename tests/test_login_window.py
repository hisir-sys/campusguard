import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from campusguard import auth, auth_config
from campusguard.ui import login_window, theme

APP = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _dark_after():
    yield
    theme.set_current("dark")


def _dialog(monkeypatch, name="dark", prefill="", notice=""):
    monkeypatch.setattr(login_window, "saved_theme", lambda: name)
    dialog = login_window.LoginDialog(prefill, notice)
    dialog.show()
    APP.processEvents()
    return dialog


@pytest.mark.parametrize("name", ["dark", "light"])
def test_login_follows_the_saved_theme(monkeypatch, name):
    dialog = _dialog(monkeypatch, name)
    assert theme.get_palette().name == name
    assert not dialog.grab().isNull()
    dialog.close()


def test_show_button_is_wide_enough_for_both_labels(monkeypatch):
    dialog = _dialog(monkeypatch)
    metrics = dialog.show_password.fontMetrics()
    widest = max(metrics.horizontalAdvance("Show"), metrics.horizontalAdvance("Hide"))
    assert dialog.show_password.width() >= widest + 24  # was clipped to "Sho w" before
    dialog.show_password.setChecked(True)
    assert dialog.password.echoMode() == login_window.QLineEdit.EchoMode.Normal
    assert dialog.show_password.text() == "Hide"
    dialog.close()


def test_message_is_visible_and_never_overlaps_the_form(monkeypatch):
    dialog = _dialog(monkeypatch)
    dialog._show_message("That email or password is not right. Check them and try again.", "error")
    APP.processEvents()
    assert dialog.message.isVisible()
    gap = dialog.email_label.geometry().top() - dialog.message.geometry().bottom()
    assert gap >= 10, "error box must not touch the Email label"
    dialog._show_message("", "info")
    assert not dialog.message.isVisible()
    dialog.close()


def test_reset_mode_swaps_the_form_and_back(monkeypatch):
    dialog = _dialog(monkeypatch)
    dialog._toggle_reset_mode()
    assert dialog.title.text() == "Reset password"
    assert not dialog.password_row.isVisible() and not dialog.apply_link.isVisible()
    assert dialog.submit.text() == "Send reset link"
    dialog._toggle_reset_mode()
    assert dialog.title.text() == "Sign in" and dialog.password_row.isVisible()
    dialog.close()


def test_auth_errors_are_shown_with_the_right_tone(monkeypatch):
    dialog = _dialog(monkeypatch)
    dialog._failed(auth.AuthError("Pending review", kind="pending"))
    assert dialog.message.property("kind") == "info"
    dialog._failed(auth.AuthError("Wrong password", kind="error"))
    assert dialog.message.property("kind") == "error"
    dialog._failed(RuntimeError("boom"))
    assert "Something went wrong" in dialog.message.text()
    assert "boom" not in dialog.message.text()  # internal errors never reach the screen
    dialog.close()


def test_successful_sign_in_stores_the_session_and_clears_the_password(monkeypatch):
    saved = []
    monkeypatch.setattr(auth, "save_session", lambda session: saved.append(session))
    dialog = _dialog(monkeypatch)
    dialog.password.setText("a-secret-password")
    session = auth.Session(email="a@school.edu", access_token="t", refresh_token="r")
    dialog._signed_in(session)
    assert dialog.session is session and saved == [session]
    assert dialog.password.text() == ""
    assert dialog.result() == login_window.QDialog.DialogCode.Accepted


def test_privacy_policy_link_opens_the_website_policy(monkeypatch):
    opened = []
    monkeypatch.setattr(login_window.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    dialog = _dialog(monkeypatch)
    dialog.privacy_link.click()
    assert opened == [auth_config.WEBSITE_URL + "/privacy"]
    dialog.close()


def test_password_manager_friendly_prefill_focuses_the_password(monkeypatch):
    dialog = _dialog(monkeypatch, prefill="head@school.edu")
    assert dialog.email.text() == "head@school.edu"
    assert dialog.password.hasFocus() or dialog.focusWidget() is dialog.password
    dialog.close()
    QTest.qWait(10)
