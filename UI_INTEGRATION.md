# CampusGuard UI Integration

This build combines the existing CampusGuard desktop application with the supplied glass navigation UI and dashboard components.

Integrated UI files:
- `campusguard/ui/main_window.py`
- `campusguard/ui/common.py`
- `campusguard/ui/dashboard_page.py`
- `campusguard/ui/glass_nav.py`
- `campusguard/ui/icons.py`
- `campusguard/ui/theme.py`

The existing camera runtime, AI pipeline, storage, settings, credentials, camera page, incidents, alerts, and settings pages are preserved from the base desktop project.

The UI remains local-first and is designed for configured external USB, RTSP, HTTP/MJPEG, and IP camera sources. No sample camera or simulated detection is added.
