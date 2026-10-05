from __future__ import annotations

"""Download only the verified optional CampusGuard violence checkpoints."""

from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"

FDSC_MC3_ID = "1MWDeLnpEaZDrKK-OjmzvYLxfjwp-GDcp"
X3D_URL = (
    "https://huggingface.co/visionlab-ai/school-violence-detection-models/"
    "resolve/main/final/final_x3d_realtime.pt?download=true"
)


def download_url(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        print(f"Already present: {destination}")
        return

    print(f"Downloading: {destination.name}")
    request = Request(url, headers={"User-Agent": "CampusGuard/1.0"})
    with urlopen(request) as response, destination.open("wb") as output:
        total = int(response.headers.get("Content-Length", "0"))
        downloaded = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            downloaded += len(chunk)
            if total:
                print(
                    f"  {downloaded / 1024 / 1024:.1f} / "
                    f"{total / 1024 / 1024:.1f} MB",
                    end="\r",
                )
    print()


def download_fdsc() -> None:
    destination = MODELS / "model_16_m3_0.8888.pth"
    if destination.exists():
        print(f"Already present: {destination}")
        return

    try:
        import gdown
    except ImportError:
        raise SystemExit(
            "FDSC download needs gdown. Run: python -m pip install gdown"
        )

    print(f"Downloading: {destination.name}")
    gdown.download(
        id=FDSC_MC3_ID,
        output=str(destination),
        quiet=False,
    )


def main() -> None:
    MODELS.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("CampusGuard verified optional model installer")
    print("=" * 72)
    print()
    print("1/2 FDSC MC3-18")
    print("    Source: MohamedSebaie Fight Detection project")
    print("    Contract: 16 frames, fight/noFight, fight=class 0")
    download_fdsc()

    print()
    print("2/2 X3D-M")
    print("    Source: visionlab-ai/school-violence-detection-models")
    print("    Contract: 16 frames, 224x224, non-violent/violent")
    download_url(X3D_URL, MODELS / "final_x3d_realtime.pt")

    print()
    print("=" * 72)
    print("Download step complete.")
    print("R3D-18 was intentionally not downloaded because its checkpoint")
    print("identity and class mapping are not sufficiently documented.")
    print("=" * 72)


if __name__ == "__main__":
    main()
