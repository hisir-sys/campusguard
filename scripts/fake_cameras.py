"""Pretend to be a school's camera system, so CampusGuard can be tested with 50 "cameras" on one PC.

Three steps (see docs/LOAD_TEST_GUIDE.md for the full walk-through):

    python scripts/fake_cameras.py encode my_clip.mp4          # make a small camera-like sub-stream
    python scripts/fake_cameras.py serve  --count 50           # publish 50 RTSP feeds (needs MediaMTX running)
    python scripts/fake_cameras.py csv    --count 50           # a CSV to import into CampusGuard

Uses only the standard library plus ffmpeg on PATH. It never uses real cameras or real passwords.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_SUBSTREAM = "substream_test.mp4"
DEFAULT_BASE = "rtsp://127.0.0.1:8554"


def need_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise SystemExit("ffmpeg was not found. Install it and add it to PATH (check: ffmpeg -version).")
    return path


def encode_command(source: str, output: str, size: str, fps: int) -> list[str]:
    width, height = size.lower().split("x")
    return [
        need_ffmpeg(), "-y", "-i", source,
        "-vf", f"scale={width}:{height}", "-r", str(fps),
        "-c:v", "libx264", "-preset", "fast", "-crf", "26",
        "-g", str(fps * 2),            # a keyframe every 2 s, like a camera
        "-pix_fmt", "yuv420p", "-an", output,
    ]


def publish_command(video: str, url: str) -> list[str]:
    return [
        need_ffmpeg(), "-loglevel", "error", "-re", "-stream_loop", "-1", "-i", video,
        "-c", "copy", "-rtsp_transport", "tcp", "-f", "rtsp", url,
    ]


def cmd_encode(args: argparse.Namespace) -> int:
    if not Path(args.source).is_file():
        raise SystemExit(f"Cannot find {args.source}")
    subprocess.run(encode_command(args.source, args.output, args.size, args.fps), check=True)
    print(f"Wrote {args.output} ({args.size} at {args.fps} fps, no audio).")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    if not Path(args.video).is_file():
        raise SystemExit(f"Cannot find {args.video}. Run the 'encode' step first.")
    processes: list[subprocess.Popen] = []
    print(f"Starting {args.count} fake cameras from {args.video} ... (MediaMTX must already be running)")
    try:
        for number in range(1, args.count + 1):
            url = f"{args.base.rstrip('/')}/cam_{number}"
            processes.append(subprocess.Popen(publish_command(args.video, url), stdout=subprocess.DEVNULL))
            time.sleep(args.stagger)
        time.sleep(2)
        dead = [i + 1 for i, p in enumerate(processes) if p.poll() is not None]
        if dead:
            print(f"WARNING: {len(dead)} feeds stopped straight away (first: cam_{dead[0]}). Is MediaMTX running?")
        print(f"{len(processes) - len(dead)} feeds live: {args.base}/cam_1 ... cam_{args.count}")
        print("Press Ctrl+C to stop them all.")
        while True:
            time.sleep(5)
            failed = [i + 1 for i, p in enumerate(processes) if p.poll() is not None]
            if failed and len(failed) != len(dead):
                dead = failed
                print(f"{len(failed)} feeds have stopped (first: cam_{failed[0]}).")
    except KeyboardInterrupt:
        print("\nStopping ...")
    finally:
        for process in processes:
            process.terminate()
    return 0


def cmd_csv(args: argparse.Namespace) -> int:
    buildings = [name.strip() for name in args.buildings.split(",") if name.strip()] or ["Test Block"]
    with open(args.output, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "type", "address", "group", "sensitivity", "ai"])
        for number in range(1, args.count + 1):
            writer.writerow([
                f"Test Cam {number:03d}", "RTSP", f"{args.base.rstrip('/')}/cam_{number}",
                buildings[(number - 1) % len(buildings)], "Default", "yes",
            ])
    print(f"Wrote {args.output} with {args.count} cameras. In CampusGuard: Cameras -> Import CSV.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    encode = sub.add_parser("encode", help="turn any video into a small camera-like sub-stream")
    encode.add_argument("source")
    encode.add_argument("--output", default=DEFAULT_SUBSTREAM)
    encode.add_argument("--size", default="640x360", help="try 960x540 for better clips (more CPU)")
    encode.add_argument("--fps", type=int, default=15)
    encode.set_defaults(func=cmd_encode)

    serve = sub.add_parser("serve", help="publish N fake RTSP cameras to a running MediaMTX")
    serve.add_argument("--count", type=int, default=50)
    serve.add_argument("--video", default=DEFAULT_SUBSTREAM)
    serve.add_argument("--base", default=DEFAULT_BASE)
    serve.add_argument("--stagger", type=float, default=0.1, help="seconds between starts")
    serve.set_defaults(func=cmd_serve)

    make_csv = sub.add_parser("csv", help="write a CSV of the fake cameras for Import CSV")
    make_csv.add_argument("--count", type=int, default=50)
    make_csv.add_argument("--base", default=DEFAULT_BASE)
    make_csv.add_argument("--output", default="fake_cameras.csv")
    make_csv.add_argument("--buildings", default="Block A,Block B", help="comma list; cameras are spread across them")
    make_csv.set_defaults(func=cmd_csv)

    args = parser.parse_args(argv)
    if getattr(args, "count", 1) < 1 or getattr(args, "count", 1) > 1000:
        raise SystemExit("--count must be 1 to 1000")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
