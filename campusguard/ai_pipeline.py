from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import copy
import os
import sys
from pathlib import Path
from time import perf_counter
from typing import Callable

import cv2
import numpy as np
import torch

from campusguard.model_registry import EnhancedEnsemble, MODEL_PROFILES, VideoClassifier
from campusguard.settings import AppSettings

ModelStatusCallback = Callable[[str, str], None]
Event = tuple[str, float, str]


def resolve_model_path(value: str) -> Path:
    """Resolve bundled model paths independently of the process working directory."""
    raw = Path(value).expanduser()
    if raw.is_absolute():
        return raw

    # PyInstaller extracts bundled data below _MEIPASS at runtime.
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        bundled = Path(bundle_root) / raw
        if bundled.is_file():
            return bundled

    # Source checkout: resolve relative to the project root, not the user's
    # current PowerShell/shortcut working directory.
    project_root = Path(__file__).resolve().parents[1]
    project_file = project_root / raw
    if project_file.is_file():
        return project_file

    return raw

# Detection confidence is deliberately independent from the 65% violence
# decision threshold so lower-confidence people can still be tracked.
PERSON_DETECTION_CONFIDENCE = 0.35
POSE_DETECTION_CONFIDENCE = 0.25

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
        for person in people:
            person.close_to.clear()
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
    """Turn noisy temporal predictions into one stable, high-confidence event.

    Persistent incidents require several consecutive FIGHT predictions with a
    strong rolling confidence average. POSSIBLE ALTERCATION remains a visual
    state but does not create a persistent incident.
    """

    NORMAL_RELEASE_PREDICTIONS = 6
    # Require several consecutive temporal predictions before creating a
    # persistent incident. This filters isolated classifier spikes while
    # keeping the configured confidence threshold as the primary confidence gate.
    TRIGGER_PREDICTIONS = 4
    MIN_TRIGGER_CONFIDENCE = 0.0

    def __init__(self, threshold: float) -> None:
        self.threshold = threshold
        self.states: deque[str] = deque(maxlen=self.TRIGGER_PREDICTIONS)
        self.confidences: deque[float] = deque(maxlen=self.TRIGGER_PREDICTIONS)
        self.event_latched = False
        self.normal_release_count = 0

    def reset(self) -> None:
        self.states.clear()
        self.confidences.clear()
        self.event_latched = False
        self.normal_release_count = 0

    def update(self, state: str, confidence: float | None) -> Event | None:
        if state == "NORMAL":
            self.states.clear()
            self.confidences.clear()
            self.normal_release_count += 1
            if self.normal_release_count >= self.NORMAL_RELEASE_PREDICTIONS:
                self.event_latched = False
                self.normal_release_count = 0
            return None

        self.normal_release_count = 0

        if state != "FIGHT DETECTED" or confidence is None:
            self.states.clear()
            self.confidences.clear()
            return None

        self.states.append(state)
        self.confidences.append(float(confidence))

        if self.event_latched:
            return None
        if len(self.states) < self.TRIGGER_PREDICTIONS:
            return None
        if not all(item == "FIGHT DETECTED" for item in self.states):
            return None

        rolling_confidence = float(np.mean(self.confidences))
        required_confidence = max(
            float(self.threshold),
            self.MIN_TRIGGER_CONFIDENCE,
        )
        if rolling_confidence < required_confidence:
            return None

        self.event_latched = True
        return "FIGHT DETECTED", rolling_confidence, "HIGH"


class VisionPipeline:
    """YOLO person detection + ByteTrack + YOLO Pose + selectable temporal violence model."""

    def __init__(self, settings: AppSettings, status: ModelStatusCallback) -> None:
        # Keep CPU inference responsive when multiple camera workers run at once.
        # Two threads per worker is a deliberate compromise between throughput and
        # CPU oversubscription on typical Windows demo machines.
        cpu_threads = max(1, min(2, (os.cpu_count() or 2) // 2))
        torch.set_num_threads(cpu_threads)
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
        self.display_track_memory: dict[int, tuple[tuple[int, int, int, int], int]] = {}
        self.next_display_id = 1
        self.fallback_tracks: dict[int, tuple[float, float, float]] = {}
        self.last_scene_signature: tuple[int, int, int] | None = None
        self.scene_cut_cooldown = 0
        self.next_fallback_track_id = -1
        self.last_state = "MODEL NOT LOADED"
        self.last_confidence: float | None = None
        self.last_involved_ids: set[int] = set()
        self.person_buffers: dict[int, deque[np.ndarray]] = {}
        self.person_frame_counts: dict[int, int] = {}
        self.person_scores: dict[int, tuple[str, float]] = {}
        self.last_process_fps = 0.0
        self.last_inference_ms = 0.0
        self.frame_index = 0
        self.last_diagnostics: list[dict[str, object]] = []
        # Expensive detector/pose passes are decimated while the temporal MC3
        # classifier still receives every analyzed frame. This keeps the UI live
        # without removing temporal evidence from Spontim.
        self.cached_people: list[TrackedPerson] = []
        self._load_models(settings)

    def configure(self, settings: AppSettings) -> None:
        # Normalize input first. Enhanced is intentionally non-operational.
        normalized = (
            AppSettings.from_dict({**settings.to_dict(), "violence_model": "mc3"})
            if settings.violence_model == "enhanced"
            else settings
        )
        if settings.violence_model == "enhanced":
            self.status("fight", "CampusGuard Enhanced — COMING SOON (not operational)")

        reload_models = (
            normalized.detector_model_path != self.settings.detector_model_path
            or normalized.pose_model_path != self.settings.pose_model_path
            or normalized.fight_model_path != self.settings.fight_model_path
            or normalized.fdsc_mc3_model_path != self.settings.fdsc_mc3_model_path
            or normalized.r3d_model_path != self.settings.r3d_model_path
            or normalized.x3d_model_path != self.settings.x3d_model_path
            or normalized.device != self.settings.device
        )
        selection_changed = normalized.violence_model != self.settings.violence_model

        self.settings = normalized
        self.decision.threshold = normalized.confidence_threshold

        if reload_models or selection_changed:
            self.device = self._select_device(normalized.device)
            self._load_models(normalized)

        for classifier in self.classifiers.values():
            classifier.update(normalized.confidence_threshold)
        if self.ensemble:
            self.ensemble.update(normalized.confidence_threshold)

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

        self.classifiers.clear()
        self.ensemble = None

        selected_key = settings.violence_model
        if selected_key == "enhanced":
            self.status("fight", "CampusGuard Enhanced — COMING SOON (not operational)")
            selected_key = "fdsc_mc3"

        profile = MODEL_PROFILES.get(selected_key, MODEL_PROFILES["fdsc_mc3"])
        paths = {
            "mc3": settings.fight_model_path,
            "fdsc_mc3": settings.fdsc_mc3_model_path,
            "r3d": settings.r3d_model_path,
            "x3d": settings.x3d_model_path,
        }
        fight_class_override = (
            settings.fight_positive_class
            if selected_key == "mc3"
            else None
        )

        self.classifiers[selected_key] = VideoClassifier(
            profile,
            paths[selected_key],
            self.device,
            settings.confidence_threshold,
            self.status,
            fight_class_override=fight_class_override,
        )
        self.status("fight", f"VIOLENCE MODEL — {self.model_display_name(selected_key)}")

        self.person_buffers.clear()
        self.person_frame_counts.clear()
        self.person_scores.clear()
        self.fallback_tracks.clear()
        self.display_ids.clear()
        self.display_track_memory.clear()
        self.next_display_id = 1
        self.last_scene_signature = None
        self.scene_cut_cooldown = 0
        self.decision.reset()
        self.last_state = "MODEL NOT LOADED"
        self.last_confidence = None
        self.last_involved_ids.clear()
        self.cached_people.clear()

    def _load_yolo(self, component: str, model_path: str, task: str):
        path = resolve_model_path(model_path)
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
        self.frame_index += 1
        self.last_diagnostics.clear()

        if self._detect_scene_cut(frame):
            self._reset_tracking_state()
        process_started = perf_counter()
        annotated = frame.copy()
        state = "AI DISABLED" if not ai_enabled else "MODEL NOT LOADED"
        confidence: float | None = None
        event: Event | None = None

        if not ai_enabled:
            self._clear_involvement([])
            self.cached_people.clear()
            self.decision.reset()
            for classifier in self.classifiers.values():
                classifier.reset()
            self.last_state, self.last_confidence = "AI DISABLED", None
            self.last_process_fps = 1.0 / max(perf_counter() - process_started, 1e-6)
            cv2.putText(annotated, "AI OFF", (18, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (180, 180, 180), 2, cv2.LINE_AA)
            return annotated, state, confidence, event

        people: list[TrackedPerson] = []
        run_detector = (
            settings.detection_enabled
            and self.detector is not None
            and (self.frame_index % 4 == 0 or not self.cached_people)
        )
        if run_detector:
            try:
                people = self._detect_people(annotated, tracking_enabled, settings)
            except Exception as error:
                self.detector = None
                self.status("detector", f"MODEL ERROR — {error}")
        elif self.cached_people:
            people = copy.deepcopy(self.cached_people)

        run_pose = (
            settings.pose_enabled
            and pose_enabled
            and self.pose_model is not None
            and (self.frame_index == 1 or self.frame_index % 8 == 0)
        )
        if run_pose and people:
            try:
                self._attach_pose(frame, people, annotated, settings)
            except Exception as error:
                self.pose_model = None
                self.status("pose", f"MODEL ERROR — {error}")

        # Keep the latest detector/pose result so expensive YOLO passes are
        # actually decimated. The temporal classifier still receives every
        # analyzed frame.
        if people:
            self.cached_people = copy.deepcopy(people)

        pair_ids = self.interactions.update(people)
        model_key = settings.violence_model if settings.violence_model != "enhanced" else "fdsc_mc3"
        model = self._selected_model(model_key)
        if model is not None and model.ready:
            try:
                inference_started = perf_counter()
                if model_key in {"mc3", "fdsc_mc3"}:
                    # MC3 was trained and validated on full-scene temporal clips.
                    # Do not crop the scene to individual people: that removes the
                    # interaction context that the verified checkpoint relies on.
                    prediction = model.add_frame(frame)
                    if prediction is None:
                        state, confidence = self.last_state, self.last_confidence
                    else:
                        state, confidence = prediction
                        self.last_diagnostics.append(
                            {
                                "frame": self.frame_index,
                                "scope": "scene",
                                "state": state,
                                "fight_probability": confidence,
                                "clip_length": model.CLIP_LENGTH,
                                "inference_stride": model.INFERENCE_STRIDE,
                            }
                        )
                        # Spontim/MC3 is a whole-scene temporal classifier.
                        # Its verified decision must not be blocked by the
                        # optional person-interaction heuristic: that heuristic
                        # can miss valid confrontations because people may be
                        # separated, partially occluded, or tracked imperfectly.
                        # The MC3/Spontim classifier evaluates the whole scene.
                        # Do not gate its event creation on detector/pair availability;
                        # those auxiliary signals can temporarily miss people while
                        # the temporal classifier is still correctly detecting the event.
                        event = self.decision.update(state, confidence)
                        self.last_state, self.last_confidence = state, confidence
                else:
                    self._update_person_clips(frame, people, model)
                    state, confidence = self._aggregate_person_predictions(people)
                    # Consume every temporal prediction. The previous implementation
                    # only updated the stability gate when values changed, so three
                    # identical predictions could never fill the gate.
                    event = self.decision.update(state, confidence)
                    self.last_state, self.last_confidence = state, confidence
                self._apply_involvement(people, pair_ids, state, confidence)
                self.last_inference_ms = (perf_counter() - inference_started) * 1000.0
            except Exception as error:
                self.status("fight", f"MODEL ERROR — {error}")
                state, confidence = "MODEL ERROR", None
                self.last_state, self.last_confidence = state, confidence
        else:
            state, confidence = "MODEL NOT LOADED", None
            self._clear_involvement(people)

        self._draw_people(annotated, people)
        self._draw_status(annotated, state, confidence, model_key)
        self.last_process_fps = 1.0 / max(perf_counter() - process_started, 1e-6)
        return annotated, state, confidence, event

    def render_cached(
        self,
        frame: np.ndarray,
        state: str | None = None,
        confidence: float | None = None,
    ) -> np.ndarray:
        """Render the latest detector/pose state onto a fresh live frame."""
        annotated = frame.copy()
        people = copy.deepcopy(self.cached_people)
        self._draw_people(annotated, people)
        self._draw_status(
            annotated,
            state or self.last_state,
            confidence if confidence is not None else self.last_confidence,
            self.settings.violence_model,
        )
        return annotated

    def _selected_model(self, key: str):
        if key == "enhanced":
            return None
        return self.classifiers.get(key)

    def _update_person_clips(
        self,
        frame: np.ndarray,
        people: list[TrackedPerson],
        model: VideoClassifier,
    ) -> None:
        active_ids = {person.track_id for person in people}
        for track_id in list(self.person_buffers):
            if track_id not in active_ids:
                self.person_buffers.pop(track_id, None)
                self.person_frame_counts.pop(track_id, None)
                self.person_scores.pop(track_id, None)

        for person in people:
            roi = self._person_roi(frame, person.bbox)
            if roi is None:
                continue
            buffer = self.person_buffers.setdefault(person.track_id, deque(maxlen=model.CLIP_LENGTH))
            buffer.append(roi)
            count = self.person_frame_counts.get(person.track_id, 0) + 1
            self.person_frame_counts[person.track_id] = count

            if len(buffer) == model.CLIP_LENGTH and count % model.INFERENCE_STRIDE == 0:
                state, confidence = model.classify_clip(list(buffer))
                self.person_scores[person.track_id] = (state, confidence)
                self.last_diagnostics.append(
                    {
                        "frame": self.frame_index,
                        "person_id": person.display_id,
                        "track_id": person.track_id,
                        "state": state,
                        "fight_probability": confidence,
                        "roi_width": int(roi.shape[1]),
                        "roi_height": int(roi.shape[0]),
                        "buffer_length": len(buffer),
                    }
                )

            if person.track_id in self.person_scores:
                person_state, person_confidence = self.person_scores[person.track_id]
                person.violence_confidence = person_confidence
                person.involved = person_state in {"FIGHT DETECTED", "POSSIBLE ALTERCATION"} and person_confidence >= self.settings.confidence_threshold

    @staticmethod
    def _person_roi(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray | None:
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        bw, bh = max(1, x2 - x1), max(1, y2 - y1)
        expand_x, expand_y = int(bw * 0.35), int(bh * 0.30)
        left, top = max(0, x1 - expand_x), max(0, y1 - expand_y)
        right, bottom = min(width, x2 + expand_x), min(height, y2 + expand_y)
        if right <= left or bottom <= top:
            return None
        return frame[top:bottom, left:right].copy()

    def _aggregate_person_predictions(self, people: list[TrackedPerson]) -> tuple[str, float | None]:
        predictions = [
            self.person_scores[person.track_id]
            for person in people
            if person.track_id in self.person_scores
        ]
        if not predictions:
            # No visible people means there is no current person-level evidence.
            return "NORMAL", None

        fight = [confidence for state, confidence in predictions if state == "FIGHT DETECTED"]
        possible = [confidence for state, confidence in predictions if state == "POSSIBLE ALTERCATION"]
        if fight:
            return "FIGHT DETECTED", max(fight)
        if possible:
            return "POSSIBLE ALTERCATION", max(possible)
        return "NORMAL", max(confidence for _, confidence in predictions)


    def _detect_people(self, annotated: np.ndarray, tracking_enabled: bool, settings: AppSettings) -> list[TrackedPerson]:
        if tracking_enabled:
            results = self.detector.track(
                annotated,
                persist=True,
                tracker="bytetrack.yaml",
                classes=[0],
                conf=PERSON_DETECTION_CONFIDENCE,
                device=str(self.device),
                verbose=False,
            )
        else:
            results = self.detector.predict(
                annotated,
                classes=[0],
                conf=PERSON_DETECTION_CONFIDENCE,
                device=str(self.device),
                verbose=False,
            )
        if not results or results[0].boxes is None:
            return []

        boxes = results[0].boxes
        xyxy = boxes.xyxy.detach().cpu().numpy()
        confs = boxes.conf.detach().cpu().numpy() if boxes.conf is not None else np.ones(len(xyxy))

        has_tracker_ids = boxes.id is not None and tracking_enabled
        if has_tracker_ids:
            ids = boxes.id.detach().cpu().numpy().astype(int).tolist()
            self.fallback_tracks.clear()
        else:
            ids = self._assign_fallback_track_ids(xyxy)

        people = []
        used_display_ids: set[int] = set()
        for raw_box, raw_conf, raw_id in zip(xyxy, confs, ids):
            x1, y1, x2, y2 = (int(v) for v in raw_box)
            track_id = int(raw_id)
            display_id = self._stable_display_id(
                track_id,
                (x1, y1, x2, y2),
                used_display_ids,
            )
            used_display_ids.add(display_id)
            person = TrackedPerson(
                track_id=track_id,
                display_id=display_id,
                bbox=(x1, y1, x2, y2),
                detection_confidence=float(raw_conf),
                center=((x1 + x2) / 2.0, (y1 + y2) / 2.0),
            )
            people.append(person)
        return people

    @staticmethod
    def _bbox_iou(
        left: tuple[int, int, int, int],
        right: tuple[int, int, int, int],
    ) -> float:
        lx1, ly1, lx2, ly2 = left
        rx1, ry1, rx2, ry2 = right
        ix1, iy1 = max(lx1, rx1), max(ly1, ry1)
        ix2, iy2 = min(lx2, rx2), min(ly2, ry2)
        iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
        intersection = iw * ih
        if intersection <= 0:
            return 0.0
        left_area = max(1, lx2 - lx1) * max(1, ly2 - ly1)
        right_area = max(1, rx2 - rx1) * max(1, ry2 - ry1)
        return intersection / float(left_area + right_area - intersection)

    def _stable_display_id(
        self,
        track_id: int,
        bbox: tuple[int, int, int, int],
        used_display_ids: set[int],
    ) -> int:
        """Keep operator-facing IDs stable when ByteTrack briefly re-issues an ID."""
        if track_id in self.display_ids:
            display_id = self.display_ids[track_id]
            self.display_track_memory[display_id] = (bbox, self.frame_index)
            return display_id

        best_display: int | None = None
        best_score = 0.0
        bx1, by1, bx2, by2 = bbox
        bcx, bcy = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0
        bh = max(1, by2 - by1)

        for display_id, (previous_bbox, last_seen) in self.display_track_memory.items():
            if display_id in used_display_ids:
                continue
            if self.frame_index - last_seen > 12:
                continue
            px1, py1, px2, py2 = previous_bbox
            pcx, pcy = (px1 + px2) / 2.0, (py1 + py2) / 2.0
            ph = max(1, py2 - py1)
            distance = float(np.hypot(bcx - pcx, bcy - pcy))
            distance_limit = max(50.0, max(bh, ph) * 1.25)
            iou = self._bbox_iou(bbox, previous_bbox)
            proximity = max(0.0, 1.0 - distance / distance_limit)
            score = max(iou, proximity * 0.70)
            if distance <= distance_limit and score > best_score:
                best_display = display_id
                best_score = score

        if best_display is None:
            best_display = self.next_display_id
            self.next_display_id += 1

        self.display_ids[track_id] = best_display
        self.display_track_memory[best_display] = (bbox, self.frame_index)
        return best_display

    def _detect_scene_cut(self, frame: np.ndarray) -> bool:
        """Detect abrupt source-video cuts so old tracking/clip state is not reused."""
        small = cv2.resize(frame, (32, 18))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        signature = (
            int(gray.mean()),
            int(gray.std()),
            int(gray[::4, ::4].mean()),
        )

        if self.last_scene_signature is None:
            self.last_scene_signature = signature
            return False

        previous = np.array(self.last_scene_signature, dtype=np.float32)
        current = np.array(signature, dtype=np.float32)
        difference = float(np.linalg.norm(current - previous))
        self.last_scene_signature = signature

        if self.scene_cut_cooldown > 0:
            self.scene_cut_cooldown -= 1
            return False

        if difference >= 28.0:
            self.scene_cut_cooldown = 8
            return True
        return False

    def _reset_tracking_state(self) -> None:
        self.display_ids.clear()
        self.display_track_memory.clear()
        self.next_display_id = 1
        self.fallback_tracks.clear()
        self.next_fallback_track_id = -1
        self.person_buffers.clear()
        self.person_frame_counts.clear()
        self.person_scores.clear()
        self.interactions.pair_history.clear()
        self.decision.reset()
        # A scene cut invalidates the temporal clip as well as tracking state.
        # Never allow frames from the previous scene to contribute to the next
        # violence prediction.
        for classifier in self.classifiers.values():
            classifier.reset()
        self.last_involved_ids.clear()
        self.cached_people.clear()

    def _assign_fallback_track_ids(self, boxes: np.ndarray) -> list[int]:
        """Keep temporal ROI IDs stable when ByteTrack is disabled/unavailable."""
        current: list[tuple[int, float, float, float]] = []
        used_previous: set[int] = set()

        for raw_box in boxes:
            x1, y1, x2, y2 = (float(v) for v in raw_box)
            center_x = (x1 + x2) / 2.0
            center_y = (y1 + y2) / 2.0
            height = max(1.0, y2 - y1)

            best_id: int | None = None
            best_distance = float("inf")
            for track_id, (px, py, previous_height) in self.fallback_tracks.items():
                if track_id in used_previous:
                    continue
                distance = float(np.hypot(center_x - px, center_y - py))
                limit = max(45.0, max(height, previous_height) * 1.25)
                if distance <= limit and distance < best_distance:
                    best_id = track_id
                    best_distance = distance

            if best_id is None:
                best_id = self.next_fallback_track_id
                self.next_fallback_track_id -= 1

            used_previous.add(best_id)
            current.append((best_id, center_x, center_y, height))

        self.fallback_tracks = {
            track_id: (center_x, center_y, height)
            for track_id, center_x, center_y, height in current
        }
        return [track_id for track_id, *_ in current]


    def _attach_pose(
        self,
        frame: np.ndarray,
        people: list[TrackedPerson],
        annotated: np.ndarray,
        settings: AppSettings,
    ) -> None:
        results = self.pose_model.predict(
            frame,
            conf=POSE_DETECTION_CONFIDENCE,
            classes=[0],
            device=str(self.device),
            verbose=False,
        )
        if not results or results[0].keypoints is None or not people:
            return

        result = results[0]
        keypoints = result.keypoints
        points = keypoints.xy.detach().cpu().numpy()
        confidences = (
            keypoints.conf.detach().cpu().numpy()
            if keypoints.conf is not None
            else np.ones(points.shape[:2], dtype=np.float32)
        )

        candidates: list[tuple[float, int, int, float]] = []
        for pose_index, person_points in enumerate(points):
            pose_conf = confidences[pose_index]
            valid = pose_conf >= 0.50
            if int(np.count_nonzero(valid)) < 5:
                continue

            valid_points = person_points[valid]
            px1 = int(np.min(valid_points[:, 0]))
            py1 = int(np.min(valid_points[:, 1]))
            px2 = int(np.max(valid_points[:, 0]))
            py2 = int(np.max(valid_points[:, 1]))
            pose_box = (px1, py1, px2, py2)
            pose_center = ((px1 + px2) / 2.0, (py1 + py2) / 2.0)

            for person_index, person in enumerate(people):
                iou = self._bbox_iou(person.bbox, pose_box)
                distance = float(
                    np.hypot(
                        person.center[0] - pose_center[0],
                        person.center[1] - pose_center[1],
                    )
                )
                person_height = max(1, person.bbox[3] - person.bbox[1])
                distance_limit = max(45.0, person_height * 0.75)

                if iou >= 0.10:
                    score = 1.0 + iou
                elif distance <= distance_limit:
                    score = max(0.0, 0.55 - distance / distance_limit * 0.55)
                else:
                    continue

                candidates.append(
                    (-score, pose_index, person_index, float(np.mean(pose_conf[valid])))
                )

        assigned_people: set[int] = set()
        assigned_poses: set[int] = set()
        for _, pose_index, person_index, pose_confidence in sorted(candidates):
            if pose_index in assigned_poses or person_index in assigned_people:
                continue
            selected_points = points[pose_index].copy()
            selected_conf = confidences[pose_index]
            selected_points[selected_conf < 0.50] = -1
            people[person_index].keypoints = selected_points
            people[person_index].pose_confidence = pose_confidence
            assigned_people.add(person_index)
            assigned_poses.add(pose_index)


    def _clear_involvement(self, people: list[TrackedPerson]) -> None:
        self.last_involved_ids.clear()
        for person in people:
            person.involved = False
            person.violence_confidence = None


    def _apply_involvement(
        self,
        people: list[TrackedPerson],
        pair_ids: list[tuple[int, int]],
        state: str,
        confidence: float | None,
    ) -> None:
        self._clear_involvement(people)
        if confidence is None or confidence < self.settings.confidence_threshold:
            return

        # Person-specific ROI scores are used for models that operate on person
        # crops. MC3 is scene-level, so attribution is deliberately conservative:
        # only people participating in a tracked interaction are highlighted.
        involved_ids = {
            person.track_id
            for person in people
            if (
                person.track_id in self.person_scores
                and self.person_scores[person.track_id][0]
                in {"FIGHT DETECTED", "POSSIBLE ALTERCATION"}
                and self.person_scores[person.track_id][1]
                >= self.settings.confidence_threshold
            )
        }

        # For scene-level MC3/Spontim, the fight confidence belongs to the
        # whole scene, not to an individual crop. When the scene classifier says
        # FIGHT DETECTED, highlight the currently detected people so the operator
        # can immediately see which boxes are part of the detected scene event.
        # Most importantly, use the exact same scene confidence for those boxes
        # that is shown in the main fight-detection HUD; never substitute the
        # YOLO person-detection confidence (which caused misleading values such
        # as 89% to appear repeatedly).
        if state in {"FIGHT DETECTED", "POSSIBLE ALTERCATION"}:
            if self.settings.violence_model in {"mc3", "fdsc_mc3"}:
                involved_ids.update(person.track_id for person in people)
            elif not involved_ids and pair_ids:
                involved_ids.update(track_id for pair in pair_ids for track_id in pair)
            else:
                for left, right in pair_ids:
                    if left in involved_ids or right in involved_ids:
                        involved_ids.update((left, right))

        self.last_involved_ids = involved_ids
        for person in people:
            person.involved = person.track_id in involved_ids
            if person.involved:
                if self.settings.violence_model in {"mc3", "fdsc_mc3"}:
                    # Scene-level Spontim confidence: exactly the same value
                    # reported by the fight classifier/UI.
                    person.violence_confidence = confidence
                else:
                    score = self.person_scores.get(person.track_id)
                    person.violence_confidence = score[1] if score else confidence
            else:
                person.violence_confidence = None


    def _draw_people(self, annotated: np.ndarray, people: list[TrackedPerson]) -> None:
        for person in people:
            x1, y1, x2, y2 = person.bbox
            if person.involved and person.violence_confidence is not None:
                color = (74, 74, 223) if person.violence_confidence >= 0.75 else (0, 191, 255)
            else:
                color = (95, 194, 132)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)

            label = f"PERSON #{person.display_id}"
            if person.involved and person.violence_confidence is not None:
                label += f"  {person.violence_confidence:.0%} VIOLENCE"
            else:
                # Do not display the YOLO person-detection confidence as if it
                # were a violence/fight percentage.
                label += "  PERSON"

            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
            top = max(0, y1 - th - 10)
            cv2.rectangle(annotated, (x1, top), (min(annotated.shape[1] - 1, x1 + tw + 10), y1), color, -1)
            cv2.putText(annotated, label, (x1 + 5, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)

            if person.keypoints is not None:
                self._draw_skeleton(annotated, person.keypoints, color)

    def _draw_skeleton(
        self,
        annotated: np.ndarray,
        points: np.ndarray,
        color: tuple[int, int, int],
    ) -> None:
        for start, end in SKELETON_EDGES:
            if start >= len(points) or end >= len(points):
                continue
            a, b = points[start], points[end]
            if (
                a[0] <= 0 or a[1] <= 0
                or b[0] <= 0 or b[1] <= 0
                or np.any(np.abs(a) > 10000)
                or np.any(np.abs(b) > 10000)
            ):
                continue
            cv2.line(
                annotated,
                tuple(int(v) for v in a),
                tuple(int(v) for v in b),
                color,
                2,
                cv2.LINE_AA,
            )

        for point in points[:17]:
            if point[0] > 0 and point[1] > 0:
                cv2.circle(
                    annotated,
                    tuple(int(v) for v in point),
                    3,
                    (242, 238, 225),
                    -1,
                    cv2.LINE_AA,
                )


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
