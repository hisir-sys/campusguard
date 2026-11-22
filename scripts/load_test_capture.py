# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
"""How many cameras can this machine read? Run it on the school's server before the pilot.

    python scripts/load_test_capture.py --streams 50 --fps 20 --size 1280x720
    python scripts/load_test_capture.py --streams 150 --video my_sub_stream_sample.mp4

It plays a video file N times at once, paced like live cameras, through the same clip buffer
CampusGuard uses (EvidenceRing), and prints CPU cores used and memory. Raise --streams until
"keeping up" says NO. It does NOT run the AI model, so also watch the GPU during the real pilot.
Needs ffmpeg on PATH only if you do not pass --video.
"""
from __future__ import annotations

import argparse
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402

from campusguard.evidence import EvidenceRing  # noqa: E402


def make_sample(size: str, fps: int, path: str) -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg was not found. Install it, or pass --video with a sample file.")
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={fps}",
         "-t", "20", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", path],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--streams", type=int, default=16)
    parser.add_argument("--fps", type=int, default=20, help="frame rate of the (sub-)stream")
    parser.add_argument("--size", default="1280x720")
    parser.add_argument("--seconds", type=float, default=15.0)
    parser.add_argument("--video", help="a real sample clip from the school's cameras (better than the test pattern)")
    args = parser.parse_args()

    cv2.setNumThreads(1)
    video = args.video
    if not video:
        video = os.path.join(tempfile.mkdtemp(prefix="cg-load-"), "sample.mp4")
        make_sample(args.size, args.fps, video)
    rings = [EvidenceRing(fps=args.fps, width=1280) for _ in range(args.streams)]
    counts = [0] * args.streams
    period = 1.0 / args.fps
    end = time.time() + args.seconds

    def worker(index: int) -> None:
        capture = cv2.VideoCapture(video)
        due = time.time()
        while time.time() < end:
            ok, frame = capture.read()
            if not ok:
                capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            counts[index] += 1
            rings[index].push(frame)
            due += period
            pause = due - time.time()
            if pause > 0:
                time.sleep(pause)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(args.streams)]
    start, cpu_start = time.time(), time.process_time()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall, cpu = time.time() - start, time.process_time() - cpu_start
    per_stream = sum(counts) / wall / args.streams
    keeping_up = per_stream >= args.fps * 0.95
    memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"streams            : {args.streams} at {args.fps} fps")
    print(f"achieved fps/stream: {per_stream:.1f}   keeping up: {'yes' if keeping_up else 'NO - too many streams for this CPU'}")
    print(f"CPU used           : {cpu / wall:.2f} cores  ({cpu / wall / args.streams:.3f} per stream)")
    print(f"memory             : {memory:.0f} MB  ({memory / args.streams:.1f} MB per stream)")
    print(f"clip buffer        : {sum(r.byte_count for r in rings) / 1e6 / args.streams:.1f} MB per stream")
    return 0 if keeping_up else 1


if __name__ == "__main__":
    raise SystemExit(main())
