from __future__ import annotations

import argparse
from time import perf_counter

import cv2

from campusguard.settings import AppSettings
from campusguard.ai_pipeline import VisionPipeline


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark CampusGuard AI on a local video."
    )

    parser.add_argument(
        "video",
        help="Path to a test video.",
    )

    parser.add_argument(
        "--model",
        choices=("mc3", "fdsc_mc3", "r3d", "x3d"),
        default="fdsc_mc3",
    )

    parser.add_argument(
        "--max-frames",
        type=int,
        default=600,
    )

    parser.add_argument(
        "--device",
        choices=("auto", "cpu", "cuda"),
        default="auto",
    )

    parser.add_argument(
        "--show-predictions",
        action="store_true",
        help="Print temporal predictions and confidence values.",
    )

    args = parser.parse_args()

    settings = AppSettings.from_dict(
        {
            "violence_model": args.model,
            "device": args.device,
        }
    )

    capture = cv2.VideoCapture(args.video)

    if not capture.isOpened():
        print(f"Could not open video: {args.video}")
        return 2

    pipeline = VisionPipeline(
        settings,
        lambda component, message: print(
            f"[{component}] {message}"
        ),
    )

    frames = 0
    started = perf_counter()
    total_pipeline_ms = 0.0

    states: dict[str, int] = {}

    last_reported_state: str | None = None
    last_reported_confidence: float | None = None

    print()
    print("Starting CampusGuard AI benchmark...")
    print()

    while frames < args.max_frames:
        ok, frame = capture.read()

        if not ok:
            break

        before = perf_counter()

        _, state, confidence, _ = pipeline.process(
            frame,
            settings,
            ai_enabled=True,
            tracking_enabled=settings.tracking_enabled,
            pose_enabled=settings.pose_enabled,
        )

        frame_pipeline_ms = (
            perf_counter() - before
        ) * 1000.0

        total_pipeline_ms += frame_pipeline_ms

        frames += 1

        states[state] = states.get(state, 0) + 1

        # ---------------------------------------------------------
        # Optional prediction logging
        # ---------------------------------------------------------
        if args.show_predictions:
            if confidence is None:
                confidence_text = "N/A"

                confidence_changed = (
                    last_reported_confidence is not None
                )
            else:
                confidence_text = (
                    f"{confidence * 100.0:6.2f}%"
                )

                confidence_changed = (
                    last_reported_confidence is None
                    or abs(
                        confidence
                        - last_reported_confidence
                    ) >= 0.01
                )

            state_changed = (
                state != last_reported_state
            )

            if state_changed or confidence_changed:
                print(
                    f"Frame {frames:03d} | "
                    f"{state:<22} | "
                    f"confidence={confidence_text} | "
                    f"frame={frame_pipeline_ms:7.1f} ms | "
                    f"temporal={pipeline.last_inference_ms:7.1f} ms"
                )

                last_reported_state = state
                last_reported_confidence = confidence

    capture.release()

    elapsed = perf_counter() - started

    wall_fps = (
        frames / elapsed
        if elapsed > 0
        else 0.0
    )

    average_pipeline_ms = (
        total_pipeline_ms / frames
        if frames > 0
        else 0.0
    )

    # -------------------------------------------------------------
    # Final benchmark report
    # -------------------------------------------------------------

    print()
    print("=" * 64)
    print("CampusGuard AI benchmark")
    print("=" * 64)

    print(f"Model: {args.model}")
    print(f"Video: {args.video}")
    print(f"Frames: {frames}")
    print(f"Wall FPS: {wall_fps:.2f}")
    print(
        f"Average pipeline time: "
        f"{average_pipeline_ms:.1f} ms/frame"
    )
    print(
        f"Last temporal inference: "
        f"{pipeline.last_inference_ms:.1f} ms"
    )

    print()
    print("States:")

    if states:
        for state_name, count in states.items():
            percentage = (
                count / frames * 100.0
                if frames
                else 0.0
            )

            print(
                f"  {state_name:<24} "
                f"{count:>4} "
                f"({percentage:6.2f}%)"
            )
    else:
        print("  No states recorded.")

    print()
    print(
        "Accuracy is not inferred from this benchmark. "
        "Use labelled test clips and compare predictions "
        "with ground truth."
    )

    print("=" * 64)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())