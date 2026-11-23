# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
"""Train the CampusGuard fight model (MC3-18, 16 frames, 112x112) from your own videos.

Folder layout (names of the two folders matter; anything inside may be nested):

    data/
      fight/      staged or real fights, any length
      nofight/    classrooms, corridors, playground, canteen, sport, running, hugging, shoving in play
      segments.csv   (optional)  video,start_s,end_s   one row per fight stretch inside a fight video

Without segments.csv every window of a video in fight/ counts as a fight. With it, only the listed
seconds count as fight and the rest of that video becomes a nofight "hard negative" (best, because
real fight videos contain a lot of people standing around).

Frames are decoded once to 15 fps, resized exactly like the app does (RGB, 171x128, INTER_AREA) and
cached as .npy files, so training and the app see the same pixels.

    python fightkit.py prepare --data data --cache cache
    python fightkit.py train   --cache cache --out fight_model.pth
    python fightkit.py check   --model fight_model.pth --videos calm1.mp4 calm2.mp4
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import random
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn

FPS = 15.0
CLIP = 16
RESIZE = (171, 128)         # width, height: same as the app
CROP = 112
MEAN = (0.43216, 0.394666, 0.37645)
STD = (0.22803, 0.22145, 0.216989)
FIGHT, NOFIGHT = 0, 1       # class order the app expects: ("fight", "noFight"), fight = index 0
VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg"}


# ----------------------------------------------------------------------------- prepare
def decode(video: Path) -> np.ndarray:
    """All frames of a video at FPS, RGB, 128x171, uint8 (N,128,171,3)."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise OSError(f"cannot open {video}")
    source_fps = float(capture.get(cv2.CAP_PROP_FPS) or FPS)
    if not 1.0 <= source_fps <= 240.0:
        source_fps = FPS
    frames, index, next_time = [], 0, 0.0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if index / source_fps >= next_time - 1e-6:         # keep a frame every 1/FPS seconds
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(cv2.resize(rgb, RESIZE, interpolation=cv2.INTER_AREA))
            next_time += 1.0 / FPS
        index += 1
    capture.release()
    return np.stack(frames) if frames else np.zeros((0, RESIZE[1], RESIZE[0], 3), np.uint8)


def read_segments(path: Path) -> dict[str, list[tuple[float, float]]]:
    out: dict[str, list[tuple[float, float]]] = {}
    if path.is_file():
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                out.setdefault(row["video"].strip(), []).append((float(row["start_s"]), float(row["end_s"])))
    return out


def prepare(data: Path, cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    segments = read_segments(data / "segments.csv")
    rows = []
    for kind in ("fight", "nofight"):
        for video in sorted((data / kind).rglob("*")):
            if video.suffix.lower() not in VIDEO_EXT:
                continue
            name = hashlib.sha1(str(video.relative_to(data)).encode()).hexdigest()[:12]
            target = cache / f"{name}.npy"
            frames = None
            if not target.exists():
                try:
                    frames = decode(video)
                except OSError as error:
                    print("skip:", error)
                    continue
                if len(frames) < CLIP:
                    print(f"skip (shorter than {CLIP} frames): {video}")
                    continue
                np.save(target, frames)
            n = len(np.load(target, mmap_mode="r")) if frames is None else len(frames)
            segs = segments.get(video.name, []) if kind == "fight" else []
            rows.append((name, kind, video.name, n, ";".join(f"{a}-{b}" for a, b in segs)))
            print(f"{kind:8s} {video.name}: {n / FPS:.0f} s")
    with (cache / "index.csv").open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows([("id", "kind", "video", "frames", "segments"), *rows])
    fights = sum(r[3] for r in rows if r[1] == "fight") / FPS / 60
    calm = sum(r[3] for r in rows if r[1] == "nofight") / FPS / 60
    print(f"\n{len(rows)} videos cached: {fights:.1f} min fight videos, {calm:.1f} min nofight videos")


# ----------------------------------------------------------------------------- dataset
def load_index(cache: Path) -> list[dict]:
    with (cache / "index.csv").open(newline="", encoding="utf-8") as handle:
        out = []
        for row in csv.DictReader(handle):
            segs = [tuple(float(x) for x in s.split("-")) for s in row["segments"].split(";") if s]
            out.append({**row, "frames": int(row["frames"]), "segs": segs})
        return out


def split_videos(index: list[dict], val_fraction: float) -> tuple[list[dict], list[dict]]:
    """Split by VIDEO (never by clip, or the model sees the same scene in training and testing)."""
    train, val = [], []
    for item in index:
        bucket = int(hashlib.sha1(item["id"].encode()).hexdigest(), 16) % 1000 / 1000
        (val if bucket < val_fraction else train).append(item)
    for kind in ("fight", "nofight"):                       # make sure validation has both kinds
        if not any(v["kind"] == kind for v in val):
            movers = [t for t in train if t["kind"] == kind][:1]
            for m in movers:
                train.remove(m)
                val.append(m)
    return train, val


def window_label(item: dict, start: int) -> int:
    if item["kind"] == "nofight":
        return NOFIGHT
    if not item["segs"]:
        return FIGHT
    middle = (start + CLIP / 2) / FPS
    return FIGHT if any(a <= middle <= b for a, b in item["segs"]) else NOFIGHT


def windows(item: dict, step: int) -> list[tuple[int, int]]:
    return [(s, window_label(item, s)) for s in range(0, item["frames"] - CLIP + 1, step)]


def to_tensor(clip: np.ndarray, device=None) -> torch.Tensor:
    """(16,112,112,3) uint8 RGB -> (1,3,16,112,112) float, Kinetics normalisation (same as the app)."""
    t = torch.from_numpy(np.ascontiguousarray(clip)).permute(3, 0, 1, 2).unsqueeze(0).float() / 255.0
    mean = torch.tensor(MEAN).view(1, 3, 1, 1, 1)
    std = torch.tensor(STD).view(1, 3, 1, 1, 1)
    t = (t - mean) / std
    return t.to(device) if device is not None else t


def center_crop(clip: np.ndarray) -> np.ndarray:
    h, w = clip.shape[1:3]
    top, left = (h - CROP) // 2, (w - CROP) // 2
    return clip[:, top:top + CROP, left:left + CROP]


class ClipSet(torch.utils.data.Dataset):
    def __init__(self, cache: Path, items: list[dict], step: int, train: bool):
        self.cache, self.items, self.train = cache, items, train
        self.samples = [(i, s, y) for i, it in enumerate(items) for s, y in windows(it, step)]
        self._open: dict[int, np.ndarray] = {}

    def labels(self) -> list[int]:
        return [y for _, _, y in self.samples]

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, k: int):
        i, start, label = self.samples[k]
        if i not in self._open:
            self._open[i] = np.load(self.cache / f"{self.items[i]['id']}.npy", mmap_mode="r")
        frames = self._open[i]
        if self.train:
            gap = random.choice((1, 1, 1, 1, 2))            # now and then a slower camera
            if start + (CLIP - 1) * gap >= len(frames):
                gap = 1
            clip = np.array(frames[start:start + CLIP * gap:gap])
            h, w = clip.shape[1:3]
            top = (h - CROP) // 2 + random.randint(-10, 10)
            left = (w - CROP) // 2 + random.randint(-14, 14)
            top, left = max(0, min(h - CROP, top)), max(0, min(w - CROP, left))
            clip = clip[:, top:top + CROP, left:left + CROP]
            if random.random() < 0.5:
                clip = clip[:, :, ::-1]
            clip = clip.astype(np.float32)
            clip = clip * random.uniform(0.7, 1.3) + random.uniform(-25, 25)      # brightness/contrast
            if random.random() < 0.2:                                              # grayscale-ish CCTV
                clip[:] = clip.mean(axis=3, keepdims=True)
            clip = np.clip(clip, 0, 255).astype(np.uint8)
        else:
            clip = center_crop(np.array(frames[start:start + CLIP]))
        return to_tensor(clip)[0], label


# ----------------------------------------------------------------------------- model
def build_model(pretrained: bool) -> nn.Module:
    from torchvision.models.video import MC3_18_Weights, mc3_18
    model = mc3_18(weights=MC3_18_Weights.KINETICS400_V1 if pretrained else None)
    model.fc = nn.Linear(model.fc.in_features, 2)
    return model


def evaluate(model, loader, device) -> dict:
    model.eval()
    probs, labels = [], []
    with torch.inference_mode():
        for x, y in loader:
            p = torch.softmax(model(x.to(device)), dim=1)[:, FIGHT].cpu()
            probs.append(p)
            labels.append(y)
    p, y = torch.cat(probs).numpy(), torch.cat(labels).numpy()
    fight = y == FIGHT
    out = {"windows": len(y)}
    for th in (0.65, 0.85, 0.95):
        out[f"recall@{th}"] = float((p[fight] >= th).mean()) if fight.any() else float("nan")
        out[f"false_pos@{th}"] = float((p[~fight] >= th).mean()) if (~fight).any() else float("nan")
    return out


def train(cache: Path, out: Path, epochs: int, batch: int, lr: float, val_fraction: float,
          pretrained: bool, step: int, workers: int, max_windows: int, seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    index = load_index(cache)
    train_items, val_items = split_videos(index, val_fraction)
    print(f"{len(train_items)} training videos, {len(val_items)} validation videos, device {device}")
    train_set = ClipSet(cache, train_items, step, True)
    val_set = ClipSet(cache, val_items, max(step, 8), False)
    labels = np.array(train_set.labels())
    if (labels == FIGHT).sum() == 0 or (labels == NOFIGHT).sum() == 0:
        raise SystemExit("Training data needs BOTH fight and nofight windows.")
    # Balanced sampling: half the clips seen per epoch are fights, half are not.
    weights = np.where(labels == FIGHT, 0.5 / (labels == FIGHT).sum(), 0.5 / (labels == NOFIGHT).sum())
    per_epoch = min(len(train_set), max_windows)
    sampler = torch.utils.data.WeightedRandomSampler(weights, per_epoch, replacement=True)
    loader = torch.utils.data.DataLoader(train_set, batch, sampler=sampler, num_workers=workers, drop_last=True,
                                         persistent_workers=workers > 0)
    val_loader = torch.utils.data.DataLoader(val_set, batch, num_workers=workers)

    model = build_model(pretrained).to(device)
    # Penalise a false alarm a little more than a miss: staff stop trusting a noisy system.
    loss_fn = nn.CrossEntropyLoss(weight=torch.tensor([1.0, 1.5], device=device), label_smoothing=0.05)
    params = [
        {"params": [p for n, p in model.named_parameters() if not n.startswith("fc")], "lr": lr * 0.3},
        {"params": model.fc.parameters(), "lr": lr},
    ]
    optim = torch.optim.AdamW(params, weight_decay=1e-2)
    steps = epochs * max(1, len(loader))
    sched = torch.optim.lr_scheduler.OneCycleLR(optim, [lr * 0.3, lr], total_steps=steps, pct_start=0.15)
    scaler = torch.amp.GradScaler(enabled=device.type == "cuda")

    best = (-1.0, None)
    for epoch in range(1, epochs + 1):
        model.train()
        started, total = time.time(), 0.0
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            with torch.autocast(device.type, enabled=device.type == "cuda"):
                loss = loss_fn(model(x), y)
            optim.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(optim)
            scaler.update()
            sched.step()
            total += float(loss)
        report = evaluate(model, val_loader, device)
        # Pick the epoch with the best recall while false alarms stay low (false alarms count double).
        score = report["recall@0.85"] - 2 * report["false_pos@0.85"]
        print(f"epoch {epoch}/{epochs}  loss {total / max(1, len(loader)):.3f}  "
              f"recall@.85 {report['recall@0.85']:.2f}  false@.85 {report['false_pos@0.85']:.3f}  "
              f"false@.95 {report['false_pos@0.95']:.3f}  ({time.time() - started:.0f}s)")
        if score > best[0]:
            best = (score, {k: v.detach().cpu().clone() for k, v in model.state_dict().items()})
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(best[1], out)
    print(f"\nsaved best epoch to {out}  (plain torchvision mc3_18 state dict, 2 classes, fight = class 0)")


# ----------------------------------------------------------------------------- check
def check(model_path: Path, videos: list[Path], step: int = 5) -> None:
    """False alarms on videos that contain NO fight, using the model exactly as the app loads it."""
    model = build_model(False)
    model.load_state_dict(torch.load(model_path, map_location="cpu", weights_only=True))
    model.eval()
    for video in videos:
        frames = decode(video)
        scores = []
        with torch.inference_mode():
            for s in range(0, len(frames) - CLIP + 1, step):
                clip = center_crop(frames[s:s + CLIP])
                scores.append(float(torch.softmax(model(to_tensor(clip)), 1)[0, FIGHT]))
        hours = len(frames) / FPS / 3600
        print(f"\n{video.name}: {len(frames) / FPS:.0f} s, {len(scores)} checks")
        for th in (0.65, 0.85, 0.95):
            alerts, run, latched = 0, 0, False
            for v in scores:
                run = run + 1 if v >= th else 0
                if run >= 2 and not latched:
                    alerts, latched = alerts + 1, True
                if v < th:
                    latched = False
            print(f"  threshold {th:.2f}: {alerts} alerts  = {alerts / hours:.0f} per hour per camera")


# ----------------------------------------------------------------------------- compare
def load_any(path: Path) -> dict:
    """Load a checkpoint of any common shape and return just the weights (fight = class 0 assumed)."""
    try:
        ck = torch.load(path, map_location="cpu", weights_only=True)
    except Exception:
        ck = torch.load(path, map_location="cpu", weights_only=False)   # your own files only
    for key in ("model_state_dict", "state_dict", "model", "net"):
        if isinstance(ck, dict) and isinstance(ck.get(key), dict):
            ck = ck[key]
            break
    if not isinstance(ck, dict):
        ck = ck.state_dict()
    return {k.removeprefix("module."): v.float() for k, v in ck.items() if torch.is_tensor(v)}


def score_windows(model, video: Path, step: int = 5) -> list[float]:
    frames = decode(video)
    out = []
    with torch.inference_mode():
        for s in range(0, len(frames) - CLIP + 1, step):
            out.append(float(torch.softmax(model(to_tensor(center_crop(frames[s:s + CLIP]))), 1)[0, FIGHT]))
    return out


def alerts_in(scores: list[float], th: float, confirm: int = 2) -> int:
    n = run = 0
    latched = False
    for v in scores:
        run = run + 1 if v >= th else 0
        if run >= confirm and not latched:
            n, latched = n + 1, True
        if v < th:
            latched = False
    return n


def compare(models: list[Path], calm: list[Path], fights: list[Path], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"{'model':32s} {'MB':>6s} {'false alarms/hour @.85':>24s} {'@.95':>6s} {'fights caught @.85':>20s}")
    for path in models:
        try:
            weights = load_any(path)
            model = build_model(False)
            model.load_state_dict(weights)
        except Exception as error:
            print(f"{path.name:32s} cannot load as MC3-18 with 2 classes: {str(error)[:90]}")
            continue
        model.eval()
        hours = false85 = false95 = 0.0
        for v in calm:
            sc = score_windows(model, v)
            hours += (len(sc) * 5 + CLIP) / FPS / 3600
            false85 += alerts_in(sc, 0.85)
            false95 += alerts_in(sc, 0.95)
        caught = sum(alerts_in(score_windows(model, v), 0.85) > 0 for v in fights)
        stripped = out_dir / (path.stem + "_stripped.pth")
        torch.save({k: v.half() if v.is_floating_point() else v for k, v in weights.items()}, stripped)
        mb = stripped.stat().st_size / 1e6
        rate85 = false85 / hours if hours else float("nan")
        rate95 = false95 / hours if hours else float("nan")
        print(f"{path.name:32s} {mb:6.0f} {rate85:24.1f} {rate95:6.1f} {caught:>14d} of {len(fights)}")
    print("\nStripped files (weights only, half precision) are in", out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("prepare")
    a.add_argument("--data", type=Path, required=True)
    a.add_argument("--cache", type=Path, required=True)
    b = sub.add_parser("train")
    b.add_argument("--cache", type=Path, required=True)
    b.add_argument("--out", type=Path, default=Path("fight_model.pth"))
    b.add_argument("--epochs", type=int, default=8)
    b.add_argument("--batch", type=int, default=8)
    b.add_argument("--lr", type=float, default=3e-4)
    b.add_argument("--val-fraction", type=float, default=0.2)
    b.add_argument("--step", type=int, default=4, help="frames between window starts")
    b.add_argument("--workers", type=int, default=2)
    b.add_argument("--max-windows", type=int, default=4000, help="clips seen per epoch")
    b.add_argument("--no-pretrained", action="store_true")
    b.add_argument("--seed", type=int, default=1)
    c = sub.add_parser("check")
    c.add_argument("--model", type=Path, required=True)
    c.add_argument("--videos", type=Path, nargs="+", required=True)
    d = sub.add_parser("compare", help="rank several checkpoints and shrink them for upload")
    d.add_argument("--models", type=Path, nargs="+", required=True)
    d.add_argument("--calm", type=Path, nargs="+", required=True, help="videos with NO fight")
    d.add_argument("--fights", type=Path, nargs="*", default=[], help="videos that contain a fight")
    d.add_argument("--out-dir", type=Path, default=Path("stripped"))
    args = parser.parse_args()
    if args.cmd == "compare":
        compare(args.models, args.calm, args.fights, args.out_dir)
    elif args.cmd == "prepare":
        prepare(args.data, args.cache)
    elif args.cmd == "train":
        train(args.cache, args.out, args.epochs, args.batch, args.lr, args.val_fraction,
              not args.no_pretrained, args.step, args.workers, args.max_windows, args.seed)
    else:
        check(args.model, args.videos)


if __name__ == "__main__":
    sys.exit(main())
