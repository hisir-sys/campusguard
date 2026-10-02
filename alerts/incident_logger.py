import json
import threading
from datetime import datetime, timezone
from pathlib import Path


class IncidentLogger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        if not self.path.exists(): self.path.write_text('[]', encoding='utf-8')

    def add(self, camera_id, camera_name, result):
        with self.lock:
            try: data = json.loads(self.path.read_text(encoding='utf-8'))
            except Exception: data = []
            item = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "camera_id": camera_id,
                "camera": camera_name,
                "severity": result.get("severity", "warning"),
                "label": result.get("label", "fight"),
                "confidence": round(float(result.get("fight_probability", 0)), 4),
                "source": result.get("source", "unknown"),
            }
            data.insert(0, item)
            self.path.write_text(json.dumps(data[:100], indent=2), encoding='utf-8')
            return item

    def all(self):
        try: return json.loads(self.path.read_text(encoding='utf-8'))
        except Exception: return []
