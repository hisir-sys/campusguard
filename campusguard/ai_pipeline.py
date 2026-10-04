from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import torch

from campusguard.model_registry import EnhancedEnsemble, MODEL_PROFILES, VideoClassifier
from campusguard.settings import AppSettings

ModelStatusCallback = Callable[[str, str], None]
Event = tuple[str, float, str]

SKELETON_EDGES = (
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12), (11, 13), (13, 15),
    (12, 14), (14, 16),
)


@dataclass
class TrackedPerson:
    track_id: int
    display_id: int
    bbox: tuple[int, int, int, int]
    detection_confidence: float
    keypoints: np.ndarray | None = None
    pose_confidence: float = 0.0
    center: tuple[float, float] = (0.0, 0.0)
    involved: bool = False
    violence_confidence: float | None = None
    close_to: set[int] = field(default_factory=set)


class InteractionEngine:
    """Finds people who are spatially interacting without treating proximity as proof of violence."""

    def __init__(self) -> None:
        self.pair_history: dict[tuple[int, int], deque[bool]] = {}

    @staticmethod
    def _close(a: TrackedPerson, b: TrackedPerson) -> bool:
        ax, ay = a.center
        bx, by = b.center
        distance = float(np.hypot(ax - bx, ay - by))
        ah = max(1, a.bbox[3] - a.bbox[1])
        bh = max(1, b.bbox[3] - b.bbox[1])
        scale = max(ah, bh)
        return distance <= scale * 1.45

    def update(self, people: list[TrackedPerson]) -> list[tuple[int, int]]:
        pairs: list[tuple[int, int]] = []
        for index, left in enumerate(people):
            for right in people[index + 1:]:
                key = tuple(sorted((left.track_id, right.track_id)))
                close = self._close(left, right)
                history = self.pair_history.setdefault(key, deque(maxlen=4))
                history.append(close)
                if close:
                    left.close_to.add(right.track_id)
                    right.close_to.add(left.track_id)
                if sum(history) >= 2:
                    pairs.append(key)

        active = {tuple(sorted((a.track_id, b.track_id))) for a, b in combinations(people)}
        for key in list(self.pair_history):
            if key not in active:
                del self.pair_history[key]
        return pairs


def combinations(items: list[TrackedPerson]):
    for index, left in enumerate(items):
        for right in items[index + 1:]:
            yield left, right


class FightDecision:
    def __init__(self, threshold: float) -> None:
        self.threshold = threshold
        self.states: deque[str] = deque(maxlen=3)
        self.event_latched = False

    def update(self, state: str, confidence: float | None) -> Event | None:
        self.threshold = self.threshold
        self.states.append(state)
        if state == "NORMAL":
            self.event_latched = False
            return None
        if len(self.states) < self.states.maxlen:
            return None
        if not all(item == state for item in self.states):
            return None
        if self.event_latched or confidence is None or confidence < self.threshold:
            return None
        self.event_latched = True
        severity = "HIGH" if state == "FIGHT DETECTED" else "MEDIUM"
        return state, confidence, severity


class VisionPipeline:
    """YOLO person detection + ByteTrack + YOLO Pose + selectable temporal violence model."""

    def __init__(self, settings: AppSettings, status: ModelStatusCallback) -> None:
        torch.set_num_threads(1)
        self.status = status
        self.settings = settings
        self.detector = None
        self.pose_model = None
        self.device = self._select_device(settings.device)
        self.classifiers: dict[str, VideoClassifier] = {}
        self.ensemble: EnhancedEnsemble | None = None
        self.decision = FightDecision(settings.confidence_threshold)
        self.interactions = InteractionEngine()
        self.display_ids: dict[int, int] = {}
        self.next_display_id = 1
        self.last_state = "MODEL NOT LOADED"
        self.last_confidence: float | None = None
        self.last_involved_ids: set[int] = set()
        self._load_models(settings)

    def configure(self, settings: AppSettings) -> None:
        reload_models = (
            settings.detector_model_path != self.settings.detector_model_path
            or settings.pose_model_path != self.settings.pose_model_path
            or settings.fight_model_path != self.settings.fight_model_path
            or settings.fdsc_mc3_model_path != self.settings.fdsc_mc3_model_path
            or settings.r3d_model_path != self.settings.r3d_model_path
            or settings.x3d_model_path != self.settings.x3d_model_path
            or settings.device != self.settings.device
        )
        selection_changed = settings.violence_model != self.settings.violence_model
        self.settings = settings
        self.decision.threshold = settings.confidence_threshold
        if reload_models:
            self.device = self._select_device(settings.device)
            self._load_models(settings)
        elif selection_changed:
            self.status("fight", f"VIOLENCE MODEL — {self.model_display_name(settings.violence_model)}")

        for classifier in self.classifiers.values():
            classifier.update(settings.confidence_threshold, settings.fight_positive_class)
        if self.ensemble:
            self.ensemble.update(settings.confidence_threshold, settings.fight_positive_class)

    @staticmethod
    def model_display_name(key: str) -> str:
        if key == "enhanced":
            return "CampusGuard Enhanced"
        return MODEL_PROFILES.get(key, MODEL_PROFILES["mc3"]).name

    def _select_device(self, requested: str) -> torch.device:
        if requested == "cuda" and not torch.cuda.is_available():
            self.status("device", "CUDA unavailable — using CPU")
            return torch.device("cpu")
        if requested == "cuda" or (requested == "auto" and torch.cuda.is_available()):
            try:
                self.status("device", f"CUDA available — {torch.cuda.get_device_name(0)}")
            except Exception:
                self.status("device", "CUDA available")
            return torch.device("cuda:0")
        self.status("device", "CPU selected")
        return torch.device("cpu")

    def _load_models(self, settings: AppSettings) -> None:
        self.detector = self._load_yolo("detector", settings.detector_model_path, "detect")
        self.pose_model = self._load_yolo("pose", settings.pose_model_path, "pose")

        paths = {
            "mc3": settings.fight_model_path,
            "fdsc_mc3": settings.fdsc_mc3_model_path,
            "r3d": settings.r3d_model_path,
            "x3d": settings.x3d_model_path,
        }
        self.classifiers.clear()
        for key, profile in MODEL_PROFILES.items():
            self.classifiers[key] = VideoClassifier(
                profile,
                paths[key],
                self.device,
                settings.fight_positive_class,
                settings.confidence_threshold,
                self.status,
            )

        self.ensemble = EnhancedEnsemble(list(self.classifiers.values()), settings.confidence_threshold)
        self.status("fight", f"VIOLENCE MODEL — {self.model_display_name(settings.violence_model)}")

    def _load_yolo(self, component: str, model_path: str, task: str):
        path = Path(model_path).expanduser()
        if not model_path.strip() or not path.is_file():
            self.status(component, f"MODEL NOT LOADED — file not found: {path}")
            return None
        try:
            from ultralytics import YOLO
            model = YOLO(str(path), task=task)
            model.to(str(self.device))
            self.status(component, f"READY — {path.name}")
            return model
        except Exception as error:
            self.status(component, f"MODEL NOT LOADED — {error}")
            return None

    def process(
        self,
        frame: np.ndarray,
        settings: AppSettings,
        ai_enabled: bool,
        tracking_enabled: bool,
        pose_enabled: bool,
    ) -> tuple[np.ndarray, str, float | None, Event | None]:
        self.configure(settings)
        annotated = frame.copy()
        state = "AI DISABLED" if not ai_enabled else "MODEL NOT LOADED"
        confidence: float | None = None
        event: Event | None = None

        if not ai_enabled:
            cv2.putText(annotated, "AI OFF", (18, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (180, 180, 180), 2, cv2.LINE_AA)
            return annotated, state, confidence, event

        people: list[TrackedPerson] = []
        if settings.detection_enabled and self.detector is not None:
            try:
                people = self._detect_people(annotated, tracking_enabled, settings)
            except Exception as error:
                self.detector = None
                self.status("detector", f"MODEL ERROR — {error}")

        if settings.pose_enabled and pose_enabled and self.pose_model is not None:
            try:
                self._attach_pose(frame, people, annotated, settings)
            except Exception as error:
                self.pose_model = None
                self.status("pose", f"MODEL ERROR — {error}")

        pair_ids = self.interactions.update(people)
        model = self._selected_model(settings.violence_model)
        if model is not None and model.ready:
            try:
                result = model.add_frame(frame)
                if result is not None:
                    state, confidence = result
                    self.last_state, self.last_confidence = state, confidence
                    event = self.decision.update(state, confidence)
                    self._apply_involvement(people, pair_ids, state, confidence)
                else:
                    state, confidence = self.last_state, self.last_confidence
                    self._apply_involvement(people, pair_ids, state, confidence)
            except Exception as error:
                self.status("fight", f"MODEL ERROR — {error}")
                state, confidence = "MODEL ERROR", None
                self.last_state, self.last_confidence = state, confidence
        else:
            state, confidence = "MODEL NOT LOADED", None

        self._draw_people(annotated, people)
        self._draw_status(annotated, state, confidence, settings.violence_model)
        return annotated, state, confidence, event

    def _selected_model(self, key: str):
        if key == "enhanced":
            return self.ensemble
        return self.classifiers.get(key)

    def _detect_people(self, annotated: np.ndarray, tracking_enabled: bool, settings: AppSettings) -> list[TrackedPerson]:
        if tracking_enabled:
            results = self.detector.track(
                annotated,
                persist=True,
                tracker="bytetrack.yaml",
                classes=[0],
                conf=settings.confidence_threshold,
                device=str(self.device),
                verbose=False,
            )
        else:
            results = self.detector.predict(
                annotated,
                classes=[0],
                conf=settings.confidence_threshold,
                device=str(self.device),
                verbose=False,
            )
        if not results or results[0].boxes is None:
            return []

        boxes = results[0].boxes
        xyxy = boxes.xyxy.detach().cpu().numpy()
        confs = boxes.conf.detach().cpu().numpy() if boxes.conf is not None else np.ones(len(xyxy))
        ids = boxes.id.detach().cpu().numpy().astype(int) if boxes.id is not None else np.arange(1, len(xyxy) + 1)

        people = []
        for raw_box, raw_conf, raw_id in zip(xyxy, confs, ids):
            x1, y1, x2, y2 = (int(v) for v in raw_box)
            track_id = int(raw_id)
            if track_id not in self.display_ids:
                self.display_ids[track_id] = self.next_display_id
                self.next_display_id += 1
            person = TrackedPerson(
                track_id=track_id,
                display_id=self.display_ids[track_id],
                bbox=(x1, y1, x2, y2),
                detection_confidence=float(raw_conf),
                center=((x1 + x2) / 2.0, (y1 + y2) / 2.0),
            )
            people.append(person)
        return people

    def _attach_pose(self, frame: np.ndarray, people: list[TrackedPerson], annotated: np.ndarray, settings: AppSettings) -> None:
        results = self.pose_model.predict(frame, conf=settings.confidence_threshold, device=str(self.device), verbose=False)
        if not results or results[0].keypoints is None:
            return
        keypoints = results[0].keypoints
        points = keypoints.xy.detach().cpu().numpy()
        confidences = keypoints.conf.detach().cpu().numpy() if keypoints.conf is not None else np.ones(points.shape[:2], dtype=np.float32)

        for index, person_points in enumerate(points):
            valid = confidences[index] >= 0.5
            if not np.any(valid):
                continue
            pose_center = np.mean(person_points[valid], axis=0)
            best = min(people, key=lambda p: float(np.hypot(p.center[0] - pose_center[0], p.center[1] - pose_center[1])), default=None)
            if best is None:
                continue
            distance = float(np.hypot(best.center[0] - pose_center[0], best.center[1] - pose_center[1]))
            box_scale = max(30, max(best.bbox[2] - best.bbox[0], best.bbox[3] - best.bbox[1]))
            if distance <= box_scale * 0.9:
                best.keypoints = person_points
                best.pose_confidence = float(np.mean(confidences[index][valid]))

    def _apply_involvement(self, people: list[TrackedPerson], pair_ids: list[tuple[int, int]], state: str, confidence: float | None) -> None:
        if confidence is None or confidence < self.settings.confidence_threshold:
            return
        involved_ids: set[int] = set()
        if state in {"FIGHT DETECTED", "POSSIBLE ALTERCATION"}:
            for left, right in pair_ids:
                involved_ids.update((left, right))
        self.last_involved_ids = involved_ids
        for person in people:
            person.involved = person.track_id in involved_ids
            person.violence_confidence = confidence if person.involved else None

    def _draw_people(self, annotated: np.ndarray, people: list[TrackedPerson]) -> None:
        for person in people:
            x1, y1, x2, y2 = person.bbox
            color = (64, 68, 235) if person.involved else (95, 194, 132)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)

            label = f"PERSON #{person.display_id}"
            if person.involved and person.violence_confidence is not None:
                label += f"  {person.violence_confidence:.0%} VIOLENCE"
            else:
                label += f"  {person.detection_confidence:.0%}"

            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
            top = max(0, y1 - th - 10)
            cv2.rectangle(annotated, (x1, top), (min(annotated.shape[1] - 1, x1 + tw + 10), y1), color, -1)
            cv2.putText(annotated, label, (x1 + 5, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)

            if person.keypoints is not None:
                self._draw_skeleton(annotated, person.keypoints, color)

    def _draw_skeleton(self, annotated: np.ndarray, points: np.ndarray, color: tuple[int, int, int]) -> None:
        for start, end in SKELETON_EDGES:
            if start < len(points) and end < len(points):
                a, b = points[start], points[end]
                if a[0] > 0 and a[1] > 0 and b[0] > 0 and b[1] > 0:
                    cv2.line(annotated, tuple(int(v) for v in a), tuple(int(v) for v in b), color, 2, cv2.LINE_AA)
        for point in points:
            if point[0] > 0 and point[1] > 0:
                cv2.circle(annotated, tuple(int(v) for v in point), 3, (242, 238, 225), -1, cv2.LINE_AA)

    def _draw_status(self, annotated: np.ndarray, state: str, confidence: float | None, model_key: str) -> None:
        text = self.model_display_name(model_key)
        if state not in {"NORMAL", "MODEL NOT LOADED"}:
            text += f"  •  {state}"
        if confidence is not None:
            text += f"  {confidence:.0%}"
        color = self._state_color(state)
        width = min(annotated.shape[1] - 20, max(360, 12 + len(text) * 8))
        cv2.rectangle(annotated, (10, 10), (width, 48), (22, 27, 33), -1)
        cv2.putText(annotated, text, (18, 37), cv2.FONT_HERSHEY_SIMPLEX, 0.58, color, 2, cv2.LINE_AA)

    @staticmethod
    def _state_color(state: str) -> tuple[int, int, int]:
        if state == "FIGHT DETECTED":
            return (74, 74, 223)
        if state == "POSSIBLE ALTERCATION":
            return (49, 176, 221)
        if state == "NORMAL":
            return (95, 194, 132)
        return (180, 180, 180)
