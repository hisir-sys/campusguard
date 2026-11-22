# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
"""Score a video with the fight model at the video's true frame rate.

Use it to measure false alarms on footage that has NO fights (a normal classroom, a corridor) and
to see how many alerts a clip with a fight would raise, for different thresholds:

    python scripts/score_video.py calm.mp4 --calm
    python scripts/score_video.py fight.mp4

It feeds every frame at the video's own speed (the best case: the analyser keeps up), so the numbers
are what the model does when the PC is NOT overloaded. Run it on the school's own footage before
promising anything. With --calm it also prints false alarms per hour for each threshold.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from campusguard.model_registry import MODEL_PROFILES, VideoClassifier  # noqa: E402
from campusguard.settings import AppSettings  # noqa: E402

THRESHOLDS = (0.65, 0.75, 0.85, 0.90, 0.95)


def score(video: Path, model_path: Path) -> tuple[list[float], float]:
    classifier = VideoClassifier(MODEL_PROFILES["fdsc_mc3"], str(model_path), torch.device("cpu"), 0.65, lambda *_: None)
    if not classifier.ready:
        raise SystemExit("The fight model could not be loaded: " + str(model_path))
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise SystemExit(f"Cannot open {video}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 15.0)
    scores: list[float] = []
    index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        result = classifier.add_frame(frame, timestamp=index / fps)
        if result:
            scores.append(float(result[1]))
        index += 1
    return scores, index / fps


def incidents(scores: list[float], threshold: float, confirm: int) -> int:
    count = run = 0
    latched = False
    for value in scores:
        run = run + 1 if value >= threshold else 0
        if run >= confirm and not latched:
            count, latched = count + 1, True
        if value < threshold:
            latched = False
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("videos", nargs="+", type=Path)
    parser.add_argument("--model", type=Path, default=ROOT / "models" / "model_16_m3_0.8888.pth")
    parser.add_argument("--calm", action="store_true", help="the video has NO fight: report false alarms per hour")
    args = parser.parse_args()
    confirm = AppSettings().alert_confirm_predictions
    for video in args.videos:
        scores, seconds = score(video, args.model)
        print(f"\n{video.name}: {seconds:.0f} s, {len(scores)} checks (one about every {seconds / max(1, len(scores)):.2f} s)")
        print("scores:", " ".join(f"{value:.2f}" for value in scores))
        if args.calm and seconds < 600:
            print("(this clip is short, so the per-hour figure is only a rough warning; use 30 minutes or more of calm footage)")
        print(f"alerts raised ({confirm} checks in a row at or above the threshold):")
        for threshold in THRESHOLDS:
            n = incidents(scores, threshold, confirm)
            extra = f"  = {n * 3600 / seconds:.0f} false alarms per hour per camera" if args.calm and seconds else ""
            print(f"  threshold {threshold:.2f}: {n}{extra}")


if __name__ == "__main__":
    main()
