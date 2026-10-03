@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python Launcher not found. Install 64-bit Python 3.14 and enable the launcher.
    pause
    exit /b 1
)

py -3.14 -m venv .venv
if errorlevel 1 (
    echo Could not create the Python 3.14 virtual environment.
    echo If Python 3.14 is not installed, download it from python.org and enable the Python Launcher during setup.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo Could not upgrade pip.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed. See the output above.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo CampusGuard exited with an error.
    pause
    exit /b 1
)
