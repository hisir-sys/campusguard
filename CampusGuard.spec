# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the CampusGuard Windows app (onedir).

Same packages as before, but trimmed: only the Qt modules the app imports are
bundled, build-only files (headers, import libraries, cmake) are dropped, and
the duplicate model checkpoint is shipped once (see campusguard/model_paths.py).
"""

import re

from PyInstaller.utils.hooks import collect_all

datas = [("models", "models"), ("assets", "assets")]
binaries = []
hiddenimports = []
for package in ("cv2", "torch", "torchvision", "ultralytics", "pytorchvideo", "keyring"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

# The app only uses QtCore, QtGui, QtWidgets and QtSvg. PySide6's own PyInstaller
# hooks bundle exactly the modules that are imported (plus their plugins), so we
# no longer use collect_all("PySide6"), which copied every Qt module.
excludes = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtWebView",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets", "PySide6.QtQuickControls2",
    "PySide6.QtQml", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtLocation", "PySide6.QtPositioning", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech",
    "PyQt5", "PyQt6", "tkinter", "IPython", "notebook", "pytest", "sphinx",
]

# Files that are only needed to compile against PyTorch/OpenCV, never to run them.
DROP_PATTERNS = [
    r"(^|/)torch/include/",
    r"(^|/)torch/share/cmake/",
    r"(^|/)torch/lib/cmake/",
    r"\.(lib|h|hpp|cuh|cmake|pdb)$",
    # Identical to models/fight_mc3_18.pth (same SHA-256); resolved by model_paths.py.
    r"(^|/)models/model_16_m3_0\.8888\.pth$",
]
_drop = [re.compile(pattern) for pattern in DROP_PATTERNS]


def keep(entry):
    destination = entry[0].replace("\\", "/")
    return not any(pattern.search(destination) for pattern in _drop)


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

before = len(a.datas) + len(a.binaries)
a.datas = [entry for entry in a.datas if keep(entry)]
a.binaries = [entry for entry in a.binaries if keep(entry)]
print(f"CampusGuard.spec: dropped {before - len(a.datas) - len(a.binaries)} build-only/duplicate files")

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CampusGuard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/campusguard.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="CampusGuard",
)
