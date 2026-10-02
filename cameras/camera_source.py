from pathlib import Path
import cv2


class CameraSource:
    """OpenCV source wrapper for webcams and local video files."""

    def __init__(self, source, name=None, loop=False):
        raw = str(source).strip()
        self.source = int(raw) if raw.isdigit() else raw
        self.name = name or (f"Camera {self.source}" if isinstance(self.source, int) else Path(raw).stem)
        self.loop = loop
        self.cap = None
        self.is_file = not isinstance(self.source, int)

    def open(self):
        self.cap = cv2.VideoCapture(self.source)
        if isinstance(self.source, int):
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
            self.cap.set(cv2.CAP_PROP_FPS, 20)
        return bool(self.cap.isOpened())

    def read(self):
        if self.cap is None and not self.open():
            return False, None
        ok, frame = self.cap.read()
        if not ok and self.is_file and self.loop:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        return ok, frame

    def release(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
