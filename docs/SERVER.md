# School server guide

Running CampusGuard headless on one PC for a whole school: installer, API, engine profiles and phone alerts. See also [SCHOOL_DEPLOYMENT.md](SCHOOL_DEPLOYMENT.md) and [LOAD_TEST_GUIDE.md](LOAD_TEST_GUIDE.md).

## School server installer (Phase 4)

The school-server installer is separate from the everyday desktop installer. Download the **CampusGuard-Server-Installer** artifact from a successful Phase 3–4 validation run, or use the compiled CampusGuard-Server-Setup.exe provided by your CampusGuard administrator. The server installer is built for Windows 10/11 x64 and does not install Python separately. The package contains the application runtime, but intentionally excludes model checkpoints; schools must supply model files they are licensed to use.

### Install on the school server PC

1. Run the server installer. It installs into the current Windows user's local Programs folder and creates the CampusGuard app-data folders.
2. Choose a dedicated footage folder with enough free space. Set the maximum footage size (default 200 GB); when the cap is exceeded, the oldest clips are removed first. Incident records are retained for 365 days by default and clips for 30 days.
3. Leave **Allow connections from other PCs** unchecked for local-only use. If office PCs must connect, enable it only on a trusted school LAN or VPN. The installer then configures the server to listen on 0.0.0.0 and requests a Windows Firewall rule for the selected TCP port. If the firewall elevation is cancelled or fails, it switches back to local-only mode. Do not expose the API directly to the public internet. Plain HTTP does not encrypt the token; use HTTPS or a VPN when traffic crosses an untrusted network.
4. Sign in using the approved CampusGuard website account. The account and approval are rechecked every six hours. Run the **CampusGuard Server Sign In** shortcut later if the sign-in must be renewed.
5. If selected, the installer registers a Windows Task Scheduler job for the same Windows user. Windows asks for that user's password so the task can start at boot while the user is signed out. Confirm the task is registered before relying on unattended operation.
6. If the installer starts the server, the access-token window shows the token masked. Reveal it only when needed and share it only with trusted CampusGuard client PCs. The token is stored in Windows Credential Manager, not in server.json or the logs. You can open **CampusGuard Server Status** later to check reachability, camera health counts, and the most recent logged warning/error.

### Add licensed model files

Copy the model checkpoints you are licensed to use into:

    %APPDATA%\CampusGuard\CampusGuard\models\

Use the filenames expected by the current model configuration, normally yolo11n.pt (person detector), yolo11n-pose.pt (pose estimator), and the Spontim 1.0 fight classifier model_16_m3_0.8888.pth. The server resolves relative models paths from this folder when a checkpoint is not bundled beside the application. Restart the server after adding or replacing weights. Missing weights are reported as model errors; CampusGuard must not pretend that a missing model is detecting fights.

### Connect a desktop client from another PC

1. On the server PC, open **CampusGuard Server Status** and confirm it reports the server is reachable.
2. Find the server PC's private LAN IP address in Windows Settings or with ipconfig. Do not use 0.0.0.0 as the address clients connect to.
3. On the client PC, install and open CampusGuard, sign in with an approved account, then open **Settings → Connection mode** and choose **Server**.
4. Enter http://SERVER-LAN-IP:8765 only on a trusted LAN, or the configured https:// address when TLS is set up. Paste the token from the server's token window and choose **Test connection**. The token is saved in Windows Credential Manager on the client PC.
5. Open the server viewer to manage cameras, review incidents/alerts, and play saved clips. If the server is unavailable, the viewer shows a reconnecting state; it does not switch to fake detections.

### Server commands and recovery

From the Start Menu shortcuts, you can sign in, show the token, open status, start the server, install the boot task, or remove it. The corresponding executable flags are --server-login, --show-token, --server-status, --server, --install-task, and --remove-task. Logs are in %APPDATA%\CampusGuard\CampusGuard\logs\server.log. The uninstall asks whether to delete server data; choose **No** to keep the database and footage. Choosing **Yes** deletes the app-data folder and the selected footage folder and cannot be undone.

**Real-world checks still required before school deployment:** test the boot task under the actual school Windows account, verify any firewall prompt with IT, confirm the server PC's IP/port from a second PC, and measure throughput with the school's real RTSP/NVR streams. The CI installer build does not prove camera-scale performance or the Windows boot-task credentials.

## Analysis engine profiles (Lite / Standard / Server)

The app picks a profile automatically from the machine and the number of running cameras:

| Profile | Chosen when | Behaviour |
|---|---|---|
| Lite | no GPU and ≤4 CPU cores or <8 GB RAM | motion gate, light analysis |
| Standard | normal PC, or a GPU PC with ≤16 cameras | motion gate |
| Server | NVIDIA GPU and more than 16 cameras | motion gate, analysis at ≤960 px wide, GPU-batched person detection, capped evidence pre-buffer, preview ≤10 fps |

**Smart analysis (all profiles):** every camera runs a tiny motion check; the detector, pose and fight models only run while the scene is moving (plus a 5–6 s hangover, and whenever an event or recording is in progress). Unclear cases count as motion, so the gate can only add analysis, never skip it. When a camera cannot keep up, its analysis stride rises (2 → up to 4) and returns to 2 when load drops.

Override (optional): set `CAMPUSGUARD_PROFILE=lite|standard|server` and/or `CAMPUSGUARD_SMART_ANALYSIS=0`, or put `{"profile": "server", "smart_analysis": true}` in `engine.json` inside the CampusGuard app-data folder.

For many cameras, enter each camera's low-resolution *sub-stream* RTSP address (typically 640×360) instead of the main stream, and use the CUDA build of PyTorch on the server.

## Server mode (headless, for a school server)

One program, two ways to run it. The desktop app is unchanged. Server mode runs every camera with no window, records incidents and clips, and serves a token-protected API for viewers.

```
CampusGuard.exe --server-login      # sign in as the Windows user that will run the server
CampusGuard.exe --server            # run in this console (Ctrl+C stops it)
CampusGuard.exe --install-task      # start automatically at boot, restart on failure (asks for the Windows password)
CampusGuard.exe --show-token        # opens a masked token window in the windowed app; prints only from a console
CampusGuard.exe --server-status     # open the local server status window
CampusGuard.exe --remove-task
```

Non-secret settings live in `server.json` in the CampusGuard app-data folder. The API token is stored in Windows Credential Manager, not in JSON, SQLite or logs. Existing installations migrate their legacy JSON token into the vault on the next server start:

| key | default | meaning |
|---|---|---|
| `host` | `127.0.0.1` | set `0.0.0.0` to accept connections from other PCs on the school network (then also allow the port in Windows Firewall) |
| `port` | `8765` | API port |
| `retention_days_footage` / `retention_days_incidents` | 30 / 365 | older clips / incidents are deleted hourly |
| `max_footage_gb` | 200 | oldest clips are deleted first when the footage folder grows past this |
| `footage_dir` | app-data `footage` folder | optional custom folder for saved incident clips |
| `recheck_hours` | 6 | how often the website account approval is re-verified |
| `tls_cert_file`, `tls_key_file` | empty | serve HTTPS; use this (or a VPN) if the API crosses anything other than a trusted LAN |

API (`Authorization: Bearer <token>`, base path `/api/v1`, plus an open `GET /health`):
`GET /status`, `GET|POST /cameras`, `POST /cameras/import` (CSV body: `name,type,address,username,password,ai_enabled`), `DELETE /cameras/{id}`, `POST /cameras/{id}/ai`, `POST /cameras/{id}/reconnect`, `GET /incidents?after_id=&limit=`, `GET /alerts`, `POST /incidents/{INC-id}/status`, `GET /incidents/{INC-id}/clip` (MP4, supports Range). Logs: `logs/server.log` in the app-data folder.

Cameras are opened a few at a time at start-up, reconnect automatically with back-off, and `/cameras` shows per-camera health (`ok`, `stalled` if no frames for 15 s, `offline`, `connecting`).

## Phone alerts, groups, reports and safety (launch features)

- **Phone alerts** (Settings, Phone alerts): add one or many numbers. Each alert carries the camera (place), time, confidence percentage and, where the channel allows, the video clip.
  - *Free WhatsApp*: opens WhatsApp with the message ready; you tap Send. No video can be attached this way.
  - *Automatic WhatsApp*: WhatsApp Business Cloud API (needs a Meta business account; conversations may be charged). Sends text and video. Token is stored in the OS credential vault.
  - *ntfy push*: free push notifications; keep clip attachment off on the public server.
  - Backup numbers are alerted if nobody acknowledges within the chosen minutes.
- **Alert confirmation**: choose 2 to 6 consecutive detections before an incident is raised.
- **Camera groups** and a "needs attention" filter on the Cameras page.
- **Trend report** (HTML) from Settings or Ctrl+K: incidents per day, hour and camera, false-alarm rate.
- **Supervisor PIN**: required before deleting footage or history. This is an approval step, not encryption; use BitLocker for disk encryption.
- **GPU decode** option and `scripts/export_models.py` (ONNX / TensorRT).
- **Update rollback**: the last installers are kept; Ctrl+K, "Roll back to previous version".
- Server API: `POST /api/v1/cameras/{id}/sensitivity`.

