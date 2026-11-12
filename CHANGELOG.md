# CampusGuard Desktop — Update Notes

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
