# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
"""Camera source address validation (no Qt / OpenCV / torch imports)."""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import quote, urlsplit, urlunsplit

from campusguard.settings import CameraCredentials

_HOST_LABEL = re.compile(r"^(?!-)[A-Za-z0-9_-]{1,63}(?<!-)$")
_LOCAL_SUFFIXES = (".local", ".lan", ".home", ".internal", ".localdomain", ".home.arpa", ".corp", ".intranet")


def host_problem(host: str) -> str | None:
    """Why ``host`` cannot be a camera address, or None when it is fine.

    Any IPv4 or IPv6 address is accepted, public or private, and so is any host name.
    Nothing here restricts a camera to the local network.
    """
    host = (host or "").strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if not host:
        return "The camera address has no host name or IP address."
    if ":" in host:
        try:
            ipaddress.IPv6Address(host.split("%", 1)[0])
        except ValueError:
            return f"'{host}' is not a valid IPv6 address."
        return None
    if all(character.isdigit() or character == "." for character in host):
        try:
            ipaddress.IPv4Address(host)
        except ValueError:
            return f"'{host}' is not a valid IP address. Each of the four numbers must be between 0 and 255."
        return None
    name = host.rstrip(".")
    if not name.isascii():  # internationalised names are sent in their ASCII (punycode) form
        try:
            name = name.encode("idna").decode("ascii")
        except UnicodeError:
            return f"'{host}' is not a valid host name."
    if len(name) > 253 or not all(_HOST_LABEL.match(part) for part in name.split(".")):
        return f"'{host}' is not a valid host name."
    return None


def is_valid_host(host: str) -> bool:
    return host_problem(host) is None


def is_internet_address(host: str) -> bool:
    """True for a public IP address, or a host name that does not look like a local one.

    Used only to show a reminder: a camera reached over the internet needs a port opened on the
    school's router and a strong camera password.
    """
    host = (host or "").strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_global
    except ValueError:
        name = host.lower().rstrip(".")
        if "." not in name or host_problem(host) is not None:
            return False
        return not name.endswith(_LOCAL_SUFFIXES)


def address_host(source_type: str, source_address: str) -> str:
    """The host part of a camera address as typed, or '' for USB or an address with no host yet."""
    if source_type.upper() == "USB":
        return ""
    address = (source_address or "").strip()
    if not address:
        return ""
    if "://" not in address:
        address = f"http://{address}"
    try:
        return urlsplit(address).hostname or ""
    except ValueError:
        return ""


def build_rtsp_url(
    host: str,
    port: int = 554,
    user: str = "",
    password: str = "",
    path: str = "/stream1",
    *,
    secure: bool = False,
) -> str:
    """Build an RTSP address. Credentials are percent-encoded so characters such as ``@`` are safe."""
    problem = host_problem(host)
    if problem:
        raise ValueError(problem)
    try:
        port_number = int(port)
    except (TypeError, ValueError) as error:
        raise ValueError("The camera port must be a number from 1 to 65535.") from error
    if not 1 <= port_number <= 65535:
        raise ValueError("The camera port must be a number from 1 to 65535.")
    bare = host.strip()[1:-1] if host.strip().startswith("[") else host.strip()
    host_part = f"[{bare}]" if ":" in bare else bare
    auth = ""
    if user:
        auth = quote(user, safe="")
        if password:
            auth += ":" + quote(password, safe="")
        auth += "@"
    path = path.strip() or "/"
    if not path.startswith("/"):
        path = "/" + path
    return f"{'rtsps' if secure else 'rtsp'}://{auth}{host_part}:{port_number}{path}"


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

    try:
        parsed = urlsplit(address)
        port = parsed.port
    except ValueError as error:
        raise ValueError(
            "The camera address is not valid. Check the IP address or host name and that the port is a number from 1 to 65535."
        ) from error
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
    if port == 0:
        raise ValueError("The camera port must be a number from 1 to 65535.")
    problem = host_problem(parsed.hostname or "")
    if problem:
        raise ValueError(problem)

    if credentials.username or credentials.password:
        host = parsed.netloc.rsplit("@", 1)[-1]
        user = quote(credentials.username, safe="")
        password = quote(credentials.password, safe="")
        auth = user if not password else f"{user}:{password}"
        parsed = parsed._replace(netloc=f"{auth}@{host}")

    return urlunsplit(parsed)
