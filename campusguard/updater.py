from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen

from campusguard.build_info import BUILD_VERSION, GITHUB_REPOSITORY, RELEASE_TAG

_API_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/tags/{RELEASE_TAG}"
_USER_AGENT = "CampusGuard-Updater/1.0"


def _request(url: str, timeout: float = 4.0):
    return urlopen(
        Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": _USER_AGENT}),
        timeout=timeout,
    )


def _version_number(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def check_for_update() -> dict | None:
    if BUILD_VERSION == "dev" or not getattr(sys, "frozen", False):
        return None
    try:
        with _request(_API_URL) as response:
            release = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    remote_version = str(release.get("body", "")).strip()
    if not remote_version:
        remote_version = str(release.get("tag_name", "")).removeprefix("v")

    if _version_number(remote_version) <= _version_number(BUILD_VERSION):
        return None

    for asset in release.get("assets", []):
        if asset.get("name") == "CampusGuard.exe" and asset.get("browser_download_url"):
            return {"version": remote_version, "url": asset["browser_download_url"]}
    return None


def _download(url: str) -> Path | None:
    try:
        folder = Path(tempfile.gettempdir()) / "CampusGuardUpdate"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "CampusGuard.exe.new"
        with _request(url, timeout=60) as response, target.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        if target.stat().st_size < 1_000_000:
            target.unlink(missing_ok=True)
            return None
        return target
    except Exception:
        return None


def _apply_update(new_file: str, current_file: str, parent_pid: int) -> int:
    new_path = Path(new_file)
    current_path = Path(current_file)

    for _ in range(120):
        try:
            os.kill(parent_pid, 0)
        except OSError:
            break
        time.sleep(0.25)

    if not new_path.is_file():
        return 1

    backup = current_path.with_suffix(".old.exe")
    try:
        if current_path.is_file():
            shutil.copy2(current_path, backup)
        os.replace(new_path, current_path)
        backup.unlink(missing_ok=True)
    except Exception:
        try:
            if backup.is_file():
                os.replace(backup, current_path)
        except Exception:
            pass
        return 1

    subprocess.Popen([str(current_path)], close_fds=True)
    return 0


def maybe_update() -> bool:
    latest = check_for_update()
    if not latest:
        return False

    downloaded = _download(latest["url"])
    if not downloaded:
        return False

    current = Path(sys.executable).resolve()
    subprocess.Popen(
        [str(current), "--apply-update", str(downloaded), str(current), str(os.getpid())],
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return True


def handle_update_arguments(argv: list[str]) -> int | None:
    if len(argv) != 5 or argv[1] != "--apply-update":
        return None
    return _apply_update(argv[2], argv[3], int(argv[4]))
