from .camera_source import CameraSource
from .frame_processor import CameraWorker
from config import MAX_CAMERAS


class CameraManager:
    def __init__(self, on_event):
        self.cameras = {}
        self.on_event = on_event

    def add(self, source, name=None, loop=False):
        if len(self.cameras) >= MAX_CAMERAS:
            raise ValueError(f"Maximum of {MAX_CAMERAS} cameras reached")
        camera_id = max(self.cameras.keys(), default=0) + 1
        worker = CameraWorker(camera_id, CameraSource(source, name, loop=loop), self.on_event)
        self.cameras[camera_id] = worker
        worker.start()
        return camera_id

    def remove(self, camera_id):
        worker = self.cameras.pop(int(camera_id), None)
        if worker:
            worker.stop()

    def restart(self, camera_id):
        worker = self.get(camera_id)
        if not worker:
            return False
        worker.restart()
        return True

    def snapshot(self):
        return [v.snapshot() for v in self.cameras.values()]

    def get(self, camera_id):
        return self.cameras.get(int(camera_id))

    def shutdown(self):
        for worker in list(self.cameras.values()):
            worker.stop()
