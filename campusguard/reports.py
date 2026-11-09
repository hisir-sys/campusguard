"""Trend report: incidents per day, hour and camera, plus the false-alarm rate.

Pure functions over incident rows, so the numbers can be tested without a UI.
The HTML export is one self-contained file (no scripts, no network).
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from html import escape
from typing import Any

CLOSED_FALSE = "FALSE_ALARM"


def _parse(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    per_day: Counter[str] = Counter()
    per_hour: Counter[int] = Counter()
    per_camera: Counter[str] = Counter()
    false_by_camera: Counter[str] = Counter()
    severity: Counter[str] = Counter()
    false_alarms = 0
    for row in rows:
        when = _parse(row.get("happened_at"))
        if when:
            per_day[when.date().isoformat()] += 1
            per_hour[when.hour] += 1
        name = str(row.get("camera_name") or row.get("camera_id") or "Unknown")
        per_camera[name] += 1
        severity[str(row.get("severity", "")).upper()] += 1
        if str(row.get("status", "")).upper() == CLOSED_FALSE:
            false_alarms += 1
            false_by_camera[name] += 1
    total = len(rows)
    return {
        "total": total,
        "false_alarms": false_alarms,
        "false_alarm_rate": (false_alarms / total) if total else 0.0,
        "per_day": dict(sorted(per_day.items())),
        "per_hour": {h: per_hour.get(h, 0) for h in range(24)},
        "per_camera": per_camera.most_common(),
        "false_by_camera": dict(false_by_camera),
        "severity": dict(severity),
        "busiest_hour": max(per_hour, key=per_hour.get) if per_hour else None,
    }


def _bars(items: list[tuple[str, int]], width: int = 360) -> str:
    peak = max((n for _, n in items), default=0) or 1
    out = []
    for label, n in items:
        out.append(
            f'<div class="r"><span class="l">{escape(str(label))}</span>'
            f'<span class="b" style="width:{max(2, int(width * n / peak))}px"></span>'
            f'<span class="n">{n}</span></div>'
        )
    return "".join(out)


def render_html(rows: list[dict[str, Any]], title: str = "CampusGuard trend report") -> str:
    s = summarize(rows)
    hours = [(f"{h:02d}:00", n) for h, n in s["per_hour"].items()]
    days = list(s["per_day"].items())[-31:]
    cams = [(f"{name}  ({s['false_by_camera'].get(name, 0)} false)", n) for name, n in s["per_camera"][:20]]
    busiest = f"{s['busiest_hour']:02d}:00" if s["busiest_hour"] is not None else "n/a"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{escape(title)}</title>
<style>body{{font:14px system-ui,sans-serif;margin:32px;color:#1d232b;background:#f6f7f9}}
h1{{font-size:22px}}h2{{font-size:15px;margin-top:28px}}.k{{display:flex;gap:16px;flex-wrap:wrap}}
.k div{{background:#fff;border:1px solid #dde1e7;border-radius:10px;padding:12px 18px}}
.k b{{display:block;font-size:22px}}.r{{display:flex;align-items:center;gap:8px;margin:3px 0}}
.l{{width:210px;font-size:12px;color:#556}}.b{{height:12px;background:#7b8fa8;border-radius:3px;display:inline-block}}
.n{{font-size:12px}}</style></head><body><h1>{escape(title)}</h1>
<p>Generated {datetime.now().strftime('%d %b %Y %H:%M')}. Detections are AI estimates for human review, not proof of wrongdoing.</p>
<div class="k"><div><b>{s['total']}</b>incidents</div><div><b>{s['false_alarms']}</b>false alarms</div>
<div><b>{s['false_alarm_rate']:.0%}</b>false-alarm rate</div><div><b>{busiest}</b>busiest hour</div></div>
<h2>Incidents per day (last 31 days with activity)</h2>{_bars(days)}
<h2>Incidents by hour of day</h2>{_bars(hours)}
<h2>Incidents by camera</h2>{_bars(cams)}</body></html>"""
