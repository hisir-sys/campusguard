"""Find cameras on the school's own network (no Qt / OpenCV imports).

Two methods are combined:

* ONVIF discovery: a WS-Discovery probe is sent to the standard multicast address and cameras
  that support ONVIF answer with their address.
* Port scan: every address on the local /24 network is checked for the RTSP ports (554, 8554).

Only the machine's own private network is scanned, and only for those ports. Nothing is sent
beyond a TCP connection attempt and the standard discovery probe.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

RTSP_PORTS = (554, 8554)
WS_DISCOVERY_ADDRESS = ("239.255.255.250", 3702)

_PROBE = """<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
 xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
 xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
 xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
<e:Header><w:MessageID>uuid:{message_id}</w:MessageID>
<w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
<w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action></e:Header>
<e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body>
</e:Envelope>"""

# Stream paths that cover most cameras, most common first. The user can type their own.
COMMON_STREAM_PATHS = (
    "/stream1",
    "/Streaming/Channels/101",
    "/cam/realmonitor?channel=1&subtype=0",
    "/live",
    "/h264",
    "/",
)


@dataclass
class FoundCamera:
    host: str
    ports: set[int] = field(default_factory=set)
    onvif: bool = False

    @property
    def port(self) -> int:
        return min(self.ports) if self.ports else 554

    @property
    def found_by(self) -> str:
        parts = []
        if self.onvif:
            parts.append("ONVIF")
        if self.ports:
            label = "port" if self.onvif else "Port"
            parts.append(f"{label} " + "/".join(str(port) for port in sorted(self.ports)))
        return ", ".join(parts) or "Network"

    def sort_key(self) -> tuple[int, ...]:
        try:
            return tuple(int(part) for part in self.host.split("."))
        except ValueError:
            return (999, 999, 999, 999)


def local_address() -> str | None:
    """This machine's address on its main network. Opening a UDP socket sends no data."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return None
    finally:
        probe.close()


def local_network(address: str | None = None) -> ipaddress.IPv4Network | None:
    """The /24 around this machine, or None when it is not on a private network."""
    if address is None:
        address = local_address()
    if not address:
        return None
    try:
        ip = ipaddress.IPv4Address(address)
    except ValueError:
        return None
    if not ip.is_private or ip.is_loopback or ip.is_link_local:
        return None
    return ipaddress.ip_network(f"{ip}/24", strict=False)


_XADDRS_BLOCK = re.compile(r"<[^>]*XAddrs[^>]*>(.*?)</", re.DOTALL)
_URL_HOST = re.compile(r"https?://(\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?[/\s<]|https?://(\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?$")


def parse_probe_match(payload: bytes, sender: str) -> str:
    """The IPv4 address a camera advertises in its probe match, or whoever answered if it names none."""
    text = payload.decode("utf-8", errors="ignore")
    block = _XADDRS_BLOCK.search(text)
    if block:
        for url in block.group(1).split():
            match = _URL_HOST.match(url + " ")
            if not match:
                continue
            try:
                address = ipaddress.IPv4Address(match.group(1) or match.group(2))
            except ValueError:
                continue
            if not address.is_link_local:
                return str(address)
    return sender


def onvif_discover(
    timeout: float = 3.0,
    cancel: threading.Event | None = None,
    interface: str | None = None,
) -> set[str]:
    """Addresses of ONVIF cameras that answer a multicast probe within ``timeout`` seconds.

    ``interface`` is this computer's address on the network being scanned. Sending the probe out of
    that network card keeps it on the right network when a VPN or virtual adapter is also present.
    """
    found: set[str] = set()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        if interface:
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(interface))
            except OSError:
                pass  # fall back to the system's choice of network card
        sock.settimeout(0.4)
        sock.sendto(_PROBE.format(message_id=uuid.uuid4()).encode(), WS_DISCOVERY_ADDRESS)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not (cancel and cancel.is_set()):
            try:
                payload, sender = sock.recvfrom(65535)
            except socket.timeout:
                continue
            found.add(parse_probe_match(payload, sender[0]))
    except OSError:
        # No multicast on this network (common with managed switches): the port scan still runs.
        pass
    finally:
        sock.close()
    return found


def port_open(host: str, port: int = 554, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((str(host), port), timeout=timeout):
            return True
    except OSError:
        return False


def scan_network(
    ports: tuple[int, ...] = RTSP_PORTS,
    *,
    network: ipaddress.IPv4Network | None = None,
    use_onvif: bool = True,
    cancel: threading.Event | None = None,
    progress: Callable[[int, int], None] | None = None,
    timeout: float = 0.5,
    workers: int = 100,
) -> list[FoundCamera]:
    """Scan this machine's own network and return every camera-like device found, sorted by address."""
    network = network or local_network()
    if network is None:
        raise RuntimeError("This computer is not on a private network, so there is nothing safe to scan.")
    if not network.is_private:
        raise RuntimeError("Only private networks are scanned.")

    cameras: dict[str, FoundCamera] = {}
    own = local_address()

    def note(host: str) -> FoundCamera:
        return cameras.setdefault(host, FoundCamera(host))

    if use_onvif:
        for host in onvif_discover(cancel=cancel, interface=own):
            try:
                if ipaddress.IPv4Address(host) in network:
                    note(host).onvif = True
            except ValueError:
                continue

    targets = [(str(host), port) for host in network.hosts() if str(host) != own for port in ports]
    total = len(targets)
    done = 0
    lock = threading.Lock()

    def probe(target: tuple[str, int]) -> tuple[str, int] | None:
        nonlocal done
        if cancel is not None and cancel.is_set():
            return None
        host, port = target
        hit = (host, port) if port_open(host, port, timeout) else None
        with lock:
            done += 1
            current = done
        if progress is not None and (current % 20 == 0 or current == total):
            progress(current, total)
        return hit

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for hit in pool.map(probe, targets):
            if hit:
                note(hit[0]).ports.add(hit[1])
    return sorted(cameras.values(), key=FoundCamera.sort_key)
