# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Callable
import weakref

import cv2
import numpy as np
import queue
import time
import threading
import torch
from torch import nn

from campusguard.model_manifest import MODEL_MANIFESTS
from campusguard.model_paths import with_aliases
from campusguard.model_adapters import get_model_input_adapter
from campusguard.storage import application_data_dir

Status = Callable[[str, str], None]

# Share immutable model weights across per-camera classifier state. Each camera
# still owns its own temporal frames, probabilities, and decision history.
MODEL_CACHE_LOCK = threading.RLock()
_MODEL_INFERENCE_LOCKS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()

def model_inference_lock(model) -> threading.RLock:
    """Return a lock scoped to one shared model, not to the whole AI stack."""
    with MODEL_CACHE_LOCK:
        lock = _MODEL_INFERENCE_LOCKS.get(model)
        if lock is None:
            lock = threading.RLock()
            _MODEL_INFERENCE_LOCKS[model] = lock
        return lock

# Weak references allow unused model variants to be released when the last
# camera stops using them, instead of pinning every GPU model until app exit.
_SHARED_VIDEO_MODELS: dict[
    tuple[str, str, str, int | None],
    tuple[weakref.ReferenceType[nn.Module | torch.jit.ScriptModule], int],
] = {}

@dataclass(frozen=True)
class ModelProfile:
    key: str
    name: str
    description: str
    architecture: str
    path_setting: str
    class_labels: tuple[str, ...]
    fight_class: int | None
    preprocessing: str
    semantic_status: str
    source_note: str

    @property
    def class_count(self) -> int:
        return len(self.class_labels)

    @property
    def semantic_verified(self) -> bool:
        return self.fight_class is not None and self.semantic_status == "verified"


MODEL_PROFILES: dict[str, ModelProfile] = {
    key: ModelProfile(
        key=manifest.key,
        name=manifest.name,
        description=manifest.description,
        architecture=manifest.architecture,
        path_setting=manifest.path_setting,
        class_labels=manifest.class_labels,
        fight_class=manifest.fight_class,
        preprocessing=manifest.preprocessing,
        semantic_status=manifest.semantic_status,
        source_note=manifest.source_note,
    )
    for key, manifest in MODEL_MANIFESTS.items()
}

class _InferenceWorker:
    """One background thread runs the newer models' checks for every camera.

    A camera only raises its hand ("I have enough new frames"); the worker then takes the camera that has
    gone longest without a check, copies that camera's NEWEST clip and runs it. So the camera thread never
    waits for the model, a clip is never stale, and under load the cameras that were checked least recently
    go first."""

    _instance: "_InferenceWorker | None" = None
    _guard = threading.Lock()

    def __init__(self) -> None:
        self.cond = threading.Condition()
        self.wanting: set = set()
        threading.Thread(target=self._run, name="fight-model-worker", daemon=True).start()

    @classmethod
    def get(cls) -> "_InferenceWorker":
        with cls._guard:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def request(self, classifier: "VideoClassifier") -> None:
        with self.cond:
            self.wanting.add(classifier)
            self.cond.notify()

    def _run(self) -> None:
        while True:
            with self.cond:
                while not self.wanting:
                    self.cond.wait()
                chosen = min(
                    self.wanting,
                    key=lambda c: (c._covered_end if c._covered_end is not None else float("-inf"), c._want_since),
                )
                self.wanting.discard(chosen)
            try:
                chosen._run_check()
            except Exception as error:               # never kill the worker
                chosen.last_error = str(error)
            finally:
                chosen._pending = False


class VideoClassifier:
    CLIP_LENGTH = 16
    INFERENCE_STRIDE = 8
    INPUT_SIZE = (112, 112)
    # The 16 frames of one check should cover about one second of real time (a camera at 15 fps).
    # If the analyser is too busy to keep up, the same 16 frames stretch over many seconds, ordinary
    # movement then looks like fast fighting and the model reports "fight" on calm scenes (measured
    # on a classroom clip: 4 of 35 checks above 65% at 15 fps, 13 of 17 at 7.5 fps, 3 of 3 at 1.9 fps).
    # A check whose frames span more than this is skipped and reported as "analyser behind".
    MAX_CLIP_SECONDS = 1.6

    def __init__(
        self,
        profile: ModelProfile,
        path: str,
        device: torch.device,
        threshold: float,
        status: Status,
        fight_class_override: int | None = None,
    ) -> None:
        self.profile, self.path, self.device = profile, path, device
        self.adapter = get_model_input_adapter(profile.key)
        # Clip geometry comes from the model's own adapter. The old model keeps its legacy values
        # (16 frames, a check every 8 frames, 1.6 s); the newer ones look at longer stretches of video.
        self.span = self.adapter.span_frames
        self.grid_interval = (1.0 / self.adapter.time_grid_fps) if self.adapter.time_grid_fps else None
        self._last_grid_time: float | None = None
        self.since_check = 0
        self._token = 0
        self._pending = False                 # a check is requested or running
        self._want_since = 0.0
        self._covered_end: float | None = None
        self._first_grid_time: float | None = None
        self._windows: list[tuple[float, float]] = []
        self._buf_lock = threading.Lock()
        self._next_coverage = 0.0
        self._result: tuple[str, float] | None = None
        self.coverage_now = 1.0
        self.checks_done = 0
        self.max_probability = 0.0
        self.last_check_seconds = 0.0
        self.last_error = ""
        self.INFERENCE_STRIDE = self.adapter.inference_stride
        self.CLIP_LENGTH = self.adapter.clip_length
        self.MAX_CLIP_SECONDS = self.span / 15.0 * 1.5 if self.adapter.frame_step > 1 or self.adapter.clip_length != 16 else type(self).MAX_CLIP_SECONDS
        self.threshold, self.status = threshold, status
        self.fight_class: int | None = (
            fight_class_override
            if fight_class_override is not None
            else profile.fight_class
        )
        self.model: nn.Module | torch.jit.ScriptModule | None = None
        self.class_count = 0
        self.frames: list[np.ndarray] = []
        self.frame_times: list[float] = []
        self.frame_count = 0
        self.skipped_slow = 0
        self.behind = False
        self.last_probability = 0.0
        self.last_state = "MODEL NOT LOADED"
        self._load()

    @property
    def ready(self) -> bool:
        return self.model is not None

    @property
    def semantic_ready(self) -> bool:
        """True only when the checkpoint is loaded and its fight class is verified."""
        return self.ready and self.fight_class is not None

    @property
    def semantic_label(self) -> str:
        if self.fight_class is None:
            return "UNVERIFIED"
        if 0 <= self.fight_class < len(self.profile.class_labels):
            return self.profile.class_labels[self.fight_class]
        return f"class_{self.fight_class}"

    def _resolved_path(self) -> Path:
        raw_path = Path(self.path).expanduser()
        path = raw_path
        if not raw_path.is_absolute():
            # Resolve checkpoints independently of PowerShell/shortcut working
            # directory. PyInstaller extracts bundled assets under _MEIPASS.
            bundle_root = getattr(sys, "_MEIPASS", None)
            data_root = application_data_dir()
            for candidate in with_aliases(raw_path):
                bundled_path = Path(bundle_root) / candidate if bundle_root else None
                project_path = Path(__file__).resolve().parents[1] / candidate
                data_paths = (data_root / candidate, data_root / "models" / candidate.name)
                if bundled_path is not None and bundled_path.is_file():
                    path = bundled_path
                    break
                if project_path.is_file():
                    path = project_path
                    break
                data_path = next((item for item in data_paths if item.is_file()), None)
                if data_path is not None:
                    path = data_path
                    break
        return path

    def _load(self) -> None:
        # Resolve aliases before caching, so relative and absolute references to
        # the same checkpoint reuse the same model. File changes invalidate cache.
        path = self._resolved_path()
        try:
            modified_ns = path.stat().st_mtime_ns
        except OSError:
            modified_ns = None
        cache_key = (
            self.profile.architecture,
            str(path.resolve()),
            str(self.device),
            modified_ns,
        )
        with MODEL_CACHE_LOCK:
            cached = _SHARED_VIDEO_MODELS.get(cache_key)
            cached_model = cached[0]() if cached is not None else None
            if cached_model is not None:
                self.model, self.class_count = cached_model, cached[1]
                self.last_state = "NORMAL"
                self.status(
                    self.profile.key,
                    f"READY — {self.profile.name} (shared model instance)",
                )
                return
            self._load_uncached(path)
            if self.model is not None:
                _SHARED_VIDEO_MODELS[cache_key] = (
                    weakref.ref(self.model),
                    self.class_count,
                )

    def _load_uncached(self, path: Path | None = None) -> None:
        path = path or self._resolved_path()
        if not self.path.strip() or not path.is_file():
            self.status(self.profile.key, f"MODEL NOT LOADED — file not found: {path}")
            return
        try:
            model = self._build_architecture(self.profile.architecture)

            checkpoint = self._load_checkpoint(path)
            state = self._extract_state_dict(checkpoint)
            cleaned = self._clean_state_dict(state)

            classifier_key = self._find_classifier_key(cleaned)
            if classifier_key is None:
                raise ValueError("Could not locate a classifier weight in checkpoint.")
            classifier_weight = cleaned[classifier_key]
            if getattr(classifier_weight, "ndim", 0) != 2:
                raise ValueError(f"Classifier weight '{classifier_key}' is not a 2D tensor.")

            self.class_count = int(classifier_weight.shape[0])
            if self.class_count not in (2, 3):
                raise ValueError(f"Checkpoint has {self.class_count} output classes; expected 2 or 3.")

            if self.class_count != self.profile.class_count:
                raise ValueError(
                    f"Checkpoint has {self.class_count} classes, but the manifest expects {self.profile.class_count}."
                )
            if self.fight_class is not None and not (0 <= self.fight_class < self.class_count):
                raise ValueError(
                    f"Manifest fight class {self.fight_class} is outside the checkpoint's {self.class_count} classes."
                )

            if self.profile.architecture == "mc3":
                self._resize_classifier(model, self.class_count, classifier_key)
            missing, unexpected = model.load_state_dict(cleaned, strict=False)
            if missing or unexpected:
                missing_text = ", ".join(missing[:8])
                unexpected_text = ", ".join(unexpected[:8])
                details = []
                if missing_text:
                    details.append(f"missing={missing_text}")
                if unexpected_text:
                    details.append(f"unexpected={unexpected_text}")
                raise ValueError("Checkpoint architecture mismatch (" + "; ".join(details) + ").")
            model.to(self.device)
            model.eval()
            self.model = model
            self.last_state = "NORMAL"
            semantic = f"fight class={self.fight_class}" if self.fight_class is not None else "fight class=UNVERIFIED"
            self.status(self.profile.key, f"READY — {self.profile.name}, {self.class_count} classes ({path.name}); {semantic}")
            if self.fight_class is None:
                self.status(self.profile.key, "SEMANTIC MAPPING NOT VERIFIED — model will not produce violence decisions.")
        except Exception as error:
            self.model = None
            self.last_state = "MODEL NOT LOADED"
            self.status(self.profile.key, f"MODEL NOT LOADED — {error}")


    @staticmethod
    def _build_architecture(architecture: str) -> nn.Module:
        """An empty network with a 2-class head, ready to receive a checkpoint."""
        if architecture == "mc3":
            from torchvision.models.video import mc3_18
            return mc3_18(weights=None)
        if architecture == "r2plus1d":
            from torchvision.models.video import r2plus1d_18
            model = r2plus1d_18(weights=None)
            model.fc = nn.Sequential(nn.Dropout(0.0), nn.Linear(model.fc.in_features, 2))
            return model
        if architecture == "slowfast":
            try:
                from pytorchvideo.models import hub
            except ImportError as error:
                raise ValueError(
                    "this model needs the 'pytorchvideo' package (pip install pytorchvideo)"
                ) from error
            model = hub.slowfast_r50(pretrained=False)
            model.blocks[-1].proj = nn.Sequential(nn.Dropout(0.0), nn.Linear(model.blocks[-1].proj.in_features, 2))
            return model
        raise ValueError(f"Unsupported architecture: {architecture}")

    @staticmethod
    def _load_checkpoint(path: Path):
        """Load the trusted Spontim checkpoint with PyTorch's safe unpickler."""
        return torch.load(path, map_location="cpu", weights_only=True)

    @staticmethod
    def _extract_state_dict(checkpoint) -> dict:
        if not isinstance(checkpoint, dict):
            raise ValueError("Checkpoint does not contain a state dictionary.")

        for key in ("state_dict", "model_state_dict", "model"):
            candidate = checkpoint.get(key)
            if isinstance(candidate, dict):
                return candidate

        # A plain state_dict is itself a mapping of parameter names to tensors.
        if checkpoint and all(isinstance(value, torch.Tensor) for value in checkpoint.values()):
            return checkpoint

        raise ValueError("Checkpoint does not contain a usable state dictionary.")

    @staticmethod
    def _clean_state_dict(state: dict) -> dict[str, torch.Tensor]:
        cleaned: dict[str, torch.Tensor] = {}
        for raw_key, value in state.items():
            if not isinstance(value, torch.Tensor):
                continue
            key = str(raw_key)
            # Some exporters stack wrappers such as model.module.model.
            changed = True
            while changed:
                changed = False
                for prefix in ("module.", "model.", "state_dict.", "backbone."):
                    if key.startswith(prefix):
                        key = key[len(prefix):]
                        changed = True
            cleaned[key] = value

        if not cleaned:
            raise ValueError("Checkpoint state dictionary contains no tensor parameters.")
        return cleaned

    @staticmethod
    def _find_classifier_key(state: dict[str, torch.Tensor]) -> str | None:
        if "fc.weight" in state and getattr(state["fc.weight"], "ndim", 0) == 2:
            return "fc.weight"
        candidates = [key for key, value in state.items() if key.endswith(".weight") and getattr(value, "ndim", 0) == 2]
        return candidates[-1] if candidates else None

    @staticmethod
    def _resize_classifier(model: nn.Module, class_count: int, classifier_key: str) -> None:
        if hasattr(model, "fc") and isinstance(model.fc, nn.Linear):
            model.fc = nn.Linear(model.fc.in_features, class_count)
            return
        raise ValueError("Unsupported classifier head for this checkpoint architecture.")

    def reset(self) -> None:
        self.frames.clear()
        self.frame_times.clear()
        self.behind = False
        self.frame_count = 0
        self._last_grid_time = None
        self.since_check = 0
        self._token += 1                       # drops any check still running in the worker
        self._covered_end = None
        self._first_grid_time = None
        self._windows = []
        self._result = None
        self.last_probability = 0.0
        self.last_state = "NORMAL" if self.ready else "MODEL NOT LOADED"

    def update(self, threshold: float) -> None:
        self.threshold = threshold

    def _classify_clip(self, clip: list[np.ndarray] | np.ndarray) -> tuple[str, float]:
        tensor = self.adapter.prepare(clip, self.device)

        with torch.inference_mode():
            # A shared model is read-only, but a lock avoids simultaneous
            # forwards from many camera threads overwhelming accelerator memory.
            with model_inference_lock(self.model):
                logits = self.model(tensor)
            if isinstance(logits, (tuple, list)):
                logits = logits[0]
            probabilities = torch.softmax(logits, dim=1)[0].detach().cpu().numpy()

        if self.fight_class is None:
            raise RuntimeError(
                f"{self.profile.name} has no verified fight-class mapping."
            )

        fight_probability = float(probabilities[self.fight_class])

        if self.class_count == 3:
            other_classes = [
                index for index in range(self.class_count)
                if index != self.fight_class
            ]
            non_fight_probability = float(probabilities[other_classes].sum())

            if fight_probability >= self.threshold:
                state = "FIGHT DETECTED"
            elif (
                fight_probability >= self.threshold * 0.80
                and non_fight_probability < fight_probability
            ):
                state = "POSSIBLE ALTERCATION"
            else:
                state = "NORMAL"
        else:
            if fight_probability >= self.threshold:
                state = "FIGHT DETECTED"
            elif fight_probability >= self.threshold * 0.80:
                state = "POSSIBLE ALTERCATION"
            else:
                state = "NORMAL"

        confidence = fight_probability

        self.last_probability, self.last_state = confidence, state
        return state, confidence

    def add_frame(self, frame: np.ndarray, timestamp: float | None = None) -> tuple[str, float] | None:
        """Keep a legacy/global stream for callers that still need one.

        ``timestamp`` (seconds, any steady clock) lets the classifier refuse a clip whose frames are
        too far apart in time; without it every full clip is classified as before.
        """
        if self.model is None or self.fight_class is None:
            return None
        if self.grid_interval is not None:
            self._append_on_grid(frame, timestamp)
            if len(self.frames) >= self.span and self.since_check >= self.INFERENCE_STRIDE and not self._pending:
                self._pending = True
                self._want_since = time.monotonic()
                self.since_check = 0
                _InferenceWorker.get().request(self)
            self._update_coverage()
            return self._take_result()
        # Keep frames in their original BGR form. The model adapter owns
        # color conversion, resizing, and normalization so every model uses
        # one consistent preprocessing path.
        self.frames.append(self.adapter.shrink(frame))
        self.frame_times.append(float("nan") if timestamp is None else float(timestamp))
        if len(self.frames) > self.span:
            self.frames.pop(0)
            self.frame_times.pop(0)
        self.frame_count += 1
        if len(self.frames) < self.span or self.frame_count % self.INFERENCE_STRIDE:
            return None
        first, last = self.frame_times[0], self.frame_times[-1]
        if first == first and last == last and last - first > self.MAX_CLIP_SECONDS:
            self.skipped_slow += 1
            self.behind = True
            return None
        self.behind = False
        return self._classify_clip(self.frames)

    GAP_RESET_SECONDS = 1.0

    @property
    def paused(self) -> bool:
        """Checks are being skipped (old model's stretched-clip guard). The newer models never pause;
        they report how much of the time they are watching instead (``behind``)."""
        return self.behind and self.grid_interval is None

    def _take_result(self) -> tuple[str, float] | None:
        """The newest finished check, handed over once."""
        result, self._result = self._result, None
        return result

    def diagnostics(self) -> dict:
        return {
            "model": self.profile.key,
            "buffered": len(self.frames),
            "needed": self.span,
            "checks_done": self.checks_done,
            "skipped_stretched": self.skipped_slow,
            "checking_now": self._pending,
            "coverage_pct": round(100 * getattr(self, "coverage_now", 1.0)),
            "last_probability": round(self.last_probability, 3),
            "max_probability": round(self.max_probability, 3),
            "last_check_s": round(self.last_check_seconds, 2),
            "error": self.last_error,
        }

    def _append_on_grid(self, frame: np.ndarray, timestamp: float | None) -> None:
        """Keep one frame per grid step (15 fps), whatever rate the camera or the analyser runs at.

        A long hole in the stream (the camera stalled) starts the clip afresh so the model never sees
        frames glued together across a gap."""
        if timestamp is None:
            timestamp = (self._last_grid_time or 0.0) + (self.grid_interval or 0.0)
        last = self._last_grid_time
        if last is not None and timestamp - last < (self.grid_interval or 0.0) * 0.9:
            return
        small = self.adapter.shrink(frame)
        with self._buf_lock:
            if last is not None and timestamp - last > self.GAP_RESET_SECONDS:
                self.frames.clear()
                self.frame_times.clear()
            self._last_grid_time = timestamp
            if self._first_grid_time is None:
                self._first_grid_time = timestamp
            self.frames.append(small)
            self.frame_times.append(float(timestamp))
            if len(self.frames) > self.span:
                self.frames.pop(0)
                self.frame_times.pop(0)
            self.since_check += 1

    def _run_check(self) -> None:
        """Worker thread: judge this camera's newest clip."""
        with self._buf_lock:
            if len(self.frames) < self.span:
                return
            clip, times, token = list(self.frames), list(self.frame_times), self._token
        if times[-1] - times[0] > self.MAX_CLIP_SECONDS:
            self.skipped_slow += 1
            return
        started = time.perf_counter()
        result = self._classify_clip(clip)
        if token != self._token:                 # camera was reset while this ran
            return
        self._result = result
        self.checks_done += 1
        self.max_probability = max(self.max_probability, result[1])
        self.last_check_seconds = time.perf_counter() - started
        self._covered_end = times[-1]
        self._windows.append((times[0], times[-1]))
        if len(self._windows) > 80:
            del self._windows[:-80]

    COVERAGE_HORIZON_SECONDS = 60.0

    def coverage(self) -> float:
        """Share of the last minute of this camera that some completed check has looked at."""
        last, first = self._last_grid_time, self._first_grid_time
        if last is None or first is None:
            return 1.0
        observed = min(self.COVERAGE_HORIZON_SECONDS, last - first)
        if observed < 10.0:
            return 1.0                            # too early to judge
        horizon = last - observed
        covered, cursor = 0.0, horizon
        for start, end in sorted(self._windows):
            start, end = max(start, cursor), min(end, last)
            if end > start:
                covered += end - start
                cursor = end
        return min(1.0, covered / observed)

    def _update_coverage(self) -> None:
        now = time.monotonic()
        if now >= self._next_coverage:
            self._next_coverage = now + 1.0
            self.coverage_now = self.coverage()
            self.behind = self.coverage_now < 0.9

    def buffer_frame(self, frame: np.ndarray, timestamp: float | None = None) -> None:
        """Feed a frame the heavy analysis skipped. Cheap: no detector, no model."""
        if self.model is not None and self.grid_interval is not None:
            self._append_on_grid(frame, timestamp)
            if len(self.frames) >= self.span and self.since_check >= self.INFERENCE_STRIDE and not self._pending:
                self._pending = True
                self._want_since = time.monotonic()
                self.since_check = 0
                _InferenceWorker.get().request(self)

    def classify_clip(self, frames: list[np.ndarray]) -> tuple[str, float]:
        """Classify one temporal ROI clip for person-specific attribution."""
        if self.model is None or self.fight_class is None:
            raise ValueError("A loaded classifier with a verified fight-class mapping is required.")
        if len(frames) < self.CLIP_LENGTH:
            raise ValueError("A loaded classifier and 16-frame clip are required.")
        # The model adapter owns color conversion, resizing, and normalization.
        return self._classify_clip(frames[-self.CLIP_LENGTH:])
