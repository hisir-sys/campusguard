# CampusGuard Desktop — Update Notes

## Cameras no longer wait for the fight model (SlowFast and R(2+1)D)

- **Cause of "everything stays green" in the 10-camera fight test:** all cameras shared one model and queued for it, so each camera's thread could stall for seconds at every check, lose the frames it had collected and never finish a clip. The checks for the two newer models now run on one background worker; the camera keeps collecting frames while its clip is being checked, and each camera has at most one clip waiting.
- **New log file:** `detection_diagnostics.csv` in the app's data folder gets one line per camera every 15 seconds: frames arriving, frames analysed, how many frames the clip has, checks done, highest fight probability seen, seconds per check, and any error. If a fight is missed again, send this file.
- Checked end to end through the full pipeline on a fight clip: 9 checks, highest probability 0.99, "FIGHT DETECTED" raised.

## New models see fights on a busy PC; the tile says when checks are paused

- **Found in a 10-camera fight test:** with the newer models nothing was flagged. Not a hard-coded answer: scored through the app's own classifier on a fight clip, SlowFast flagged 22 of 29 checks and R(2+1)D 39 of 61, and calm footage flagged almost nothing. On a PC with all cores busy the app analyses only some frames of each camera, and the "clip stretched too far apart" guard (added for the false-alarm fix) then pauses every check.
- **Fix (SlowFast and R(2+1)D):** every camera frame, including the ones the analysis skips, now goes into the clip buffer on a steady 15 fps grid, so a busy PC still gives the model evenly spaced clips. A long stall (a check running) restarts the clip instead of gluing frames across the gap.
- The camera tile now shows **"PC TOO BUSY, CHECKS PAUSED"** whenever checks are being skipped, so a silent camera is no longer mistaken for a calm one.
- Spontim 1.0 is unchanged.

## Choose the detection model (Spontim 1.0, SlowFast, R(2+1)D)

- **Settings > Detection model** now lists three models you can swap between (the change restarts detection): Spontim 1.0 (default), **Spontim 2 (SlowFast)** and **Spontim 3 (R(2+1)D)**. The model files are included in the app (`models/spontim_slowfast.pth`, `models/spontim_r2plus1d.pth`).
- The new models use their own input rules (224 px, 32+8 or 16 frames) and treat output 1 as "fight". The old model stays as it was. The clip buffer keeps small copies of frames so long clips do not use much memory.
- SlowFast needs the `pytorchvideo` package. If it is missing, the camera shows "MODEL NOT LOADED" with the reason.
- First measurements are in the model comparison spreadsheet: SlowFast separated a calm clip from a fight best; R(2+1)D is about 5x heavier than the old model on a CPU. Two short clips are not proof: re-test on your own footage.

## False alarms when the PC is busy, and a tool to measure them

- **Found by a 10-camera test on a 12-thread laptop with calm classroom footage:** the PC sat at 100% CPU and the app reported "fight" at 90-100% on ordinary teaching. Cause 1: when the PC cannot keep up, the 16 frames the fight model looks at are spread over many seconds, so normal movement looks like fast fighting. Measured offline on that clip: 4 of 35 checks above 65% at the true 15 fps, 13 of 17 at 7.5 fps, 3 of 3 at 1.9 fps.
- **Fix:** a check whose 16 frames span more than 1.6 s is now skipped, not trusted. The camera shows "ANALYSER BEHIND" and an old fight is no longer left on screen. This stops fake fights under overload; it also means an overloaded PC watches less, so the camera count for a PC must be set where the analyser keeps up.
- **Not fixed:** even at the true frame rate, this classroom clip still raised one alert (two checks of 91% and 95% in a row). That is the model, not the PC: it needs classroom and corridor footage with no fights as extra training examples. `scripts/score_video.py` scores any video at its true speed and prints alerts per threshold (and false alarms per hour with `--calm`).
- One fight check costs hundreds of milliseconds of CPU, so many cameras with constant movement cannot fit on an ordinary laptop. Real corridors are mostly still (the motion gate skips them); a classroom is not.

## Silent test mode, relaxed hours and staying awake

- **Silent test mode** (Settings > Phone alerts): the app detects and records everything but sends no pop-up, sound, phone alert or phone push. Run it for the first week or two at a school to see how many false alarms there would have been before anyone is bothered. **What did silent mode catch?** shows the count, the busiest cameras and hours, and how many you marked as false alarms.
- **Relaxed hours per camera** (camera form): between two times (a gym during sports period, assembly, recess) a detection is still recorded with its clip but graded Low, and nobody is alerted. Also settable over the server API (`relaxed_start`, `relaxed_end`).
- **Stays awake:** Windows is asked not to sleep while CampusGuard runs (setting "Stay awake", on by default). A laptop with the lid closed can still sleep depending on its power plan: set "When I close the lid: Do nothing".
- **The account's alert numbers are now used.** Numbers saved on the website account are filled into "Alert numbers" when this PC has none, and updated when you save them in Your account.
- The website no longer sends a phone push for an incident held back by silent mode or relaxed hours.
- Tested with fakes only (rules, storage, sync payload); not yet on real cameras.

## Edit your account (shared with the website and phone app)

- **Settings > General now has a "Your account" section:** change your name, school or college name, your phone number and the phone numbers that get alerts (up to 5). It saves to the same account profile the website and the phone app use, so a change in one place shows up in the others.
- The sign-in email is shown but cannot be changed here.
- **Not wired yet:** the alert numbers are stored with the account, but the desktop's own WhatsApp sending still uses the numbers in its alert settings.
- Tested with fakes only (profile client and settings page); not yet against the live website API.

## One office PC watching 40-60 cameras

- **Settings page now has Building numbers, IT / health numbers and "Camera offline after"** (before, these could only be set on the server). Fixed a bug where changing any setting silently reset the settings that have no box on the page (clip frame rate, lead-in/follow-on seconds, disk limit, ...).
- **The desktop app now sends health notices too:** when a camera has had no picture for the chosen minutes (default 5), when it is back, and when the clip disk is low, to the IT numbers / ntfy. One message per outage; many cameras dropping together is one message. Cameras you stopped yourself are not reported.
- **New "crowd" engine profile** for a PC with no GPU watching more than 12 cameras: analyses at most 640 px wide, runs the motion check less often, and draws live previews at 3 fps instead of full speed. Saved clips are unchanged (they come from the full-quality buffer).
- **Camera-limit heads-up:** if there are more cameras than this PC is estimated to handle (about 4 per CPU core and 6 per GB of RAM, at most 120; 150 with a GPU), a notice appears once. This is a cautious estimate, not a measurement; run the load test on the school's PC.
- Tested with fakes only; not yet on a real school laptop.

## Built for schools with several buildings (server mode)

- **Smoother incident clips, with a lead-in and a follow-on.** Clips used to be cut from the frames the AI happened to look at, so they could look choppy when the AI ran behind. A separate short buffer now keeps *every* camera frame (compressed, a few seconds per camera, never a 24/7 recording). A clip starts **5 s before** the detection and ends **8 s after** things calm down (both changeable per school and per camera), saved at about **20 fps** (settings: `clip_fps` 8-30, `clip_width` 480-1920). Not tested on real cameras.
- **Per-camera tuning:** quiet hours (the AI is paused between two times, e.g. a gym at night 22:00-06:00), clip start/end seconds, sensitivity and building. Set in the camera form (app), in the CSV (`quiet_start`, `quiet_end`, `pre_roll`, `post_roll`, `group`, `sensitivity`) or over the server API (`POST /cameras/<id>/tuning`).
- **The headless server now sends the phone alerts itself.** Before, only the desktop app did. The head of the school (`alert_numbers`) gets every alert; people for a building (`building_numbers`, one line per building such as `Main Building: 98... , 97...`) are added when the camera's group matches. Nobody gets the same alert twice. Configure with `--alert-numbers`, `--building-numbers`, `--escalation-numbers`, `--health-numbers`, `--whatsapp-mode`, `--whatsapp-phone-id`, `--whatsapp-token`, `--ntfy-topic`.
- **Health monitoring:** the server tells the IT contacts when a camera has had no picture for 5 minutes (changeable), when it is back, and when the disk running the clips is low. One message per outage; many cameras dropping together (a switch or the recorder) is a single message.
- **Camera limit per server:** `--max-cameras 150 | 250 | 1000` (default 250). A full server refuses more cameras and says so; `/status` reports `camera_capacity` and `camera_slots_free`.
- **CSV import takes up to 1000 cameras per file**, plus the new columns above.
- **Not tested here:** a real WhatsApp send, real cameras, GPU load at 150-250 cameras per server. Benchmark on the school's own hardware first.

## Import cameras from CSV, and fewer popups

- **Import CSV** (new, on the Cameras page): add many cameras in one go. Columns: `name`, `type` (RTSP, HTTP, MJPEG, IP, USB) and `address` are required; `port`, `path`, `username`, `password`, `group`, `sensitivity` (Sensitive, Default, Cautious, Strict) and `ai` (yes/no) are optional. Column names are matched loosely (for example "Camera Name", "IP Address", "Zone"), and Excel's "CSV (Comma delimited)" files, semicolon files and UTF-8 files all work. **Download template** gives a ready file; rows starting with `#` are ignored.
- You see a **preview first**: every row is checked with the same rules as the Add camera form (bad IPs, missing names or types, wrong sensitivity, credentials inside a URL, USB with a password), cameras already added or repeated in the file are skipped, and only the ready rows are imported. Usernames and passwords go to the Windows credential vault as before; passwords are never shown in the preview. Up to 500 cameras per file.
- **One notice instead of a pile.** A camera that cannot connect used to show a new popup on every retry. Now a problem is announced once, and several cameras failing together share one message ("5 cameras need attention: …"), which updates in place. Identical popups no longer stack, and an import shows a single summary.
- **Not tested here:** import on a real Windows PC with the credential vault and live cameras (tested with fakes and the dialog driven offscreen).

## Camera setup: any address, and network scan

- **Any IP address or host name works.** A camera can be on the local network or reachable over the internet: public and private IPv4, IPv6 and host names are all accepted, and a bad address now says what is wrong (for example "999.1.1.1 is not a valid IP address") instead of failing generically. Typing a public address shows a reminder that the camera's port must be forwarded on its router and that it needs a strong password.
- **Scan network** (new, in the camera form): looks for ONVIF cameras and open RTSP ports (554 and 8554) on the network this PC is on, in the background with a Stop button. Each camera found gets its own username, password and stream path; **Add** unlocks only after that camera passes **Test**, and changing anything afterwards asks for a new test. It scans only this PC's own private /24 network, so use it on networks you have permission to scan. Some networks block discovery; typing the address still works.
- Passwords are still never placed inside the camera address; they are passed separately and encoded.
- Fixed: disabled primary buttons looked enabled, and table headers were a pale bar with faint text in dark mode.
- Added checks that every name one file imports from another exists (`scripts/check_cross_references.py`, also run by the tests).
- **Not tested here:** discovery against real cameras and a real school network (tested with a local socket, a faked ONVIF reply and the dialog driven offscreen).

## Floor map, notifications and launch

- **Floor map** (new page under Home): import floor-plan images, drag cameras onto the plan or click a camera and then the plan, move or remove pins. Pins show camera status and pulse coral while the camera has a new incident. Plans and pins are saved on this PC.
- **Fight detected** is now the v3 modal: a scrim, a glass card with the severity pill, incident, camera, confidence and time, and Review clip / Dismiss. Critical alerts keep sounding until dismissed.
- Notices are v3 toasts in the bottom-right corner (they used to go to a hidden status bar, so they were never seen). Marking an incident confirmed or a false alarm offers **Undo**.
- Launch: the logo plays on the v3 graphite colours, then fades into the grey thinking orb while the app loads.
- Navigation rail: eased hover, dock-style icon magnify, a label bubble beside each icon and a keyboard focus ring; Home panel rows slide on hover.
- Removed the old dashboard, charts, history and camera pages, the old top and bottom bars and other unused code.

## v3 interface

- New look across the whole desktop app: graphite surfaces with a coral signal colour, Inter for text, Outfit for titles and JetBrains Mono for figures, in dark and light.
- New Dashboard, Incidents (list, clip, notes, confirm / false alarm, WhatsApp), Alerts (channels and history), Services (pause, reconnect, start with Windows) and Settings tabs, plus a Ctrl K command palette and a Simulate alert button.
- Cameras is now a card grid with **Edit** (new), Disable/Enable AI, Reconnect and Remove. The camera form also sets zone and alert sensitivity.
- Login and the app and installer icon use the three-pill logo.
- Fixed: old rows stayed painted over new ones in the Incidents, Alerts and Dashboard lists; a Python error printed on shutdown from the overlay's event filter; unreadable text on the How it works steps in light mode.
- **Not tested here:** live YOLO detection, WhatsApp Cloud and ntfy delivery, GPU video decoding and a real school RTSP network. The blur behind dialogs is approximated with a translucent layer.

## Phase 3–4: remote desktop client and school server installer

- Added a token-protected remote server viewer with camera health, polled JPEG previews, incident/alert actions, clip playback, camera management and CSV import. Local mode remains the default and uses the existing desktop workflow.
- Added a bounded HTTP client with timeouts, retry/backoff for GET requests, clear authentication/network/TLS errors, and remote server-token storage in Windows Credential Manager.
- Added a camera-scoped snapshot endpoint with authentication, rate limiting, response size limits, and watcher expiry.
- Added a separate Inno Setup server installer, per-user installation, footage folder and storage-cap setup, optional LAN firewall rule, server sign-in/token/status shortcuts, and an uninstall prompt that preserves data by default.
- Added a Windows CI validation workflow for Python 3.14, compile checks, the full pytest suite, dark/light viewer renders at 0/5/120 cameras, and a dedicated server-installer artifact.
- The installer intentionally excludes model checkpoints. The model weights are not part of the server-installer deliverable; schools must provide licensed checkpoints. Note: the repository's current models/ tree still contains checkpoint files, so repository-level model licensing/redistribution should be reviewed separately before making the source repository public.
- **Verification limits:** automated Windows CI does not test a real school RTSP/NVR deployment, actual Windows Task Scheduler boot credentials, UAC/firewall behavior on a school PC, or sustained 100–120 camera throughput. Those require manual validation on the target hardware.


## Python 3.14 migration

- `requirements.txt` minimum versions bumped to the first release of each
  package that ships official Python 3.14 wheels:
  - `torch>=2.9` (PyTorch 2.9 was the first release with official CPython
    3.14 wheels; 2.5 would try to build from source on 3.14 and likely fail)
  - `torchvision>=0.24` (matching torch 2.9)
  - `opencv-python>=4.13.0.92` (first version with a 3.14 wheel — earlier
    versions have no cp314 build and pip would try to compile from source)
  - `numpy>=2.1.3` (added as an explicit dependency — it's imported
    directly in `ai_pipeline.py`, and older numpy releases don't publish
    3.14 wheels either)
  - `PySide6>=6.9`, `ultralytics>=8.4`, `keyring>=25.5` — bumped to the
    first versions confirmed building/working on 3.14
- `setup_windows.bat` now creates the venv with `py -3.14` instead of
  `py -3.11`.
- `README.md` setup instructions updated from Python 3.11 to 3.14.
- 3.13 still works fine with this codebase if 3.14 isn't available yet on
  your machine — nothing in the source is 3.14-specific, only the pinned
  dependency floors changed.

## Bug review

Went through every file in `campusguard/` and `campusguard/ui/` line by
line (camera threading, SQLite schema/queries, credential vault, settings
validation, AI pipeline, and all five UI pages) looking for real issues —
race conditions, unhandled exceptions, resource leaks, off-by-ones, dead
code paths.

**Honest result: no functional bugs were found.** The codebase was already
solid — capture and analysis run on separate threads with a one-slot
mailbox that correctly discards stale frames, camera failures are caught
and reported without crashing the app, the SQLite cooldown logic correctly
prevents duplicate incidents, and credentials never touch the database or
the camera list. Nothing was rewritten for the sake of it.

If something specific breaks for you when you actually run it, tell me
what you see (error text, which screen, which camera source type) and
I'll fix that concretely rather than guessing at problems that aren't
there.
