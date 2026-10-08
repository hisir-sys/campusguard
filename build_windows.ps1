$ErrorActionPreference = "Stop"

Write-Host "=== CampusGuard Windows EXE build ==="

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "CampusGuard .venv was not found. Create it first."
}

$python = (Resolve-Path ".venv\Scripts\python.exe").Path

& $python -m pip install --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python -m PyInstaller --noconfirm --clean --onefile --windowed --name CampusGuard --collect-all PySide6 --collect-all cv2 --collect-all torch --collect-all torchvision --collect-all ultralytics --collect-all pytorchvideo --collect-all keyring --add-data "models;models" main.py

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Build complete: dist\CampusGuard.exe"
