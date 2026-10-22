"""Command-line entry points for server mode (used by main.py)."""
from __future__ import annotations

import getpass
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

TASK_NAME = "CampusGuard Server"
SERVER_FLAGS = {"--server", "--server-login", "--show-token", "--install-task", "--remove-task", "--configure-server", "--server-status"}


def attach_parent_console() -> None:
    """The Windows build is a GUI program; borrow the launching console for output/prompts."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        if ctypes.windll.kernel32.AttachConsole(-1):  # type: ignore[attr-defined]
            sys.stdout = open("CONOUT$", "w", buffering=1, encoding="utf-8")
            sys.stderr = sys.stdout
            sys.stdin = open("CONIN$", "r", encoding="utf-8")
    except Exception:
        pass


def _prepare_qt(gui: bool):
    """Set the same Qt app-data identity before reading server configuration."""
    if gui:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv[:1])
    else:
        from PySide6.QtCore import QCoreApplication
        app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    app.setOrganizationName("CampusGuard")
    app.setApplicationName("CampusGuard")
    return app


def _ensure_console() -> None:
    """Open a visible console for commands that require terminal input/output."""
    if sys.platform != "win32" or (sys.stdin is not None and sys.stdout is not None):
        return
    try:
        import ctypes
        if ctypes.windll.kernel32.AllocConsole():  # type: ignore[attr-defined]
            sys.stdout = open("CONOUT$", "w", buffering=1, encoding="utf-8")
            sys.stderr = sys.stdout
            sys.stdin = open("CONIN$", "r", encoding="utf-8")
    except Exception:
        pass


def _server_login_gui() -> int:
    from PySide6.QtCore import QObject, QThread, Signal, Slot
    from PySide6.QtWidgets import QDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout
    from campusguard import auth

    _prepare_qt(True)

    class LoginDialog(QDialog):
        worker_running = False

        def closeEvent(self, event):
            if self.worker_running:
                event.ignore()
            else:
                event.accept()

    dialog = LoginDialog()
    dialog.setWindowTitle("CampusGuard server sign-in")
    dialog.setMinimumWidth(420)
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel("Sign in with the CampusGuard website account approved for this school."))
    form = QFormLayout()
    email_input = QLineEdit()
    email_input.setPlaceholderText("name@school.org")
    password_input = QLineEdit()
    password_input.setEchoMode(QLineEdit.EchoMode.Password)
    form.addRow("Email", email_input)
    form.addRow("Password", password_input)
    layout.addLayout(form)
    status = QLabel("")
    status.setWordWrap(True)
    layout.addWidget(status)
    submit = QPushButton("Sign in")
    layout.addWidget(submit)
    holder = {"worker": None, "success": False}

    class LoginWorker(QThread):
        succeeded = Signal(object)
        failed = Signal(str)

        def __init__(self, email: str, password: str):
            super().__init__(dialog)
            self.email, self.password = email, password

        def run(self):
            try:
                self.succeeded.emit(auth.login(self.email, self.password))
            except Exception as error:
                self.failed.emit(str(error))

    class LoginResultBridge(QObject):
        @Slot(object)
        def on_success(self, session):
            try:
                auth.save_session(session)
                saved = auth.load_saved()
                if not saved or saved.get("refresh_token") != session.refresh_token:
                    raise RuntimeError("Credential storage did not confirm the saved sign-in.")
            except Exception:
                status.setText(
                    "Sign-in succeeded, but Windows Credential Manager did not save the session. "
                    "Check that credential storage is available, then try again."
                )
                submit.setEnabled(True)
                dialog.worker_running = False
                return
            holder["success"] = True
            password_input.clear()
            status.setText(f"Signed in as {session.email}.")
            dialog.worker_running = False
            dialog.accept()

        @Slot(str)
        def on_failure(self, message: str):
            password_input.clear()
            status.setText(f"Sign-in failed: {message}")
            submit.setEnabled(True)
            dialog.worker_running = False

    bridge = LoginResultBridge(dialog)

    def begin_login():
        email, password = email_input.text().strip(), password_input.text()
        if not email or not password:
            status.setText("Enter both your email and password.")
            return
        submit.setEnabled(False)
        status.setText("Signing in securely…")
        dialog.worker_running = True
        worker = LoginWorker(email, password)
        holder["worker"] = worker
        worker.succeeded.connect(bridge.on_success)
        worker.failed.connect(bridge.on_failure)
        worker.finished.connect(worker.deleteLater)
        worker.start()
        password_input.clear()

    submit.clicked.connect(begin_login)
    email_input.returnPressed.connect(begin_login)
    password_input.returnPressed.connect(begin_login)
    dialog.exec()
    worker = holder["worker"]
    if worker is not None and worker.isRunning():
        worker.wait(10000)
    return 0 if holder["success"] else 1


def _show_token_gui() -> int:
    from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout
    from campusguard.server.config import load_config
    from campusguard.storage import application_data_dir

    app = _prepare_qt(True)
    try:
        config = load_config(application_data_dir())
    except Exception as error:
        QMessageBox.critical(None, "CampusGuard token unavailable", str(error))
        return 1
    dialog = QDialog()
    dialog.setWindowTitle("CampusGuard server access token")
    dialog.setMinimumWidth(560)
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel(
        "Keep this token private. Anyone who has it may access the server API. "
        "The token is stored in Windows Credential Manager and is not written to logs."
    ))
    address = "All network interfaces" if config.host == "0.0.0.0" else config.host
    layout.addWidget(QLabel(f"Server listening address: {address}:{config.port}"))
    if config.host == "0.0.0.0":
        layout.addWidget(QLabel("Connect from another PC using this server's LAN IP address, not 0.0.0.0."))
    token_input = QLineEdit(config.token)
    token_input.setEchoMode(QLineEdit.EchoMode.Password)
    token_input.setReadOnly(True)
    layout.addWidget(token_input)
    reveal = QCheckBox("Reveal token on screen")
    reveal.toggled.connect(lambda checked: token_input.setEchoMode(
        QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
    ))
    layout.addWidget(reveal)
    buttons = QHBoxLayout()
    copy_button = QPushButton("Copy token")
    close_button = QPushButton("Close")
    buttons.addWidget(copy_button)
    buttons.addStretch(1)
    buttons.addWidget(close_button)
    layout.addLayout(buttons)
    copy_button.clicked.connect(lambda: (app.clipboard().setText(config.token), copy_button.setText("Copied")))
    close_button.clicked.connect(dialog.accept)
    dialog.exec()
    return 0


def configure_server(argv: list[str]) -> int:
    """Apply non-secret installer settings without starting AI or the HTTP server."""
    try:
        _prepare_qt(False)
        from campusguard.server.config import load_config, save_config
        from campusguard.storage import application_data_dir
        import math

        data_dir = application_data_dir()
        config = load_config(data_dir)
        host = _option(argv, "--host")
        if host is not None:
            if host not in {"127.0.0.1", "0.0.0.0"}:
                raise ValueError("Host must be 127.0.0.1 or 0.0.0.0.")
            config.host = host
        port = _option(argv, "--port")
        if port is not None:
            parsed_port = int(port)
            if not 1 <= parsed_port <= 65535:
                raise ValueError("Port must be between 1 and 65535.")
            config.port = parsed_port
        footage = _option(argv, "--footage-dir")
        if footage:
            footage_path = Path(footage).expanduser().resolve()
            footage_path.mkdir(parents=True, exist_ok=True)
            config.footage_dir = str(footage_path)
        limit = _option(argv, "--max-footage-gb")
        if limit is not None:
            parsed_limit = float(limit)
            if not math.isfinite(parsed_limit) or not 1.0 <= parsed_limit <= 100000.0:
                raise ValueError("Footage size limit must be between 1 and 100000 GB.")
            config.max_footage_gb = parsed_limit
        save_config(data_dir, config)
        return 0
    except Exception as error:
        if sys.stdout is not None:
            print(f"Could not save server settings: {error}")
        return 1


def server_status() -> int:
    from PySide6.QtWidgets import QApplication, QMessageBox
    from campusguard.server.config import load_config
    from campusguard.storage import application_data_dir

    app = _prepare_qt(True)
    try:
        config = load_config(application_data_dir())
    except Exception as error:
        QMessageBox.critical(None, "CampusGuard server status", str(error))
        return 1
    from campusguard.server.status_window import ServerStatusWindow
    window = ServerStatusWindow(config, config.token)
    window.show()
    return app.exec()


def build_task_xml(command: str, arguments: str, user: str) -> str:
    """Windows Task Scheduler definition: start at boot, restart if it stops."""
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>CampusGuard analysis server</Description></RegistrationInfo>
  <Triggers>
    <BootTrigger><Delay>PT30S</Delay></BootTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{escape(user)}</UserId>
      <LogonType>Password</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(command)}</Command>
      <Arguments>{escape(arguments)}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def _option(argv: list[str], name: str) -> str | None:
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    return None


def server_login() -> int:
    from campusguard import auth

    if sys.stdin is None or sys.stdout is None:
        return _server_login_gui()
    print("CampusGuard server sign-in (use the account approved on the website).")
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")
    try:
        session = auth.login(email, password)
    except auth.AuthError as error:
        print(f"Sign-in failed: {error}")
        return 1
    except auth.NetworkError as error:
        print(f"Could not reach the sign-in service: {error}")
        return 1
    auth.save_session(session)
    saved = auth.load_saved()
    if not saved or saved.get("refresh_token") != session.refresh_token:
        print("Sign-in succeeded, but Windows Credential Manager did not save the session.")
        print("Check that credential storage is available, then try again.")
        return 1
    print(f"Signed in as {session.email}. You can now start the server with --server.")
    return 0


def show_token() -> int:
    from campusguard.server.config import load_config
    from campusguard.storage import application_data_dir

    if sys.stdout is None or sys.stdin is None:
        return _show_token_gui()
    try:
        _prepare_qt(False)
        config = load_config(application_data_dir())
    except Exception as error:
        print(f"Could not load the server token securely: {error}")
        return 1
    print(f"Listening address: {config.host}:{config.port}")
    print(f"Access token (keep private): {config.token}")
    return 0


def install_task() -> int:
    _ensure_console()
    if sys.platform != "win32":
        print("Automatic start is only available on Windows.")
        return 1
    user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".strip("\\")
    if getattr(sys, "frozen", False):
        command, arguments = sys.executable, "--server"
    else:
        command, arguments = sys.executable, f'"{Path(sys.argv[0]).resolve()}" --server'
    xml = build_task_xml(command, arguments, user)
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as handle:
        handle.write(xml)
        path = handle.name
    try:
        print(f"Creating the scheduled task as {user}. Windows will ask for this account's password.")
        result = subprocess.run(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", path, "/RU", user, "/RP", "*", "/F"])
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if result.returncode == 0:
        print(f'Done. The server now starts at boot. Start it now with: schtasks /Run /TN "{TASK_NAME}"')
    return int(result.returncode)


def remove_task() -> int:
    _ensure_console()
    if sys.platform != "win32":
        return 1
    return int(subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]).returncode)


def handle(argv: list[str]) -> int | None:
    """Return an exit code if argv is a server command, else None (normal GUI start)."""
    flags = SERVER_FLAGS.intersection(argv)
    if not flags:
        return None
    attach_parent_console()
    if "--configure-server" in flags:
        return configure_server(argv)
    if "--server-status" in flags:
        return server_status()
    if "--server-login" in flags:
        return server_login()
    if "--show-token" in flags:
        return show_token()
    if "--install-task" in flags:
        return install_task()
    if "--remove-task" in flags:
        return remove_task()
    port = _option(argv, "--port")
    from campusguard.server.host import run_server

    return run_server(_option(argv, "--host"), int(port) if port and port.isdigit() else None)
