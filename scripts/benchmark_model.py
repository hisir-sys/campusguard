from __future__ import annotations

import argparse
from collections import Counter, deque
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np
import torch

from campusguard.model_registry import MODEL_PROFILES, VideoClassifier
from campusguard.settings import AppSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a CampusGuard temporal violence model without YOLO, tracking, or pose."
    )
    parser.add_argument("video", type=Path, help="Input video path.")
    parser.add_argument(
        "--model",
        choices=("mc3", "fdsc_mc3", "x3d"),
        default="mc3",
        help="Temporal violence model to validate.",
    )
    parser.add_argument(
        "--device",
        choices=("auto", "cpu", "cuda"),
        default="cpu",
        help="Inference device.",
    )
    parser.add_argument(
        "--stride",
        type=int,
        default=8,
        help="Run one prediction every N source frames after the first complete clip.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=0,
        help="Maximum source frames to read. 0 reads the entire video.",
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Print every temporal prediction.",
    )
    return parser


def select_device(requested: str) -> torch.device:
    if requested == "cuda" and not torch.cuda.is_available():
        print("[device] CUDA unavailable — using CPU")
        return torch.device("cpu")
    if requested == "cuda" or (requested == "auto" and torch.cuda.is_available()):
        try:
            print(f"[device] CUDA available — {torch.cuda.get_device_name(0)}")
        except Exception:
            print("[device] CUDA available")
        return torch.device("cuda:0")
    print("[device] CPU selected")
    return torch.device("cpu")


def main() -> int:
    args = build_parser().parse_args()

    if not args.video.is_file():
        print(f"ERROR: video not found: {args.video}")
        return 2
    if args.stride < 1:
        print("ERROR: --stride must be at least 1")
        return 2

    settings = AppSettings.from_dict(
        {
            "violence_model": args.model,
            "device": args.device,
        }
    )
    device = select_device(args.device)

    def report_status(component: str, message: str) -> None:
        print(f"[{component}] {message}")

    profile = MODEL_PROFILES[args.model]
    model_paths = {
        "mc3": settings.fight_model_path,
        "fdsc_mc3": settings.fdsc_mc3_model_path,
        "x3d": settings.x3d_model_path,
    }

    print("CampusGuard isolated temporal-model validation")
    print(f"Video : {args.video}")
    print(f"Model : {profile.name}")
    print(f"Device: {device}")
    print("Scope : full scene — no detector, tracking, or pose")
    print()

    classifier = VideoClassifier(
        profile,
        model_paths[args.model],
        device,
        settings.confidence_threshold,
        report_status,
        fight_class_override=(
            settings.fight_positive_class if args.model == "mc3" else None
        ),
    )

    if not classifier.ready:
        print()
        print("RESULT: classifier failed to load.")
        return 4

    capture = cv2.VideoCapture(str(args.video))
    if not capture.isOpened():
        print(f"ERROR: could not open video: {args.video}")
        return 3

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    limit = args.max_frames if args.max_frames > 0 else None
    buffer: deque[np.ndarray] = deque(maxlen=classifier.CLIP_LENGTH)
    predictions: list[tuple[int, str, float]] = []
    states: Counter[str] = Counter()
    frame_number = 0
    inference_count = 0
    started = perf_counter()

    try:
        while limit is None or frame_number < limit:
            ok, frame = capture.read()
            if not ok or frame is None or frame.size == 0:
                break

            frame_number += 1
            buffer.append(frame)

            if (
                len(buffer) == classifier.CLIP_LENGTH
                and (frame_number - classifier.CLIP_LENGTH) % args.stride == 0
            ):
                state, confidence = classifier.classify_clip(list(buffer))
                inference_count += 1
                states[state] += 1
                predictions.append((frame_number, state, confidence))

                if args.diagnostics:
                    print(
                        f"[scene] frame={frame_number} "
                        f"fight={confidence:.3f} "
                        f"state={state} "
                        f"clip={classifier.CLIP_LENGTH}"
                    )
    finally:
        capture.release()

    elapsed = perf_counter() - started
    probabilities = [confidence for _, _, confidence in predictions]

    print()
    print("=== ISOLATED MODEL RESULT ===")
    print(f"Frames read       : {frame_number}")
    print(f"Source FPS        : {fps:.2f}")
    print(f"Video frames      : {total_frames}")
    print(f"Temporal clips    : {inference_count}")
    print(f"Elapsed            : {elapsed:.2f}s")
    print(f"Model FPS          : {inference_count / max(elapsed, 1e-6):.2f}")
    print(f"Classifier ready   : {classifier.ready}")
    print(f"Fight class        : {classifier.fight_class}")
    print(f"Fight label        : {classifier.semantic_label}")

    if probabilities:
        print(f"Fight probability  : min={min(probabilities):.3f} "
              f"max={max(probabilities):.3f} "
              f"mean={float(np.mean(probabilities)):.3f}")
        print("States:")
        for state, count in states.most_common():
            print(f"  {state}: {count}")
        peak_frame, peak_state, peak_probability = max(
            predictions, key=lambda item: item[2]
        )
        print(
            f"Peak prediction    : frame={peak_frame} "
            f"fight={peak_probability:.3f} state={peak_state}"
        )
    else:
        print("No complete temporal clips were produced.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
