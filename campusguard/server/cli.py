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
SERVER_FLAGS = {"--server", "--server-login", "--show-token", "--install-task", "--remove-task"}


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
    print(f"Signed in as {session.email}. You can now start the server with --server.")
    return 0


def show_token() -> int:
    from campusguard.server.config import load_config
    from campusguard.storage import application_data_dir

    config = load_config(application_data_dir())
    print(f"Address: {config.host}:{config.port}")
    print(f"Access token: {config.token}")
    return 0


def install_task() -> int:
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
    if sys.platform != "win32":
        return 1
    return int(subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]).returncode)


def handle(argv: list[str]) -> int | None:
    """Return an exit code if argv is a server command, else None (normal GUI start)."""
    flags = SERVER_FLAGS.intersection(argv)
    if not flags:
        return None
    attach_parent_console()
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
