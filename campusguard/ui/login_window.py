"""CampusGuard sign-in window, shown before any camera or AI work starts."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from campusguard import auth, auth_config
from campusguard.ui.common import apply_theme
from campusguard.ui.icons import logo_pixmap
from campusguard.ui.theme import get_palette, rgba
from campusguard.ui.workers import Worker


class LoginDialog(QDialog):
    """Email + password sign-in using the website account. ``session`` is set on accept."""

    def __init__(self, prefill_email: str = "", notice: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session: auth.Session | None = None
        self._worker: Worker | None = None
        self._reset_mode = False

        self.setWindowTitle("CampusGuard — Sign in")
        self.setWindowIcon(self._app_icon())
        self.setModal(True)
        self.setFixedWidth(460)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 32, 36, 28)
        root.setSpacing(0)

        logo = QLabel()
        logo.setPixmap(logo_pixmap(48))
        logo.setFixedSize(48, 48)
        root.addWidget(logo)
        root.addSpacing(18)

        self.eyebrow = QLabel("CUSTOMER SIGN IN")
        self.eyebrow.setObjectName("loginEyebrow")
        root.addWidget(self.eyebrow)
        root.addSpacing(6)

        self.title = QLabel("Welcome back.")
        self.title.setObjectName("loginTitle")
        root.addWidget(self.title)
        root.addSpacing(8)

        self.intro = QLabel()
        self.intro.setObjectName("loginIntro")
        self.intro.setWordWrap(True)
        root.addWidget(self.intro)
        root.addSpacing(8)

        self.message = QLabel()
        self.message.setObjectName("loginMessage")
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setVisible(False)
        root.addWidget(self.message)
        root.addSpacing(10)

        self.email_label = QLabel("Email address")
        self.email = QLineEdit(prefill_email)
        self.email.setPlaceholderText("you@institution.org")
        self.email.setMaxLength(254)
        root.addWidget(self.email_label)
        root.addSpacing(6)
        root.addWidget(self.email)
        root.addSpacing(14)

        self.password_label = QLabel("Password")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Enter your password")
        self.password.setMaxLength(128)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self.password, 1)
        self.show_password = QPushButton("Show")
        self.show_password.setCheckable(True)
        self.show_password.setCursor(Qt.CursorShape.PointingHandCursor)
        self.show_password.setFixedWidth(64)
        self.show_password.toggled.connect(self._toggle_password)
        row.addWidget(self.show_password)
        self.password_row = QWidget()
        self.password_row.setLayout(row)
        root.addWidget(self.password_label)
        root.addSpacing(6)
        root.addWidget(self.password_row)
        root.addSpacing(20)

        self.submit = QPushButton("Log in")
        self.submit.setProperty("primary", True)
        self.submit.setDefault(True)
        self.submit.setMinimumHeight(42)
        self.submit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit.clicked.connect(self._submit)
        root.addWidget(self.submit)
        root.addSpacing(16)

        divider = QFrame()
        divider.setObjectName("loginDivider")
        divider.setFixedHeight(1)
        root.addWidget(divider)
        root.addSpacing(14)

        links = QHBoxLayout()
        links.setContentsMargins(0, 0, 0, 0)
        self.toggle_reset = self._link_button("Forgot password?")
        self.toggle_reset.clicked.connect(self._toggle_reset_mode)
        self.apply_link = self._link_button("Request early access ↗")
        self.apply_link.clicked.connect(lambda: self._open_website("/"))
        links.addWidget(self.toggle_reset)
        links.addStretch(1)
        links.addWidget(self.apply_link)
        root.addLayout(links)

        self.email.returnPressed.connect(self._submit)
        self.password.returnPressed.connect(self._submit)

        self._apply_mode()
        apply_theme(self, "dark")
        self._style()
        if notice:
            self._show_message(notice, "info")
        (self.password if prefill_email else self.email).setFocus()

    # ----- helpers -------------------------------------------------------

    @staticmethod
    def _app_icon():
        from PySide6.QtWidgets import QApplication

        return QApplication.windowIcon()

    @staticmethod
    def _link_button(text: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("loginLink")
        button.setFlat(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _style(self) -> None:
        pal = get_palette()
        self.setStyleSheet(
            self.styleSheet()
            + f"""
            QDialog {{ background: {pal.bg1}; border: 1px solid {rgba(pal.accent, 40)}; border-radius: 18px; }}
            QLabel {{ background: transparent; }}
            QLabel#loginEyebrow {{ color: {pal.accent}; font-size: 8pt; font-weight: 700; letter-spacing: 2px; }}
            QLabel#loginTitle {{ font-family: 'Manrope', 'DM Sans', 'Segoe UI'; font-size: 24pt; font-weight: 800; }}
            QLabel#loginIntro {{ color: {pal.text_dim}; font-size: 10pt; }}
            QLabel#loginMessage {{ border: 1px solid {rgba(pal.line, 30)}; border-radius: 10px; padding: 10px 12px; }}
            QLabel#loginMessage[kind="error"] {{ color: {pal.bad}; border-color: {rgba(pal.bad, 110)}; background: {rgba(pal.bad, 26)}; }}
            QLabel#loginMessage[kind="info"] {{ color: {pal.text}; border-color: {rgba(pal.accent, 90)}; background: {rgba(pal.accent, 22)}; }}
            QLabel#loginMessage[kind="success"] {{ color: {pal.good}; border-color: {rgba(pal.good, 110)}; background: {rgba(pal.good, 26)}; }}
            QFrame#loginDivider {{ background: {rgba(pal.line, 22)}; border: none; }}
            QPushButton#loginLink {{ background: transparent; border: none; color: {pal.text_dim}; padding: 4px 0; }}
            QPushButton#loginLink:hover {{ color: {pal.accent}; }}
            """
        )

    def _apply_mode(self) -> None:
        reset = self._reset_mode
        self.title.setText("Reset your password." if reset else "Welcome back.")
        self.intro.setText(
            "Enter your account email and we'll send a secure reset link if the account exists."
            if reset
            else "Sign in with the email and password you used when requesting early access."
        )
        self.password_label.setVisible(not reset)
        self.password_row.setVisible(not reset)
        self.submit.setText("Send reset link" if reset else "Log in")
        self.toggle_reset.setText("Back to log in" if reset else "Forgot password?")
        self.apply_link.setVisible(not reset)

    def _show_message(self, text: str, kind: str) -> None:
        self.message.setText(text)
        self.message.setProperty("kind", kind)
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        self.message.setVisible(bool(text))
        if text:
            # Word-wrapped labels need an explicit height for the dialog's fixed width.
            self.message.setMinimumHeight(self.message.heightForWidth(self.width() - 72))
        else:
            self.message.setMinimumHeight(0)
        self.layout().activate()
        self.adjustSize()

    def _set_busy(self, busy: bool) -> None:
        for widget in (self.email, self.password, self.show_password, self.toggle_reset, self.apply_link):
            widget.setEnabled(not busy)
        self.submit.setEnabled(not busy)
        if busy:
            self.submit.setText("Sending…" if self._reset_mode else "Checking…")
        else:
            self._apply_mode()

    def _toggle_password(self, shown: bool) -> None:
        self.password.setEchoMode(QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password)
        self.show_password.setText("Hide" if shown else "Show")

    def _toggle_reset_mode(self) -> None:
        self._reset_mode = not self._reset_mode
        self._show_message("", "info")
        self._apply_mode()
        self.adjustSize()

    @staticmethod
    def _open_website(path: str) -> None:
        QDesktopServices.openUrl(QUrl(auth_config.WEBSITE_URL + path))

    # ----- actions -------------------------------------------------------

    def _submit(self) -> None:
        if self._worker is not None:
            return
        email = self.email.text().strip()
        if self._reset_mode:
            func: Callable[[], object] = lambda: auth.request_password_reset(email)
            on_ok = self._reset_sent
        else:
            password = self.password.text()
            func = lambda: auth.login(email, password)
            on_ok = self._signed_in
        self._show_message("", "info")
        self._set_busy(True)
        worker = Worker(func, self)
        worker.succeeded.connect(on_ok)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._worker_done)
        self._worker = worker
        worker.start()

    def _worker_done(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.deleteLater()
        self._set_busy(False)

    def _signed_in(self, session: object) -> None:
        assert isinstance(session, auth.Session)
        auth.save_session(session)
        self.password.clear()
        self.session = session
        if self._worker is not None:
            self._worker.wait(2000)  # let the thread finish before the dialog is torn down
        self.accept()

    def _reset_sent(self, _result: object) -> None:
        self._show_message(
            "If an account exists for that email, a password-reset link will be sent. Check your inbox and spam folder.",
            "success",
        )

    def _failed(self, error: object) -> None:
        if isinstance(error, auth.AuthError):
            kind = "info" if error.kind in ("pending", "missing") else "error"
            self._show_message(str(error), kind)
        else:
            self._show_message("Something went wrong while signing in. Please try again.", "error")

    def reject(self) -> None:
        if self._worker is not None:
            self._worker.wait(3000)
        super().reject()
