import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)
FILE = DATA / "settings.json"

DEFAULT = {
    "model_path": "models/best.pt",
    "confidence": 0.45,
    "alert_cooldown": 5
}

def load():
    try:
        return {**DEFAULT, **json.loads(FILE.read_text(encoding="utf-8"))}
    except Exception:
        return DEFAULT.copy()

def save(values):
    FILE.write_text(json.dumps(values, indent=2), encoding="utf-8")
