"""Self-update for the installed Windows build.

The release workflow publishes ``CampusGuard-Setup.exe`` (an Inno Setup
installer) plus ``checksum.txt`` to the rolling ``latest`` GitHub release.
The app checks in the background after sign-in, downloads the installer,
verifies its SHA-256, and — only if the user agrees — runs it silently. The
installer closes CampusGuard, replaces the files and relaunches it.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

from campusguard.build_info import BUILD_VERSION, GITHUB_REPOSITORY, RELEASE_TAG

INSTALLER_ASSET = "CampusGuard-Setup.exe"
CHECKSUM_ASSET = "checksum.txt"
_API_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/tags/{RELEASE_TAG}"
_USER_AGENT = "CampusGuard-Updater/2.0"
_MIN_INSTALLER_BYTES = 1_000_000


def _request(url: str, timeout: float = 10.0):
    return urlopen(
        Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": _USER_AGENT}),
        timeout=timeout,
    )


def _version_number(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def select_update(release: dict, current_version: str) -> dict | None:
    """Pure helper: pick the installer/checksum assets if the release is newer."""
    remote_version = str(release.get("body", "")).strip()
    if not remote_version:
        remote_version = str(release.get("tag_name", "")).removeprefix("v")
    if _version_number(remote_version) <= _version_number(current_version):
        return None
    installer_url = None
    checksum_url = None
    for asset in release.get("assets", []):
        if asset.get("name") == INSTALLER_ASSET:
            installer_url = asset.get("browser_download_url")
        elif asset.get("name") == CHECKSUM_ASSET:
            checksum_url = asset.get("browser_download_url")
    if not installer_url or not checksum_url:
        return None
    return {"version": remote_version, "url": installer_url, "checksum_url": checksum_url}


def check_for_update() -> dict | None:
    if BUILD_VERSION == "dev" or not getattr(sys, "frozen", False):
        return None
    try:
        with _request(_API_URL) as response:
            release = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    return select_update(release, BUILD_VERSION)


def download_installer(url: str, checksum_url: str) -> Path | None:
    """Download and verify the installer. Returns its path, or None on any failure."""
    try:
        with _request(checksum_url) as response:
            checksum_text = response.read().decode("utf-8").strip()
        expected = checksum_text.split()[0].lower()
        if len(expected) != 64:
            return None
        folder = Path(tempfile.gettempdir()) / "CampusGuardUpdate"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / INSTALLER_ASSET
        with _request(url, timeout=120) as response, target.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        if target.stat().st_size < _MIN_INSTALLER_BYTES:
            target.unlink(missing_ok=True)
            return None
        digest = hashlib.sha256()
        with target.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest().lower() != expected:
            target.unlink(missing_ok=True)
            return None
        return target
    except Exception:
        return None


def launch_installer(installer: Path) -> bool:
    """Start the silent installer. The caller must quit the app right afterwards."""
    try:
        subprocess.Popen(
            [str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
            close_fds=True,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        return True
    except Exception:
        return False


def prepare_update() -> tuple[dict, Path] | None:
    """Check for a newer release and download + verify its installer (blocking)."""
    latest = check_for_update()
    if not latest:
        return None
    installer = download_installer(latest["url"], latest["checksum_url"])
    if not installer:
        return None
    return latest, installer
