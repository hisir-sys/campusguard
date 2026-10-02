import cv2
from PySide6.QtCore import QObject, Signal, QThread

class Worker(QObject):
    frame = Signal(object)
    error = Signal(str)
    done = Signal()

    def __init__(self, source):
        super().__init__()
        self.source = source
        self.running = True

    def start(self):
        source = int(self.source) if str(self.source).isdigit() else self.source
        capture = cv2.VideoCapture(source)

        if not capture.isOpened():
            self.error.emit(f"Could not open: {self.source}")
            self.done.emit()
            return

        while self.running:
            ok, frame = capture.read()
            if not ok:
                if isinstance(source, str):
                    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                break

            self.frame.emit(frame)
            QThread.msleep(25)

        capture.release()
        self.done.emit()

    def stop(self):
        self.running = False

class CameraManager(QObject):
    frame_ready = Signal(str, object)
    error = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.workers = {}
        self.threads = {}

    def add(self, camera_id, source):
        worker = Worker(source)
        thread = QThread()

        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        worker.frame.connect(
            lambda frame: self.frame_ready.emit(camera_id, frame)
        )
        worker.error.connect(
            lambda message: self.error.emit(camera_id, message)
        )

        self.workers[camera_id] = worker
        self.threads[camera_id] = thread
        thread.start()

    def stop_all(self):
        for worker in self.workers.values():
            worker.stop()
