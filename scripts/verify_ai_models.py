from __future__ import annotations

import argparse
from pathlib import Path

from campusguard.model_registry import MODEL_PROFILES, VideoClassifier
from campusguard.settings import AppSettings


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify CampusGuard violence-model checkpoints.")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()

    settings = AppSettings(device=args.device)
    paths = {
        "mc3": settings.fight_model_path,
        "fdsc_mc3": settings.fdsc_mc3_model_path,
        "r3d": settings.r3d_model_path,
        "x3d": settings.x3d_model_path,
    }

    import torch

    device = torch.device("cuda:0" if args.device == "cuda" and torch.cuda.is_available() else "cpu")
    failures = 0

    print("CampusGuard AI checkpoint verification")
    print(f"Device: {device}")
    print()

    for key, profile in MODEL_PROFILES.items():
        configured = paths[key]
        path = Path(configured).expanduser()
        print(f"[{profile.name}]")
        print(f"  Path: {path}")

        if not path.is_file():
            print("  RESULT: MISSING")
            failures += 1
            print()
            continue

        messages: list[str] = []
        classifier = VideoClassifier(
            profile,
            str(path),
            device,
            settings.fight_positive_class,
            settings.confidence_threshold,
            lambda component, message: messages.append(message),
        )

        for message in messages:
            print(f"  {message}")

        if classifier.ready:
            print("  RESULT: READY")
        else:
            print("  RESULT: FAILED — checkpoint/architecture could not be loaded")
            failures += 1
        print()

    print("Enhanced: COMING SOON — intentionally not loaded.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
