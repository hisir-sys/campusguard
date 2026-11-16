"""Network discovery: ONVIF reply parsing, local-network detection and the port scan."""
from __future__ import annotations

import ipaddress
import socket
import threading

import pytest

from campusguard import camera_discovery as discovery
from campusguard.camera_discovery import FoundCamera


def test_local_network_is_the_private_slash_24_only():
    assert discovery.local_network("192.168.1.20") == ipaddress.ip_network("192.168.1.0/24")
    assert discovery.local_network("10.4.7.9") == ipaddress.ip_network("10.4.7.0/24")
    for unsafe in ("8.8.8.8", "169.254.1.1", "127.0.0.1", "not-an-ip", ""):
        assert discovery.local_network(unsafe) is None


def test_probe_match_prefers_the_advertised_address_and_falls_back_to_the_sender():
    reply = b'<d:ProbeMatch><d:XAddrs>http://192.168.1.64:80/onvif/device_service http://[fe80::1]/x</d:XAddrs></d:ProbeMatch>'
    assert discovery.parse_probe_match(reply, "192.168.1.99") == "192.168.1.64"
    assert discovery.parse_probe_match(b"<nothing/>", "192.168.1.99") == "192.168.1.99"
    assert discovery.parse_probe_match(b"\xff\xfe garbage", "192.168.1.7") == "192.168.1.7"
    # no port, several URLs, link-local first, IPv6 only, invalid octets
    assert discovery.parse_probe_match(b"<d:XAddrs>http://192.168.1.64/onvif/device_service</d:XAddrs>", "1.1.1.1") == "192.168.1.64"
    assert discovery.parse_probe_match(b"<w:XAddrs>http://169.254.7.7/o http://10.0.0.8:8080/o</w:XAddrs>", "1.1.1.1") == "10.0.0.8"
    assert discovery.parse_probe_match(b"<d:XAddrs>http://[fe80::1]/x</d:XAddrs>", "192.168.1.7") == "192.168.1.7"
    assert discovery.parse_probe_match(b"<d:XAddrs>http://999.1.1.1/x</d:XAddrs>", "192.168.1.7") == "192.168.1.7"


def test_found_camera_labels_and_sorting():
    both = FoundCamera("192.168.1.9", {8554, 554}, True)
    assert both.found_by == "ONVIF, port 554/8554" and both.port == 554
    assert FoundCamera("192.168.1.5", {554}).found_by == "Port 554"
    assert FoundCamera("192.168.1.6", set(), True).found_by == "ONVIF" and FoundCamera("192.168.1.6", set(), True).port == 554
    ordered = sorted([FoundCamera("192.168.1.100"), FoundCamera("192.168.1.20"), FoundCamera("192.168.1.3")], key=FoundCamera.sort_key)
    assert [camera.host for camera in ordered] == ["192.168.1.3", "192.168.1.20", "192.168.1.100"]


def test_onvif_probe_never_raises_when_multicast_is_blocked(monkeypatch):
    real = socket.socket.sendto

    def blocked(self, *args, **kwargs):
        raise OSError("network unreachable")

    monkeypatch.setattr(socket.socket, "sendto", blocked)
    assert discovery.onvif_discover(timeout=0.2) == set()
    monkeypatch.setattr(socket.socket, "sendto", real)
    assert isinstance(discovery.onvif_discover(timeout=0.2), set)


@pytest.fixture
def listener():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(8)
    yield server.getsockname()[1]
    server.close()


def test_port_open_tells_open_from_closed(listener):
    assert discovery.port_open("127.0.0.1", listener)
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    free_port = closed.getsockname()[1]
    closed.close()
    assert not discovery.port_open("127.0.0.1", free_port, timeout=0.3)


def test_scan_finds_the_device_with_an_open_port_and_reports_progress(listener):
    seen = []
    cameras = discovery.scan_network(
        (listener,), network=ipaddress.ip_network("127.0.0.0/24"), use_onvif=False,
        progress=lambda done, total: seen.append((done, total)), timeout=0.3,
    )
    assert [(camera.host, camera.ports) for camera in cameras] == [("127.0.0.1", {listener})]
    assert seen and seen[-1][0] == seen[-1][1]


def test_scan_stops_when_cancelled(listener):
    cancel = threading.Event()
    cancel.set()
    assert discovery.scan_network(
        (listener,), network=ipaddress.ip_network("127.0.0.0/24"), use_onvif=False, cancel=cancel
    ) == []


def test_scan_refuses_networks_that_are_not_private(monkeypatch):
    with pytest.raises(RuntimeError, match="private"):
        discovery.scan_network(network=ipaddress.ip_network("8.8.8.0/24"), use_onvif=False)
    monkeypatch.setattr(discovery, "local_network", lambda address=None: None)
    with pytest.raises(RuntimeError, match="not on a private network"):
        discovery.scan_network(use_onvif=False)


def test_onvif_hits_outside_the_scanned_network_are_ignored(monkeypatch, listener):
    monkeypatch.setattr(discovery, "onvif_discover", lambda **_kwargs: {"127.0.0.1", "10.9.9.9"})
    cameras = discovery.scan_network(
        (listener,), network=ipaddress.ip_network("127.0.0.0/24"), use_onvif=True, timeout=0.3
    )
    assert [camera.host for camera in cameras] == ["127.0.0.1"]
    assert cameras[0].onvif and cameras[0].ports == {listener}


def test_onvif_probe_is_pinned_to_the_scanned_networks_card(monkeypatch, listener):
    seen = {}
    monkeypatch.setattr(discovery, "local_address", lambda: "127.0.0.5")

    def fake_discover(timeout=3.0, cancel=None, interface=None):
        seen["interface"] = interface
        return set()

    monkeypatch.setattr(discovery, "onvif_discover", fake_discover)
    discovery.scan_network((listener,), network=ipaddress.ip_network("127.0.0.0/24"), use_onvif=True, timeout=0.3)
    assert seen["interface"] == "127.0.0.5"
    assert isinstance(discovery.onvif_discover(timeout=0.2, interface="not-an-address"), set)  # a bad value never raises
