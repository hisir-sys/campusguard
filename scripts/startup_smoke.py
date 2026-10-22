"""Import every CampusGuard module and check that main.py can start headlessly."""
from __future__ import annotations

import importlib
import os
import pkgutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def import_all_modules() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import campusguard

    names = sorted(
        item.name for item in pkgutil.walk_packages(
            campusguard.__path__, prefix=f"{campusguard.__name__}."
        )
    )
    names.append("main")
    for name in names:
        importlib.import_module(name)
        print(f"IMPORT OK: {name}")
    print(f"IMPORT SUMMARY: {len(names)} modules imported")


def smoke_start_main() -> None:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "main.py")],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        code = process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        print("STARTUP OK: main.py remained running for 10 seconds with no server/camera configured")
        return
    if code != 0:
        raise RuntimeError(f"main.py exited during startup with code {code}")
    raise RuntimeError("main.py exited before the startup smoke-test window elapsed")


if __name__ == "__main__":
    import_all_modules()
    smoke_start_main()
