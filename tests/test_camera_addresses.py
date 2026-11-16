"""Camera addresses: any IP or host name is accepted, credentials stay out of the URL."""
from __future__ import annotations

import pytest

from campusguard.settings import CameraCredentials
from campusguard.sources import (
    address_host,
    build_capture_source,
    build_rtsp_url,
    host_problem,
    is_internet_address,
    is_valid_host,
)


@pytest.mark.parametrize(
    "host",
    ["8.8.8.8", "192.168.1.50", "10.0.0.5", "203.0.113.7", "cam1.school.in", "cam-1.school.in", "[2001:db8::1]", "2001:db8::1", "frontdoor"],
)
def test_public_private_and_host_names_are_all_valid(host):
    assert host_problem(host) is None and is_valid_host(host)


@pytest.mark.parametrize("host", ["", "999.1.1.1", "1.2.3", "bad_host!", "-bad.example.com", "a" * 64 + ".com", "[::g]"])
def test_invalid_hosts_say_why(host):
    problem = host_problem(host)
    assert problem and problem.endswith(".")


def test_public_ip_is_accepted_by_every_source_type():
    assert build_capture_source("RTSP", "rtsp://8.8.8.8:554/live") == "rtsp://8.8.8.8:554/live"
    assert build_capture_source("IP", "8.8.8.8:8080/video") == "http://8.8.8.8:8080/video"
    assert build_capture_source("HTTP", "http://cam.school.in/mjpeg") == "http://cam.school.in/mjpeg"
    assert build_capture_source("RTSP", "rtsp://[2001:db8::1]:8554/s") == "rtsp://[2001:db8::1]:8554/s"


def test_credentials_are_percent_encoded_and_never_typed_into_the_url():
    url = build_capture_source("RTSP", "rtsp://8.8.8.8:554/live", CameraCredentials("admin", "p@ss/w:rd"))
    assert url == "rtsp://admin:p%40ss%2Fw%3Ard@8.8.8.8:554/live"
    with pytest.raises(ValueError, match="credentials"):
        build_capture_source("RTSP", "rtsp://admin:pw@8.8.8.8/live")


@pytest.mark.parametrize(
    "source_type,address,fragment",
    [
        ("RTSP", "rtsp://999.1.1.1/x", "not a valid IP"),
        ("RTSP", "rtsp://host:abc/x", "port"),
        ("RTSP", "rtsp://host:0/x", "port"),
        ("RTSP", "rtsp://bad_host!/x", "valid host"),
        ("RTSP", "rtsp://[::1/x", "not valid"),
        ("RTSP", "http://8.8.8.8/x", "rtsp"),
        ("USB", "-1", "zero"),
    ],
)
def test_bad_addresses_raise_a_readable_error(source_type, address, fragment):
    with pytest.raises(ValueError) as error:
        build_capture_source(source_type, address)
    assert fragment.lower() in str(error.value).lower()


def test_build_rtsp_url_encodes_and_validates():
    assert build_rtsp_url("10.0.0.5", 554, "admin", "p@ss word", "Streaming/Channels/101") == (
        "rtsp://admin:p%40ss%20word@10.0.0.5:554/Streaming/Channels/101"
    )
    assert build_rtsp_url("8.8.8.8", 8554) == "rtsp://8.8.8.8:8554/stream1"
    assert build_rtsp_url("2001:db8::1", 554, path="/s") == "rtsp://[2001:db8::1]:554/s"
    assert build_rtsp_url("cam.school.in", 554, secure=True, path="/").startswith("rtsps://")
    for bad_port in (0, 70000, "abc"):
        with pytest.raises(ValueError, match="port"):
            build_rtsp_url("8.8.8.8", bad_port)
    with pytest.raises(ValueError):
        build_rtsp_url("999.1.1.1")


def test_internet_addresses_are_told_apart_from_local_ones():
    assert is_internet_address("8.8.8.8") and is_internet_address("cam.school.in")
    assert is_internet_address("[2606:4700::1111]")
    for local in ("192.168.1.5", "10.1.2.3", "172.16.0.9", "127.0.0.1", "cam.local", "nvr.lan", "frontdoor", "", "999.9.9.9"):
        assert not is_internet_address(local), local


def test_address_host_reads_the_host_as_typed():
    assert address_host("RTSP", "rtsp://admin:p%40ss@8.8.8.8:554/live") == "8.8.8.8"
    assert address_host("IP", "192.168.1.5:8080/video") == "192.168.1.5"
    assert address_host("USB", "1") == "" and address_host("HTTP", "") == "" and address_host("RTSP", "rtsp://[::1/x") == ""
