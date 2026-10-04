from __future__ import annotations

import argparse
from pathlib import Path

import torch

from campusguard.model_registry import MODEL_PROFILES, VideoClassifier
from campusguard.settings import AppSettings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify CampusGuard violence-model checkpoints and class mappings."
    )
    parser.add_argument(
        "--device",
        choices=("cpu", "cuda"),
        default="cpu",
    )
    args = parser.parse_args()

    settings = AppSettings(device=args.device)
    paths = {
        key: getattr(settings, profile.path_setting)
        for key, profile in MODEL_PROFILES.items()
    }

    if args.device == "cuda" and not torch.cuda.is_available():
        print("CUDA requested but unavailable; verification will use CPU.")
        device = torch.device("cpu")
    elif args.device == "cuda":
        device = torch.device("cuda:0")
    else:
        device = torch.device("cpu")

    failures = 0
    ready_count = 0
    verified_count = 0

    print("=" * 72)
    print("CampusGuard AI model verification")
    print("=" * 72)
    print(f"Device: {device}")
    print()

    for key, profile in MODEL_PROFILES.items():
        path = Path(paths[key]).expanduser()

        print(f"[{profile.name}]")
        print(f"  Key: {key}")
        print(f"  Architecture: {profile.architecture}")
        print(f"  Path: {path}")
        print(f"  Expected classes: {profile.class_labels}")
        print(
            "  Fight class: "
            + (
                str(profile.fight_class)
                if profile.fight_class is not None
                else "UNVERIFIED"
            )
        )
        print(f"  Semantic status: {profile.semantic_status}")

        if not path.is_file():
            print("  Checkpoint: MISSING")
            print("  RESULT: MISSING")
            failures += 1
            print()
            continue

        messages: list[str] = []
        classifier = VideoClassifier(
            profile,
            str(path),
            device,
            settings.confidence_threshold,
            lambda component, message: messages.append(message),
        )

        for message in messages:
            print(f"  {message}")

        if not classifier.ready:
            print("  RESULT: FAILED — checkpoint/architecture could not be loaded")
            failures += 1
            print()
            continue

        ready_count += 1

        if not classifier.semantic_ready:
            print(
                "  RESULT: BLOCKED — checkpoint loaded, but fight-class "
                "semantics are not verified."
            )
            failures += 1
            print()
            continue

        verified_count += 1
        print(
            f"  Class mapping: class {classifier.fight_class} = "
            f"{classifier.semantic_label}"
        )
        print("  RESULT: READY")
        print()

    print("[CampusGuard Enhanced]")
    print("  Status: COMING SOON")
    print("  Operational: NO")
    print("  RESULT: NOT LOADED BY DESIGN")
    print()
    print("=" * 72)
    print(
        f"Verified operational models: {verified_count}/{len(MODEL_PROFILES)}"
    )
    print(f"Loaded but not semantically verified: {ready_count - verified_count}")
    print(
        f"Missing/failed/blocked: "
        f"{len(MODEL_PROFILES) - verified_count}"
    )
    print("=" * 72)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
