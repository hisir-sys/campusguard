# CampusGuard in a multi-building school

CampusGuard is the AI layer on top of the school's existing cameras and recorder. It does not replace
the recorder: it keeps a few seconds of video per camera in memory and saves a clip only when a fight
is detected.

## Two ways to deploy

| | One server for the campus | One server per building |
|---|---|---|
| Cameras per server | up to 1000 (`--max-cameras 1000`) | 150 or 250 (`--max-cameras 150`) |
| Needs | one strong GPU server | a smaller GPU machine in each building |
| If it fails | the whole campus is unwatched | one building is unwatched |
| Network | all camera streams must reach the one server (fibre/VLAN between buildings) | each server only reads its own building's cameras |
| Alerts | one server sends everything | each server sends its own; set the same head number on all |

For per-building servers, give every server the same head number and its own building's numbers:

    CampusGuard.exe --configure-server --server-name "Building A" --max-cameras 150 ^
      --alert-numbers "98xxxxxxxx" --building-numbers "Building A: 97xxxxxxxx, 96xxxxxxxx" ^
      --health-numbers "95xxxxxxxx" --whatsapp-mode cloud --whatsapp-phone-id ... --whatsapp-token ...

Then start it with `CampusGuard.exe --server`. Set each camera's `group` to the building name exactly as written in `--building-numbers`.

## Camera streams

Point CampusGuard at the camera's (or recorder's) **sub-stream**, not the main stream: set the sub-stream
on the camera or NVR to about 1280x720, 15-20 fps, H.264, and use its RTSP path (for Hikvision-style
cameras `Streaming/Channels/102`). The same stream is used for detection and for the saved clip, so it
must be smooth; a 640x360 stream looks blocky in a clip.

## Adding cameras

1. Export the camera list from the NVR/VMS (name, IP, channel, login).
2. Fill `campusguard-cameras-template.csv` (Cameras -> Import CSV -> Download template). One building per file works well.
3. Import; fix any red rows; run **Scan network** for cameras that were missed.
4. Cameras start a few at a time so the network is not hit by hundreds of connections at once.

## Before selling it to a school

Run a pilot on 30-50 cameras for 2 weeks: count false alerts, check clip smoothness, and measure GPU/CPU
use per camera. Scale the camera limit from those numbers, not from a guess.
