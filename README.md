# CampusGuard Desktop App

Native Windows desktop version of CampusGuard.

## Run

PowerShell:
```powershell
cd F:\main\cAMPUSgAURD\CampusGuard_Desktop_App
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

If activation is blocked:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

## Camera
In the Cameras screen, enter `0` for webcam 0 or a local video path.

## Existing AI model
Copy your working CampusGuard YOLO model to:
`models/best.pt`

The app automatically tries to load it. Without weights, the app uses a lightweight OpenCV activity fallback so the application and camera pipeline still work.

Large model/video files are intentionally not bundled; copy your existing CampusGuard assets into the indicated folders.
