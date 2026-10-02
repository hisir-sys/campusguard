import cv2
import threading
import time
from detection import CampusGuardDetector
from config import JPEG_QUALITY


class CameraWorker:
    def __init__(self, camera_id, source, on_event):
        self.camera_id = camera_id
        self.source = source
        self.on_event = on_event
        self.detector = CampusGuardDetector()
        self.latest_jpeg = None
        self.status = "starting"
        self.last_result = {"label": "warming_up", "fight_probability": 0.0, "severity": "normal"}
        self.frames_processed = 0
        self.last_frame_at = None
        self.fps = 0.0
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.started_at = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.started_at = time.time()
        self.thread = threading.Thread(target=self._loop, name=f"camera-{self.camera_id}", daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.5)
        self.source.release()
        self.status = "stopped"

    def restart(self):
        self.stop()
        self.detector.reset()
        self.latest_jpeg = None
        self.status = "starting"
        self.start()

    def _loop(self):
        if not self.source.open():
            self.status = "offline"
            return
        self.status = "live"
        last_fps_time = time.time()
        frames_since = 0

        while self.running:
            ok, frame = self.source.read()
            if not ok:
                self.status = "ended" if self.source.is_file else "offline"
                self.running = False
                break

            self.status = "live"
            frames_since += 1
            self.frames_processed += 1
            now = time.time()
            self.last_frame_at = now
            if now - last_fps_time >= 1.0:
                self.fps = frames_since / (now - last_fps_time)
                frames_since = 0
                last_fps_time = now

            result = self.detector.process(frame)
            self.last_result = result
            severity = result.get("severity", "normal")
            if severity in ("warning", "critical"):
                self.on_event(self.camera_id, self.source.name, result)

            self._annotate(frame, result)
            ok2, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
            if ok2:
                with self.lock:
                    self.latest_jpeg = encoded.tobytes()
            time.sleep(0.005)

    def _annotate(self, frame, result):
        label = result.get("label", "warming_up")
        p = float(result.get("fight_probability", 0.0))
        severity = result.get("severity", "normal").upper()
        source = result.get("source", "temporal_mc3")
        color = (80, 225, 167) if severity == "NORMAL" else (40, 190, 255) if severity == "WARNING" else (80, 90, 255)
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 78), (5, 10, 16), -1)
        cv2.putText(frame, f"{severity}  |  {label}  |  {p:.0%}", (18, 32), cv2.FONT_HERSHEY_SIMPLEX, .72, color, 2)
        cv2.putText(frame, f"{self.source.name}  |  {source}  |  {self.fps:.1f} FPS", (18, 60), cv2.FONT_HERSHEY_SIMPLEX, .52, (210, 220, 230), 1)

    def mjpeg_frame(self):
        with self.lock:
            return self.latest_jpeg

    def snapshot(self):
        return {
            "id": self.camera_id,
            "name": self.source.name,
            "status": self.status,
            "source": str(self.source.source),
            "is_file": self.source.is_file,
            "fps": round(self.fps, 1),
            "frames_processed": self.frames_processed,
            "result": self.last_result,
        }
