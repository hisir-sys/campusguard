from __future__ import annotations

import argparse
from time import perf_counter

import cv2

from campusguard.camera_runtime import CameraManager
from campusguard.settings import AppSettings
from campusguard.ai_pipeline import VisionPipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark CampusGuard AI on a local video.")
    parser.add_argument("video", help="Path to a test video.")
    parser.add_argument("--model", choices=("mc3", "fdsc_mc3", "r3d", "x3d"), default="mc3")
    parser.add_argument("--max-frames", type=int, default=600)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    args = parser.parse_args()

    settings = AppSettings.from_dict({
        "violence_model": args.model,
        "device": args.device,
    })
    capture = cv2.VideoCapture(args.video)
    if not capture.isOpened():
        print(f"Could not open video: {args.video}")
        return 2

    pipeline = VisionPipeline(settings, lambda component, message: print(f"[{component}] {message}"))
    frames = 0
    started = perf_counter()
    inference_ms = 0.0
    states: dict[str, int] = {}

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
        inference_ms += (perf_counter() - before) * 1000.0
        states[state] = states.get(state, 0) + 1
        frames += 1

    capture.release()
    elapsed = perf_counter() - started
    wall_fps = frames / elapsed if elapsed else 0.0
    avg_frame_ms = inference_ms / frames if frames else 0.0

    print()
    print("CampusGuard AI benchmark")
    print(f"Model: {args.model}")
    print(f"Frames: {frames}")
    print(f"Wall FPS: {wall_fps:.2f}")
    print(f"Average pipeline time: {avg_frame_ms:.1f} ms/frame")
    print(f"Last temporal inference: {pipeline.last_inference_ms:.1f} ms")
    print(f"States: {states}")
    print()
    print("Accuracy is not inferred from this benchmark. Use labelled test clips and compare predictions with ground truth.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
