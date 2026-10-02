import time
from collections import defaultdict
from .incident_logger import IncidentLogger
from config import ALERT_COOLDOWN


class AlertManager:
    def __init__(self, log_path):
        self.logger = IncidentLogger(log_path)
        self.last_alert = defaultdict(float)

    def handle(self, camera_id, camera_name, result):
        if result.get("severity") not in ("warning", "critical"):
            return None
        now = time.time()
        if now - self.last_alert[camera_id] < ALERT_COOLDOWN:
            return None
        self.last_alert[camera_id] = now
        incident = self.logger.add(camera_id, camera_name, result)
        # Optional integrations can be added here without coupling the detector to messaging.
        return incident
