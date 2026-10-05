from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from time import perf_counter

import cv2

from campusguard.ai_pipeline import VisionPipeline
from campusguard.settings import AppSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the complete CampusGuard vision pipeline against a local video."
    )
    parser.add_argument("video", type=Path, help="Input video path.")
    parser.add_argument(
        "--model",
        choices=("mc3", "fdsc_mc3", "x3d"),
        default="mc3",
        help="Verified violence model to use.",
    )
    parser.add_argument(
        "--device",
        choices=("auto", "cpu", "cuda"),
        default="cpu",
        help="Inference device. CPU is the safest baseline for repeatable validation.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=0,
        help="Maximum frames to process. 0 processes the entire video.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for an annotated MP4 output.",
    )
    parser.add_argument(
        "--no-pose",
        action="store_true",
        help="Disable the auxiliary pose stage.",
    )
    parser.add_argument(
        "--no-tracking",
        action="store_true",
        help="Disable ByteTrack and use the pipeline's fallback track IDs.",
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Print raw temporal predictions and whether they are scene- or person-level.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if not args.video.is_file():
        print(f"ERROR: video not found: {args.video}")
        return 2

    settings = AppSettings.from_dict(
        {
            "violence_model": args.model,
            "device": args.device,
            "pose_enabled": not args.no_pose,
            "tracking_enabled": not args.no_tracking,
        }
    )

    status_messages: dict[str, str] = {}

    def report_status(component: str, message: str) -> None:
        previous = status_messages.get(component)
        if previous == message:
            return
        status_messages[component] = message
        print(f"[{component}] {message}")

    print("CampusGuard full-pipeline validation")
    print(f"Video : {args.video}")
    print(f"Model : {args.model}")
    print(f"Device: {args.device}")
    print()

    pipeline = VisionPipeline(settings, report_status)

    capture = cv2.VideoCapture(str(args.video))
    if not capture.isOpened():
        print(f"ERROR: could not open video: {args.video}")
        return 3

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    frame_limit = args.max_frames if args.max_frames > 0 else None

    writer = None
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(
            str(args.output),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps if fps > 0 else 25.0,
            (frame_width, frame_height),
        )
        if not writer.isOpened():
            capture.release()
            print(f"ERROR: could not create output video: {args.output}")
            return 4

    state_counts: Counter[str] = Counter()
    event_counts: Counter[str] = Counter()
    events: list[tuple[int, str, float, str]] = []
    processed_frames = 0
    started = perf_counter()

    try:
        while frame_limit is None or processed_frames < frame_limit:
            ok, frame = capture.read()
            if not ok or frame is None or frame.size == 0:
                break

            processed_frames += 1
            annotated, state, confidence, event = pipeline.process(
                frame,
                settings,
                ai_enabled=True,
                tracking_enabled=not args.no_tracking,
                pose_enabled=not args.no_pose,
            )

            state_counts[state] += 1

            if args.diagnostics:
                for diagnostic in pipeline.last_diagnostics:
                    if diagnostic.get("scope") == "scene":
                        print(
                            f"[clip] frame={diagnostic['frame']} "
                            f"scope=scene "
                            f"fight={float(diagnostic['fight_probability']):.3f} "
                            f"state={diagnostic['state']} "
                            f"clip={diagnostic['clip_length']} "
                            f"stride={diagnostic['inference_stride']}"
                        )
                    else:
                        print(
                            f"[clip] frame={diagnostic['frame']} "
                            f"scope=person "
                            f"person={diagnostic['person_id']} "
                            f"track={diagnostic['track_id']} "
                            f"fight={float(diagnostic['fight_probability']):.3f} "
                            f"state={diagnostic['state']} "
                            f"roi={diagnostic['roi_width']}x{diagnostic['roi_height']} "
                            f"clip={diagnostic['buffer_length']}"
                        )

            if writer is not None:
                writer.write(annotated)

            if event is not None:
                event_name, event_confidence, severity = event
                event_counts[event_name] += 1
                events.append(
                    (processed_frames, event_name, event_confidence, severity)
                )
                print(
                    f"EVENT frame={processed_frames} "
                    f"type={event_name} confidence={event_confidence:.1%} "
                    f"severity={severity}"
                )

            if processed_frames % 100 == 0:
                confidence_text = (
                    f"{confidence:.1%}" if confidence is not None else "N/A"
                )
                print(
                    f"Progress: {processed_frames} frames | "
                    f"state={state} | confidence={confidence_text}"
                )
    finally:
        capture.release()
        if writer is not None:
            writer.release()

    elapsed = perf_counter() - started
    throughput = processed_frames / max(elapsed, 1e-6)

    print()
    print("=== PIPELINE RESULT ===")
    print(f"Frames processed : {processed_frames}")
    print(f"Source FPS       : {fps:.2f}")
    print(f"Elapsed          : {elapsed:.2f}s")
    print(f"Processing FPS   : {throughput:.2f}")
    print(f"Detector loaded  : {pipeline.detector is not None}")
    print(f"Pose loaded      : {pipeline.pose_model is not None}")
    print(f"Violence model   : {pipeline.model_display_name(args.model)}")
    selected_model = pipeline.classifiers.get(args.model)
    print(f"Classifier ready : {selected_model is not None and selected_model.ready}")
    print()
    print("States:")
    for state, count in state_counts.most_common():
        print(f"  {state}: {count}")

    print()
    print("Events:")
    if not events:
        print("  None")
    else:
        for frame_number, event_name, confidence, severity in events:
            print(
                f"  frame {frame_number}: {event_name} "
                f"({confidence:.1%}, {severity})"
            )

    if args.output is not None:
        print()
        print(f"Annotated output: {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
