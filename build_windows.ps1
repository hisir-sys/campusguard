$ErrorActionPreference = "Stop"

Write-Host "=== CampusGuard Windows EXE build ==="

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "CampusGuard .venv was not found. Create it first."
}

$python = (Resolve-Path ".venv\Scripts\python.exe").Path

& $python -m pip install --upgrade pyinstaller pillow
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path "models\yolo11n.pt") -or -not (Test-Path "models\yolo11n-pose.pt")) {
    & $python -c "from ultralytics import YOLO; YOLO('yolo11n.pt'); YOLO('yolo11n-pose.pt')"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Copy-Item yolo11n.pt models/yolo11n.pt -Force
    Copy-Item yolo11n-pose.pt models/yolo11n-pose.pt -Force
}

& $python scripts/generate_app_icon.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python -m PyInstaller --noconfirm --clean --onedir --windowed --name CampusGuard --icon "assets\campusguard.ico" --collect-all PySide6 --collect-all cv2 --collect-all torch --collect-all torchvision --collect-all ultralytics --collect-all pytorchvideo --collect-all keyring --add-data "models;models" --add-data "assets;assets" main.py

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "App folder built: dist\CampusGuard\CampusGuard.exe"

$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (Test-Path $iscc) {
    & $iscc "installer\CampusGuard.iss"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "Installer built: dist\CampusGuard-Setup.exe"
} else {
    Write-Host "Inno Setup 6 not found - install it from jrsoftware.org to build the installer."
}
