from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import torch
from torch import nn

from campusguard.settings import AppSettings

ModelStatusCallback = Callable[[str, str], None]
Event = tuple[str, float, str]

SKELETON_EDGES = (
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12), (11, 13), (13, 15),
    (12, 14), (14, 16),
)


class FightActionModel:
    """Loads an MC3-18 checkpoint and scores a real 16-frame video clip."""

    CLIP_LENGTH = 16
    INFERENCE_STRIDE = 8
    INPUT_SIZE = (112, 112)

    def __init__(
        self,
        model_path: str,
        device: torch.device,
        positive_class: int,
        confidence_threshold: float,
        status: ModelStatusCallback,
    ) -> None:
        self.device = device
        self.positive_class = positive_class
        self.confidence_threshold = confidence_threshold
        self.status = status
        self.model: nn.Module | None = None
        self.class_count = 0
        self.frames: deque[np.ndarray] = deque(maxlen=self.CLIP_LENGTH)
        self.recent_states: deque[str] = deque(maxlen=3)
        self.frame_count = 0
        self.last_state = "MODEL NOT LOADED"
        self.last_confidence: float | None = None
        self.event_latched = False
        self.normal_release_count = 0
        self.NORMAL_RELEASE_PREDICTIONS = 6

        self._load(model_path)

    def _load(self, model_path: str) -> None:
        project_root = Path(__file__).resolve().parents[1]
        configured_path = Path(model_path).expanduser() if model_path.strip() else Path()

        # Settings are persisted in the user's AppData database. If an older
        # absolute path points to a previous CampusGuard checkout, recover the
        # bundled MC3 filename from the current project automatically.
        if configured_path.is_absolute():
            path = configured_path
        else:
            path = project_root / configured_path

        if not path.is_file():
            fallback = project_root / "models" / "fight_mc3_18.pth"
            if fallback.is_file():
                path = fallback
                self.status("fight", f"Using project MC3 checkpoint — {path}")
            else:
                self.status("fight", f"MODEL NOT LOADED — file not found: {path}")
                return

        try:
            from torchvision.models.video import mc3_18

            try:
                checkpoint = torch.load(path, map_location="cpu", weights_only=True)
            except TypeError:
                checkpoint = torch.load(path, map_location="cpu")
            except Exception as first_error:
                try:
                    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
                except Exception:
                    raise first_error
            if isinstance(checkpoint, dict):
                state = checkpoint.get(
                    "state_dict",
                    checkpoint.get("model_state_dict", checkpoint),
                )
            else:
                raise ValueError("Checkpoint must contain an MC3-18 state dictionary.")

            if not isinstance(state, dict):
                raise ValueError("Checkpoint does not contain a usable state dictionary.")

            cleaned: dict[str, torch.Tensor] = {}
            for key, value in state.items():
                clean_key = str(key)
                for prefix in ("module.", "model."):
                    if clean_key.startswith(prefix):
                        clean_key = clean_key[len(prefix):]
                cleaned[clean_key] = value

            classifier = cleaned.get("fc.weight")
            if classifier is None or getattr(classifier, "ndim", 0) != 2:
                raise ValueError(
                    "Checkpoint is not a compatible torchvision MC3-18 classifier."
                )
            self.class_count = int(classifier.shape[0])
            if self.class_count not in {2, 3}:
                raise ValueError(
                    f"Checkpoint has {self.class_count} output classes; expected 2 or 3."
                )

            model = mc3_18(weights=None)
            model.fc = nn.Linear(model.fc.in_features, self.class_count)
            model.load_state_dict(cleaned, strict=True)
            model.to(self.device)
            model.eval()
            self.model = model
            self.last_state = "NORMAL"
            self.status(
                "fight",
                f"READY — MC3-18, {self.class_count} output classes ({path.name})",
            )
        except Exception as error:
            self.model = None
            self.last_state = "MODEL NOT LOADED"
            self.status("fight", f"MODEL NOT LOADED — {error}")

    def update_threshold(self, value: float, positive_class: int) -> None:
        self.confidence_threshold = value
        self.positive_class = positive_class

    def add_frame(self, frame: np.ndarray) -> tuple[str, float | None, Event | None]:
        if self.model is None:
            return self.last_state, None, None

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, self.INPUT_SIZE, interpolation=cv2.INTER_AREA)
        self.frames.append(resized)
        self.frame_count += 1

        if (
            len(self.frames) < self.CLIP_LENGTH
            or self.frame_count % self.INFERENCE_STRIDE != 0
        ):
            return self.last_state, self.last_confidence, None

        clip = np.stack(tuple(self.frames), axis=0)
        tensor = torch.from_numpy(clip).permute(3, 0, 1, 2).unsqueeze(0)
        tensor = tensor.to(device=self.device, dtype=torch.float32) / 255.0
        mean = torch.tensor(
            (0.43216, 0.394666, 0.37645),
            device=self.device,
            dtype=torch.float32,
        ).view(1, 3, 1, 1, 1)
        std = torch.tensor(
            (0.22803, 0.22145, 0.216989),
            device=self.device,
            dtype=torch.float32,
        ).view(1, 3, 1, 1, 1)
        tensor = (tensor - mean) / std

        try:
            with torch.inference_mode():
                logits = self.model(tensor)
                probabilities = torch.softmax(logits, dim=1)[0].detach().cpu().numpy()
        except Exception as error:
            self.model = None
            self.last_state = "MODEL ERROR"
            self.status("fight", f"MODEL ERROR — {error}")
            return self.last_state, None, None

        if self.class_count == 3:
            predicted_class = int(np.argmax(probabilities))
            confidence = float(probabilities[predicted_class])
            state = (
                ("NORMAL", "POSSIBLE ALTERCATION", "FIGHT DETECTED")[predicted_class]
                if confidence >= self.confidence_threshold
                else "NORMAL"
            )
        else:
            positive_class = min(max(self.positive_class, 0), 1)
            confidence = float(probabilities[positive_class])
            if confidence < self.confidence_threshold:
                state = "NORMAL"
            elif confidence >= 0.85:
                state = "FIGHT DETECTED"
            else:
                state = "POSSIBLE ALTERCATION"

        self.last_state = state
        self.last_confidence = confidence
        return state, confidence, self._stable_event(state, confidence)

    def _stable_event(self, state: str, confidence: float) -> Event | None:
        self.recent_states.append(state)

        # Once an incident has been raised, do not re-arm on a single
        # noisy NORMAL prediction. The classifier must remain NORMAL for
        # several consecutive temporal predictions before the same fight
        # is considered finished. This guarantees one incident/alert for
        # one continuous fight sequence.
        if state == "NORMAL":
            self.normal_release_count += 1
        else:
            self.normal_release_count = 0

        if self.normal_release_count >= self.NORMAL_RELEASE_PREDICTIONS:
            self.event_latched = False
            self.normal_release_count = 0
            self.recent_states.clear()
            return None

        if len(self.recent_states) < self.recent_states.maxlen:
            return None

        stable_state = self.recent_states[-1]
        if (
            not self.event_latched
            and stable_state != "NORMAL"
            and all(item == stable_state for item in self.recent_states)
            and confidence >= self.confidence_threshold
        ):
            self.event_latched = True
            severity = "HIGH" if stable_state == "FIGHT DETECTED" else "MEDIUM"
            return stable_state, confidence, severity
        return None


class VisionPipeline:
    """Runs real local YOLO detection, ByteTrack, YOLO pose, and MC3-18 inference."""

    def __init__(self, settings: AppSettings, status: ModelStatusCallback) -> None:
        torch.set_num_threads(1)
        self.status = status
        self.settings = settings
        self.detector = None
        self.pose_model = None
        self.device = self._select_device(settings.device)
        self.action_model: FightActionModel | None = None
        self._load_models(settings)

    def configure(self, settings: AppSettings) -> None:
        paths_changed = (
            settings.detector_model_path != self.settings.detector_model_path
            or settings.pose_model_path != self.settings.pose_model_path
            or settings.fight_model_path != self.settings.fight_model_path
            or settings.device != self.settings.device
        )
        self.settings = settings
        if paths_changed:
            self.device = self._select_device(settings.device)
            self._load_models(settings)
        elif self.action_model:
            self.action_model.update_threshold(
                settings.confidence_threshold,
                settings.fight_positive_class,
            )

    def _select_device(self, requested: str) -> torch.device:
        cuda_available = torch.cuda.is_available()
        if requested == "cuda" and not cuda_available:
            self.status("device", "CUDA unavailable — using CPU")
            return torch.device("cpu")
        if requested == "cuda" or (requested == "auto" and cuda_available):
            try:
                name = torch.cuda.get_device_name(0)
                self.status("device", f"CUDA available — {name}")
            except Exception:
                self.status("device", "CUDA available")
            return torch.device("cuda:0")
        self.status("device", "CPU selected")
        return torch.device("cpu")

    def _load_models(self, settings: AppSettings) -> None:
        self.detector = self._load_yolo(
            "detector",
            settings.detector_model_path,
            "detect",
        )
        self.pose_model = self._load_yolo(
            "pose",
            settings.pose_model_path,
            "pose",
        )
        self.action_model = FightActionModel(
            settings.fight_model_path,
            self.device,
            settings.fight_positive_class,
            settings.confidence_threshold,
            self.status,
        )

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
            cv2.putText(
                annotated,
                "AI OFF",
                (18, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (180, 180, 180),
                2,
                cv2.LINE_AA,
            )
            return annotated, state, confidence, event

        if settings.detection_enabled and self.detector is not None:
            try:
                self._draw_detection(annotated, tracking_enabled, settings)
            except Exception as error:
                self.detector = None
                self.status("detector", f"MODEL ERROR — {error}")

        if settings.pose_enabled and pose_enabled and self.pose_model is not None:
            try:
                self._draw_pose(frame, annotated, settings)
            except Exception as error:
                self.pose_model = None
                self.status("pose", f"MODEL ERROR — {error}")

        if self.action_model is not None and self.action_model.model is not None:
            try:
                state, confidence, event = self.action_model.add_frame(frame)
            except Exception as error:
                self.status("fight", f"MODEL ERROR — {error}")
                state = "MODEL ERROR"
                confidence = None

        text = state
        if confidence is not None:
            text = f"{state}  {confidence:.0%}"
        color = self._state_color(state)
        cv2.rectangle(annotated, (10, 10), (min(annotated.shape[1] - 10, 420), 48), (22, 27, 33), -1)
        cv2.putText(
            annotated,
            text,
            (18, 37),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.68,
            color,
            2,
            cv2.LINE_AA,
        )
        return annotated, state, confidence, event

    def _draw_detection(
        self,
        frame: np.ndarray,
        tracking_enabled: bool,
        settings: AppSettings,
    ) -> None:
        if tracking_enabled:
            results = self.detector.track(
                source=frame,
                persist=True,
                tracker="bytetrack.yaml",
                classes=[0],
                conf=settings.confidence_threshold,
                device=str(self.device),
                verbose=False,
            )
        else:
            results = self.detector.predict(
                source=frame,
                classes=[0],
                conf=settings.confidence_threshold,
                device=str(self.device),
                verbose=False,
            )
        if not results:
            return
        boxes = results[0].boxes
        if boxes is None:
            return
        coordinates = boxes.xyxy.detach().cpu().numpy()
        scores = boxes.conf.detach().cpu().numpy()
        track_ids = (
            boxes.id.detach().cpu().numpy().astype(int)
            if tracking_enabled and boxes.id is not None
            else None
        )
        for index, coordinates_for_box in enumerate(coordinates):
            x1, y1, x2, y2 = (int(value) for value in coordinates_for_box)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (66, 184, 126), 2)
            label = f"Person {scores[index]:.0%}"
            if track_ids is not None and index < len(track_ids):
                label = f"PERSON #{track_ids[index]}  {scores[index]:.0%}"
            cv2.putText(
                frame,
                label,
                (x1, max(18, y1 - 7)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (66, 184, 126),
                2,
                cv2.LINE_AA,
            )

    def _draw_pose(
        self,
        original: np.ndarray,
        annotated: np.ndarray,
        settings: AppSettings,
    ) -> None:
        results = self.pose_model.predict(
            source=original,
            conf=settings.confidence_threshold,
            device=str(self.device),
            verbose=False,
        )
        if not results or results[0].keypoints is None:
            return
        keypoints = results[0].keypoints
        points = keypoints.xy.detach().cpu().numpy()
        confidences = (
            keypoints.conf.detach().cpu().numpy()
            if keypoints.conf is not None
            else np.ones(points.shape[:2], dtype=np.float32)
        )
        for person_index, person_points in enumerate(points):
            person_confidences = confidences[person_index]
            for start, end in SKELETON_EDGES:
                if (
                    start < len(person_points)
                    and end < len(person_points)
                    and person_confidences[start] >= 0.5
                    and person_confidences[end] >= 0.5
                ):
                    a = tuple(int(value) for value in person_points[start])
                    b = tuple(int(value) for value in person_points[end])
                    cv2.line(annotated, a, b, (216, 177, 83), 2, cv2.LINE_AA)
            for point_index, point in enumerate(person_points):
                if person_confidences[point_index] >= 0.5:
                    center = tuple(int(value) for value in point)
                    cv2.circle(annotated, center, 3, (242, 238, 225), -1, cv2.LINE_AA)

    @staticmethod
    def _state_color(state: str) -> tuple[int, int, int]:
        if state == "FIGHT DETECTED":
            return (74, 74, 223)
        if state == "POSSIBLE ALTERCATION":
            return (49, 176, 221)
        if state in {"NORMAL", "AI DISABLED"}:
            return (95, 194, 132)
        return (180, 180, 180)