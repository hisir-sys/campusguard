"""Camera source address validation (no Qt / OpenCV / torch imports)."""
from __future__ import annotations

from urllib.parse import quote, urlsplit, urlunsplit

from campusguard.settings import CameraCredentials


def build_capture_source(
    source_type: str,
    source_address: str,
    credentials: CameraCredentials | None = None,
) -> int | str:
    source_type = source_type.upper()
    address = source_address.strip()
    credentials = credentials or CameraCredentials()

    if source_type == "USB":
        if credentials.username or credentials.password:
            raise ValueError("USB camera sources do not use username or password fields.")
        try:
            index = int(address)
        except ValueError as error:
            raise ValueError("Enter a USB camera device index, such as 1.") from error
        if index < 0:
            raise ValueError("USB device index must be zero or greater.")
        return index

    if source_type == "IP" and "://" not in address:
        address = f"http://{address}"
    elif source_type in {"HTTP", "MJPEG"} and "://" not in address:
        address = f"http://{address}"

    parsed = urlsplit(address)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(
            "Do not put credentials inside the camera URL. Enter them in the separate username and password fields."
        )
    if source_type == "RTSP" and parsed.scheme.lower() not in {"rtsp", "rtsps"}:
        raise ValueError("RTSP sources must use an rtsp:// or rtsps:// address.")
    if source_type in {"HTTP", "MJPEG", "IP"} and parsed.scheme.lower() not in {
        "http", "https", "rtsp", "rtsps"
    }:
        raise ValueError("Enter an HTTP, HTTPS, RTSP, or RTSPS camera address.")
    if not parsed.netloc:
        raise ValueError("The camera source address is incomplete.")

    if credentials.username or credentials.password:
        host = parsed.netloc.rsplit("@", 1)[-1]
        user = quote(credentials.username, safe="")
        password = quote(credentials.password, safe="")
        auth = user if not password else f"{user}:{password}"
        parsed = parsed._replace(netloc=f"{auth}@{host}")

    return urlunsplit(parsed)
