from __future__ import annotations

"""Download only the verified optional CampusGuard violence checkpoints."""

from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"

FDSC_MC3_ID = "1MWDeLnpEaZDrKK-OjmzvYLxfjwp-GDcp"


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
    print("Spontim 1.0 (FDSC MC3-18)")
    print("    Source: MohamedSebaie Fight Detection project")
    print("    Contract: 16 frames, fight/noFight, fight=class 0")
    download_fdsc()

    print()
    print("=" * 72)
    print("Download step complete.")
    print("=" * 72)


if __name__ == "__main__":
    main()
