"""Start CampusGuard when the user signs in to Windows (per-user Run key, no admin rights needed)."""
from __future__ import annotations

import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "CampusGuard"


def supported() -> bool:
    return sys.platform == "win32"


def command() -> str:
    """The command Windows should run at sign-in."""
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable)}"'
    main = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{Path(sys.executable)}" "{main}"'


def is_enabled() -> bool:
    if not supported():
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _kind = winreg.QueryValueEx(key, VALUE_NAME)
        return bool(value)
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    """Turn it on or off. Returns True when the change was made."""
    if not supported():
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
