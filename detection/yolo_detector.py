"""Optional YOLO violence detector based on the supplied YOLOv8 weights."""

class YOLOViolenceDetector:
    def __init__(self, model_path):
        from ultralytics import YOLO
        self.model = YOLO(str(model_path))

    def predict(self, frame, conf=0.35):
        result = self.model.predict(source=frame, conf=conf, verbose=False)[0]
        detections = []
        for box in result.boxes:
            cls = int(box.cls.item())
            score = float(box.conf.item())
            xyxy = [int(v) for v in box.xyxy[0].tolist()]
            name = result.names.get(cls, str(cls)) if hasattr(result, "names") else str(cls)
            detections.append({"class_id": cls, "label": name, "confidence": score, "box": xyxy})
        return detections
