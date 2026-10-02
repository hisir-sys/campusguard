import json
from datetime import datetime
from pathlib import Path

FILE = Path(__file__).resolve().parents[2] / "data" / "incidents.json"

class IncidentManager:
    def __init__(self):
        self.items = self._load()

    def _load(self):
        try:
            return json.loads(FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    def add(self, camera, event, confidence, severity):
        item = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "camera": camera,
            "event": event,
            "confidence": round(float(confidence) * 100, 1),
            "severity": severity
        }
        self.items.insert(0, item)
        self._save()
        return item

    def clear(self):
        self.items = []
        self._save()

    def _save(self):
        FILE.parent.mkdir(exist_ok=True)
        FILE.write_text(json.dumps(self.items[:500], indent=2), encoding="utf-8")
