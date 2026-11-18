# Test CampusGuard with 50 fake cameras on one PC

Goal: find out how many cameras a school's ordinary PC can handle, before you promise anything.

**What this tests:** reading many RTSP streams, the clip buffer, the motion gate and the AI on that PC.
**What it does not test:** real cameras' network problems. Run the fake feeds on a *second* computer if you
can (use `--base rtsp://<that-pc-ip>:8554` and allow port 8554 in its firewall); on the same PC the fake
feeds use some CPU themselves, so the result is slightly pessimistic.

## 1. Install (once, on the test PC)
1. **Python 3.11+** from python.org (tick "Add python.exe to PATH"). Check: `python --version`.
2. **FFmpeg**: `winget install Gyan.FFmpeg`, then open a NEW terminal. Check: `ffmpeg -version`.
3. **MediaMTX** (a small RTSP server): download the Windows amd64 zip from the bluenviron/mediamtx GitHub
   "Releases" page, extract it, keep `mediamtx.exe`.
4. Copy `scripts/fake_cameras.py` and `scripts/monitor_usage.py` from the CampusGuard repo to a folder, e.g. `C:\loadtest`.
5. `pip install psutil` (only for the usage logger).

## 2. Make two test clips
Use video you are allowed to use (a staged scuffle by volunteers, or a licensed clip), plus a calm corridor clip.

    python fake_cameras.py encode calm.mp4  --output calm_sub.mp4
    python fake_cameras.py encode fight.mp4 --output fight_sub.mp4

Defaults: 640x360 at 15 fps, no audio, like a camera sub-stream. Use `--size 960x540` to test better-looking clips.

## 3. Start the fake camera system
1. Double-click `mediamtx.exe`. Windows asks about the firewall: allow **private** networks. Leave it open.
2. In a second terminal, start 50 feeds from the **calm** clip first:

       python fake_cameras.py serve --count 50 --video calm_sub.mp4

   It prints "50 feeds live". If it says feeds stopped, MediaMTX is not running.
3. Check one: VLC -> Media -> Open Network Stream -> `rtsp://127.0.0.1:8554/cam_1`.

## 4. Prepare CampusGuard so the test is safe
- **Turn phone alerts off**: clear the alert numbers and set WhatsApp mode to off (Settings), otherwise 50 fake
  fights send real messages. Use a laptop that is not the school's live system.
- Close other heavy programs, plug the laptop into power, set the power mode to "Best performance".

## 5. Add the cameras in steps (10, then 25, then 50)

    python fake_cameras.py csv --count 10 --output cams10.csv
    python fake_cameras.py csv --count 25 --output cams25.csv
    python fake_cameras.py csv --count 50 --output cams50.csv

In CampusGuard: **Cameras -> Import CSV -> cams10.csv -> Import**. Wait until the cameras show as connected, then
measure (step 6). Then import `cams25.csv` (cameras already added are skipped, only the new ones are added), measure
again, then `cams50.csv`.

## 6. Measure at each step (5 minutes each)
In another terminal:

    python monitor_usage.py --seconds 300 --output usage_25_calm.csv

Also watch Task Manager (Ctrl+Shift+Esc) -> Performance. Note: CampusGuard decodes video on the **CPU**, so the
integrated-GPU graph may stay near zero. That is normal; the CPU and RAM numbers are what matter.

Fill in a table like this:

| Cameras | Clip | Peak PC CPU % | Average PC CPU % | PC RAM % | All connected? | UI smooth? |
|---|---|---|---|---|---|---|
| 10 | calm | | | | | |
| 25 | calm | | | | | |
| 50 | calm | | | | | |
| 50 | fight (worst case) | | | | | |

## 7. The worst case: every camera busy
Stop the feeds (Ctrl+C in the serve terminal) and restart with the fight clip:

    python fake_cameras.py serve --count 50 --video fight_sub.mp4

All 50 cameras now see movement at once, so the motion gate stays open on all of them. That is like break time at
school, and it is the number that decides whether the PC is enough. Run `monitor_usage.py` again. You will get
many incidents; delete the test cameras afterwards.

## 8. How to read the result (suggested limits, adjust after your first real pilot)
- **Pass:** average PC CPU under about 70%, peaks under about 90%, RAM under about 75%, every camera stays
  connected, the app stays usable, and alerts for the fight clips arrive within a few seconds.
- **Marginal:** CPU sits at 90-100% or cameras keep reconnecting. Use fewer cameras on that PC, or a smaller
  sub-stream (640x360, 10 fps).
- **Fail:** the PC freezes or the app cannot keep up. That PC is too small for this many cameras: use fewer cameras,
  or bring a dedicated PC (with an entry-level NVIDIA GPU if the AI is the bottleneck).

The largest camera count that passes the **fight (worst case)** row is the number to put in the contract for that PC.

## 9. Clean up
Ctrl+C the feeds, close MediaMTX, delete the test cameras in CampusGuard, and keep `usage_*.csv` as your evidence.

## Troubleshooting
| Problem | Fix |
|---|---|
| `ffmpeg` not recognised | Open a new terminal after installing; check PATH |
| Feeds stop straight away | MediaMTX is not running, or port 8554 is blocked by the firewall |
| CampusGuard cameras stay "connecting" | Use `rtsp://127.0.0.1:8554/cam_N` (not a different port); check VLC opens the same URL |
| Video stutters in VLC with 50 feeds | The PC is already overloaded; run the feeds on a second computer |
| Few cameras connect, others fail | Start feeds with a larger `--stagger 0.3` |
