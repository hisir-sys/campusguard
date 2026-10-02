from pathlib import Path
import time
import cv2

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None

class Detector:
    def __init__(self, model_path, confidence):
        self.model_path = Path(model_path)
        self.confidence = confidence
        self.model = None
        self.previous = None
        self.last_alert = 0
        self.load()

    def load(self):
        if YOLO and self.model_path.exists():
            try:
                self.model = YOLO(str(self.model_path))
            except Exception:
                self.model = None

    def process(self, frame):
        if self.model is not None:
            annotated = frame.copy()
            detections = []
            results = self.model.predict(
                source=frame,
                conf=self.confidence,
                verbose=False,
                device="cpu"
            )
            for result in results:
                names = result.names or {}
                if result.boxes is None:
                    continue
                for box in result.boxes:
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    label = names.get(cls, str(cls))
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    cv2.rectangle(
                        annotated, (x1, y1), (x2, y2),
                        (50, 220, 150), 2
                    )
                    cv2.putText(
                        annotated, f"{label} {conf:.0%}",
                        (x1, max(20, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (50, 220, 150), 2
                    )
                    detections.append({
                        "event": label,
                        "confidence": conf,
                        "severity": "CRITICAL" if conf >= 0.70 else "WARNING"
                    })
            return annotated, detections

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        detections = []
        if self.previous is not None:
            score = float(cv2.absdiff(self.previous, gray).mean())
            if score > 18:
                detections.append({
                    "event": "HIGH ACTIVITY",
                    "confidence": min(score / 60.0, 0.99),
                    "severity": "WARNING"
                })
        self.previous = gray
        return frame, detections

    def can_alert(self, cooldown):
        now = time.time()
        if now - self.last_alert >= cooldown:
            self.last_alert = now
            return True
        return False

    @property
    def status(self):
        return "YOLO READY" if self.model else "ACTIVITY FALLBACK"
