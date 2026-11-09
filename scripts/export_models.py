"""Export the Spontim 1.0 classifier to ONNX (and optionally build a TensorRT engine).

Usage:  python scripts/export_models.py --out models/spontim.onnx [--tensorrt]

Run this once on the school server that has the NVIDIA GPU. TensorRT needs
`trtexec` from the TensorRT install on PATH. The exported file is a starting
point for faster batched inference: the app still runs the PyTorch model until
an engine loader is added, so measure before relying on it.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="spontim.onnx")
    parser.add_argument("--weights", required=True, help="path to the Spontim 1.0 checkpoint (.pth)")
    parser.add_argument("--tensorrt", action="store_true")
    parser.add_argument("--frames", type=int, default=16)
    parser.add_argument("--size", type=int, default=112)
    args = parser.parse_args()

    import torch
    from campusguard.model_registry import MODEL_PROFILES, VideoClassifier

    profile = MODEL_PROFILES["fdsc_mc3"]
    classifier = VideoClassifier(profile, args.weights, torch.device("cpu"), 0.5, lambda key, msg: print(msg))
    if classifier.model is None:
        print("Could not load the checkpoint.")
        return 1
    model = classifier.model.eval()
    dummy = torch.zeros(1, 3, args.frames, args.size, args.size)
    torch.onnx.export(
        model, dummy, args.out, input_names=["clip"], output_names=["logits"],
        dynamic_axes={"clip": {0: "batch"}, "logits": {0: "batch"}}, opset_version=17,
    )
    print(f"ONNX written: {args.out}")
    if args.tensorrt:
        trtexec = shutil.which("trtexec")
        if not trtexec:
            print("trtexec not found on PATH; install TensorRT to build an engine.")
            return 1
        engine = str(Path(args.out).with_suffix(".engine"))
        return subprocess.call([trtexec, f"--onnx={args.out}", f"--saveEngine={engine}", "--fp16"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
