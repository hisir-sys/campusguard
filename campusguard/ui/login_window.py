"""CampusGuard sign-in window, shown before any camera or AI work starts."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QGuiApplication
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
from campusguard.build_info import BUILD_VERSION
from campusguard.ui.brand_logo import LogoMark, saved_theme
from campusguard.ui.theme import get_palette, rgba
from campusguard.ui.workers import Worker


PRIVACY_URL_PATH = "/privacy"
ASIDE_FACTS = (
    "Works with the cameras you already have",
    "Alerts reach staff on WhatsApp",
    "Video stays on this PC or your school server",
)


class LoginDialog(QDialog):
    """Email + password sign-in using the website account. ``session`` is set on accept.

    Two panes: who we are on the left, the form on the right. It follows the theme the user
    saved, so it matches the launch screen and the app instead of always opening dark.
    """

    WIDTH = 840
    ASIDE_WIDTH = 316
    PAD = 44
    MIN_HEIGHT = 540

    def __init__(self, prefill_email: str = "", notice: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session: auth.Session | None = None
        self._worker: Worker | None = None
        self._reset_mode = False

        self.setObjectName("loginDialog")
        self.setWindowTitle("CampusGuard — Sign in")
        self.setWindowIcon(self._app_icon())
        self.setModal(True)
        screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry().width() - 40 if screen is not None else self.WIDTH
        self.setFixedWidth(max(620, min(self.WIDTH, available)))
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- left pane: brand --------------------------------------------------------
        self.aside = QFrame()
        self.aside.setObjectName("loginAside")
        self.aside.setFixedWidth(self.ASIDE_WIDTH)
        aside = QVBoxLayout(self.aside)
        aside.setContentsMargins(36, 40, 32, 30)
        aside.setSpacing(0)
        brand = QHBoxLayout()
        brand.setSpacing(12)
        brand.addWidget(LogoMark(size=36), 0, Qt.AlignmentFlag.AlignVCenter)
        wordmark = QLabel("CampusGuard")
        wordmark.setObjectName("loginWordmark")
        brand.addWidget(wordmark, 1, Qt.AlignmentFlag.AlignVCenter)
        aside.addLayout(brand)
        aside.addSpacing(56)
        headline = QLabel("Spot a fight as it starts.")
        headline.setObjectName("loginHeadline")
        headline.setWordWrap(True)
        aside.addWidget(headline)
        aside.addSpacing(12)
        lede = QLabel("CampusGuard watches your existing CCTV and tells the right person, quickly.")
        lede.setObjectName("loginLede")
        lede.setWordWrap(True)
        aside.addWidget(lede)
        aside.addSpacing(30)
        for fact in ASIDE_FACTS:
            row = QHBoxLayout()
            row.setSpacing(12)
            dot = QFrame()
            dot.setObjectName("loginDot")
            dot.setFixedSize(6, 6)
            slot = QWidget()  # nudges the bullet down to the optical centre of the first text line
            slot.setFixedSize(6, 20)
            QVBoxLayout(slot).setContentsMargins(0, 7, 0, 0)
            slot.layout().addWidget(dot)
            row.addWidget(slot, 0, Qt.AlignmentFlag.AlignTop)
            text = QLabel(fact)
            text.setObjectName("loginFact")
            text.setWordWrap(True)
            row.addWidget(text, 1)
            aside.addLayout(row)
            aside.addSpacing(14)
        aside.addStretch(1)
        self.version = QLabel(f"Version {BUILD_VERSION}")
        self.version.setObjectName("loginVersion")
        aside.addWidget(self.version)
        outer.addWidget(self.aside)

        # ---- right pane: form --------------------------------------------------------
        form = QWidget()
        form.setObjectName("loginForm")
        root = QVBoxLayout(form)
        root.setContentsMargins(self.PAD, 40, self.PAD, 26)
        root.setSpacing(0)

        self.eyebrow = QLabel("Customer account")
        self.eyebrow.setObjectName("loginEyebrow")
        root.addWidget(self.eyebrow)
        root.addSpacing(6)

        self.title = QLabel("Sign in")
        self.title.setObjectName("loginTitle")
        root.addWidget(self.title)
        root.addSpacing(8)

        self.intro = QLabel()
        self.intro.setObjectName("loginIntro")
        self.intro.setWordWrap(True)
        root.addWidget(self.intro)
        root.addSpacing(14)

        self.message = QLabel()
        self.message.setObjectName("loginMessage")
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setAccessibleName("Sign-in status")
        self.message.setVisible(False)
        root.addWidget(self.message)
        root.addSpacing(16)

        self.email_label = QLabel("Email address")
        self.email_label.setObjectName("loginFieldLabel")
        self.email = QLineEdit(prefill_email)
        self.email.setPlaceholderText("you@institution.org")
        self.email.setMaxLength(254)
        self.email.setMinimumHeight(44)
        self.email.setAccessibleName("Email address")
        self.email.setClearButtonEnabled(False)
        root.addWidget(self.email_label)
        root.addSpacing(6)
        root.addWidget(self.email)
        root.addSpacing(16)

        self.password_label = QLabel("Password")
        self.password_label.setObjectName("loginFieldLabel")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Enter your password")
        self.password.setMaxLength(128)
        self.password.setMinimumHeight(44)
        self.password.setAccessibleName("Password")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self.password, 1)
        self.show_password = QPushButton("Show")
        self.show_password.setObjectName("loginShow")
        self.show_password.setCheckable(True)
        self.show_password.setCursor(Qt.CursorShape.PointingHandCursor)
        self.show_password.setFixedSize(76, 44)
        self.show_password.setAccessibleName("Show or hide password")
        self.show_password.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.show_password.toggled.connect(self._toggle_password)
        row.addWidget(self.show_password)
        self.password_row = QWidget()
        self.password_row.setLayout(row)
        root.addWidget(self.password_label)
        root.addSpacing(6)
        root.addWidget(self.password_row)
        root.addSpacing(22)

        self.submit = QPushButton("Log in")
        self.submit.setProperty("primary", True)
        self.submit.setDefault(True)
        self.submit.setMinimumHeight(46)
        self.submit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit.clicked.connect(self._submit)
        root.addWidget(self.submit)
        root.addSpacing(16)

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
        root.addStretch(1)
        root.addSpacing(18)

        divider = QFrame()
        divider.setObjectName("loginDivider")
        divider.setFixedHeight(1)
        root.addWidget(divider)
        root.addSpacing(12)

        privacy = QHBoxLayout()
        privacy.setContentsMargins(0, 0, 0, 0)
        privacy.setSpacing(4)
        self.privacy_note = QLabel("Your email and password are used only to sign you in and check your approval.")
        self.privacy_note.setObjectName("loginPrivacy")
        self.privacy_note.setWordWrap(True)
        privacy.addWidget(self.privacy_note, 1)
        self.privacy_link = self._link_button("Privacy Policy ↗")
        self.privacy_link.clicked.connect(lambda: self._open_website(PRIVACY_URL_PATH))
        privacy.addWidget(self.privacy_link, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(privacy)
        outer.addWidget(form, 1)

        self.setTabOrder(self.email, self.password)
        self.setTabOrder(self.password, self.show_password)
        self.setTabOrder(self.show_password, self.submit)
        self.email.returnPressed.connect(self._submit)
        self.password.returnPressed.connect(self._submit)

        theme = saved_theme()
        apply_theme(self, theme)
        self._apply_mode()
        self._style()
        if notice:
            self._show_message(notice, "info")
        self._fit_height()
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
        dark = pal.name == "dark"
        form_bg = pal.bg1 if dark else "#F7F7F8"
        aside_bg = "#111113" if dark else "#EAEAEE"
        field_r = 12
        self.setStyleSheet(
            self.styleSheet()
            + f"""
            QDialog#loginDialog {{ background: {form_bg}; border: none; border-radius: 0; }}
            QWidget#loginForm {{ background: {form_bg}; }}
            QFrame#loginAside {{ background: {aside_bg}; border: none; border-right: 1px solid {rgba(pal.line, 30)}; border-radius: 0; }}
            QLabel {{ background: transparent; }}
            QLabel#loginWordmark {{ font-family: 'Outfit', 'Inter'; font-size: 14pt; font-weight: 600; color: {pal.text}; }}
            QLabel#loginHeadline {{ font-family: 'Outfit', 'Inter'; font-size: 20pt; font-weight: 600; color: {pal.text}; }}
            QLabel#loginLede {{ color: {pal.text_dim}; font-size: 10pt; }}
            QLabel#loginFact {{ color: {pal.text}; font-size: 9.5pt; }}
            QFrame#loginDot {{ background: {pal.lens}; border: none; border-radius: 3px; }}
            QLabel#loginVersion {{ color: {pal.muted}; font-family: 'JetBrains Mono', 'Consolas'; font-size: 8pt; }}
            QLabel#loginEyebrow {{ color: {pal.muted}; font-size: 9pt; font-weight: 500; }}
            QLabel#loginTitle {{ font-family: 'Outfit', 'Inter'; font-size: 24pt; font-weight: 600; color: {pal.text}; }}
            QLabel#loginIntro {{ color: {pal.text_dim}; font-size: 10pt; }}
            QLabel#loginFieldLabel {{ color: {pal.text_dim}; font-size: 9pt; font-weight: 500; }}
            QLabel#loginMessage {{ border: 1px solid {rgba(pal.line, 30)}; border-radius: 10px; padding: 10px 12px; }}
            QLabel#loginMessage[kind="error"] {{ color: {pal.bad}; border-color: {rgba(pal.bad, 110)}; background: {rgba(pal.bad, 26)}; }}
            QLabel#loginMessage[kind="info"] {{ color: {pal.text}; border-color: {rgba(pal.ink, 90)}; background: {rgba(pal.ink, 22)}; }}
            QLabel#loginMessage[kind="success"] {{ color: {pal.good}; border-color: {rgba(pal.good, 110)}; background: {rgba(pal.good, 26)}; }}
            QDialog#loginDialog QLineEdit {{ padding: 0 14px; border-radius: {field_r}px; }}
            QDialog#loginDialog QLineEdit:hover {{ border-color: {rgba(pal.line, 60)}; }}
            QDialog#loginDialog QLineEdit:focus {{ border: 1px solid {pal.lens}; padding: 0 14px; }}
            QDialog#loginDialog QPushButton[primary="true"] {{ border-radius: {field_r}px; }}
            QPushButton#loginShow {{ padding: 0; border-radius: {field_r}px; font-size: 9pt; }}
            QPushButton#loginShow:checked {{ background: {rgba(pal.ink, 20)}; border-color: {pal.lens}; }}
            QFrame#loginDivider {{ background: {rgba(pal.line, 22)}; border: none; }}
            QLabel#loginPrivacy {{ color: {pal.muted}; font-size: 8.5pt; }}
            QPushButton#loginLink {{ background: transparent; border: none; color: {pal.text_dim}; padding: 4px 0; font-size: 9.5pt; }}
            QPushButton#loginLink:hover {{ color: {pal.text}; }}
            QPushButton#loginLink:focus {{ color: {pal.text}; text-decoration: underline; }}
            """
        )

    def _apply_mode(self) -> None:
        reset = self._reset_mode
        self.title.setText("Reset password" if reset else "Sign in")
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
            self.message.setMinimumHeight(self.message.heightForWidth(self.width() - self.ASIDE_WIDTH - 2 * self.PAD))
        else:
            self.message.setMinimumHeight(0)
        self._fit_height()

    def _fit_height(self) -> None:
        """Size the window from the layout's real height-for-width. ``adjustSize`` under-counts
        wrapped labels, which made Qt squeeze the spacing when an error message appeared."""
        layout = self.layout()
        layout.activate()
        needed = max(self.MIN_HEIGHT, layout.totalHeightForWidth(self.width()))
        self.setMinimumHeight(needed)
        self.resize(self.width(), needed)

    def _set_busy(self, busy: bool) -> None:
        for widget in (self.email, self.password, self.show_password, self.toggle_reset, self.apply_link, self.privacy_link):
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
        self._fit_height()

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
