$ErrorActionPreference = "Stop"

Write-Host "=== CampusGuard Windows EXE build ==="

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "CampusGuard .venv was not found. Create it first."
}

$python = (Resolve-Path ".venv\Scripts\python.exe").Path

& $python -m pip install --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path "models\yolo11n.pt") -or -not (Test-Path "models\yolo11n-pose.pt")) {
    & $python -c "from ultralytics import YOLO; YOLO('yolo11n.pt'); YOLO('yolo11n-pose.pt')"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Copy-Item yolo11n.pt models/yolo11n.pt -Force
    Copy-Item yolo11n-pose.pt models/yolo11n-pose.pt -Force
}

& $python -m PyInstaller --noconfirm --clean --onefile --windowed --name CampusGuard --collect-all PySide6 --collect-all cv2 --collect-all torch --collect-all torchvision --collect-all ultralytics --collect-all pytorchvideo --collect-all keyring --add-data "models;models" main.py

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Build complete: dist\CampusGuard.exe"
