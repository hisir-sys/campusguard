"""CSV camera import: every row is checked before anything is added."""
from __future__ import annotations

import pytest

from campusguard.camera_import import (
    MAX_ROWS,
    camera_key,
    compose_address,
    decode_csv,
    parse_camera_csv,
    parse_flag,
    parse_sensitivity,
    template_csv,
)
from campusguard.settings import SENSITIVITY_LEVELS


def _by_name(plan):
    return {row.name: row for row in plan.rows}


def test_the_template_is_a_valid_file_whose_examples_are_ignored_until_uncommented():
    plan = parse_camera_csv(template_csv())
    assert not plan.problem and plan.rows == [] and "example" in plan.summary().lower()
    lines = template_csv().splitlines()
    uncommented = "\r\n".join([lines[0]] + [line.replace("# ", "", 1) for line in lines[2:]])  # drop the instructions row
    plan = parse_camera_csv(uncommented)
    assert [row.name for row in plan.rows] == ["Main Gate", "Library Corridor", "Parking", "Office webcam"]
    assert all(row.ready for row in plan.rows), [row.status for row in plan.rows]


def test_a_full_row_becomes_the_values_the_add_camera_form_produces():
    plan = parse_camera_csv(
        "name,type,address,port,path,username,password,group,sensitivity,ai\n"
        "Main Gate,RTSP,192.168.1.64,554,Streaming/Channels/101,admin,p@ss;w d,Entrances,Sensitive,no\n"
    )
    row = plan.rows[0]
    assert row.ready and row.status == "Ready"
    assert row.values() == {
        "name": "Main Gate",
        "source_type": "RTSP",
        "source_address": "rtsp://192.168.1.64:554/Streaming/Channels/101",  # no credentials in the address
        "username": "admin",
        "password": "p@ss;w d",
        "group_name": "Entrances",
        "threshold_offset": -0.10,
        "ai_enabled": False,
    }


def test_headers_are_matched_loosely_and_unknown_columns_are_reported_not_lost():
    plan = parse_camera_csv(
        "﻿Camera Name; IP-Address; Source_Type; Zone / Group; Floor; Notes\n"
        "Gate;192.168.1.5;rtsp;Block A;2;main\n"
    )
    row = plan.rows[0]
    assert plan.delimiter == ";" and row.name == "Gate" and row.group_name == "Block A"
    assert row.source_address == "rtsp://192.168.1.5:554/stream1" and "using /stream1" in row.status
    assert plan.ignored_columns == ["Floor", "Notes"]


def test_missing_name_or_address_column_gives_a_clear_file_level_error():
    for text in ("type,address\nRTSP,1.2.3.4\n", "name,type\nGate,RTSP\n", "foo,bar\n1,2\n"):
        plan = parse_camera_csv(text)
        assert plan.problem and "first row" in plan.problem and not plan.rows
    assert parse_camera_csv("").problem == "The file is empty."
    assert parse_camera_csv("\n\n,,\n").problem == "The file is empty."


def test_each_bad_row_says_what_is_wrong_and_good_rows_still_import():
    plan = parse_camera_csv(
        "name,type,address,username,password,sensitivity,ai\n"
        "Good,RTSP,rtsp://192.168.1.2:554/s,,,,\n"
        "NoAddress,RTSP,,,,,\n"
        "BadIp,RTSP,rtsp://999.1.1.1/x,,,,\n"
        "BadType,FTP,192.168.1.4,,,,\n"
        "NoType,,192.168.1.5,,,,\n"
        "UrlCreds,RTSP,rtsp://admin:pw@192.168.1.6/x,,,,\n"
        "UsbCreds,USB,1,admin,pw,,\n"
        "BadSens,RTSP,192.168.1.7,,,loud,\n"
        "BadAi,RTSP,192.168.1.8,,,,maybe\n"
        ",RTSP,192.168.1.9,,,,\n"
    )
    rows = _by_name(plan)
    assert rows["Good"].ready
    assert "address" in rows["NoAddress"].status.lower()
    assert "not a valid IP" in rows["BadIp"].status
    assert "FTP" in rows["BadType"].status
    assert "Type is missing" in rows["NoType"].status
    assert "credentials" in rows["UrlCreds"].status.lower()
    assert "username or password" in rows["UsbCreds"].status
    assert "Sensitivity" in rows["BadSens"].status and "AI must be yes or no" in rows["BadAi"].status
    assert "Name is missing" in rows[""].status
    assert [row.name for row in plan.ready] == ["Good"]
    assert len(plan.with_problems) == 9
    assert plan.summary() == "1 ready · 9 need fixing"
    # a row's problems are always reported against the line it came from
    assert [row.line for row in plan.rows][:3] == [2, 3, 4]


def test_repeats_and_cameras_that_already_exist_are_skipped_not_added_twice():
    plan = parse_camera_csv(
        "name,type,address\n"
        "A,RTSP,rtsp://192.168.1.2/stream1\n"
        "A again,RTSP,192.168.1.2:554/stream1\n"
        "Webcam,USB,0\n"
        "Webcam copy,usb,0\n"
        "Old one,IP,192.168.1.50:8080/video\n",
        existing=[("Front door", "HTTP", "http://192.168.1.50:8080/video")],
    )
    rows = _by_name(plan)
    assert rows["A"].ready and rows["Webcam"].ready
    assert rows["A again"].skip_reason == "Same camera as line 2."
    assert rows["Webcam copy"].skip_reason == "Same camera as line 4."
    assert rows["Old one"].skip_reason == "Already added as Front door."
    assert not rows["Old one"].ready and rows["Old one"] in plan.skipped
    assert plan.summary() == "2 ready · 3 already added or repeated"


def test_camera_key_ignores_how_the_same_address_was_typed():
    assert camera_key("RTSP", "rtsp://10.0.0.5/s") == camera_key("RTSP", "rtsp://10.0.0.5:554/s")
    assert camera_key("IP", "10.0.0.5:8080/video") == camera_key("HTTP", "http://10.0.0.5:8080/video/")
    assert camera_key("IP", "10.0.0.5:80/video") == camera_key("HTTP", "http://10.0.0.5/video")
    assert camera_key("USB", "0") == camera_key("usb", " 0 ") != camera_key("USB", "1")
    assert camera_key("RTSP", "rtsp://10.0.0.5/a") != camera_key("RTSP", "rtsp://10.0.0.5/b")


@pytest.mark.parametrize(
    "source_type,address,port,path,expected",
    [
        ("RTSP", "192.168.1.64", "", "", "rtsp://192.168.1.64:554/stream1"),
        ("RTSP", "192.168.1.64", "8554", "live/ch1", "rtsp://192.168.1.64:8554/live/ch1"),
        ("RTSP", "192.168.1.64:7447/abc", "", "", "rtsp://192.168.1.64:7447/abc"),
        ("RTSP", "cam.school.in", "", "cam/realmonitor?channel=1&subtype=0", "rtsp://cam.school.in:554/cam/realmonitor?channel=1&subtype=0"),
        ("RTSP", "[2001:db8::1]", "", "/s", "rtsp://[2001:db8::1]:554/s"),
        ("RTSP", "2001:db8::1", "", "/s", "rtsp://[2001:db8::1]:554/s"),
        ("RTSP", "rtsp://192.168.1.65/stream1", "8554", "", "rtsp://192.168.1.65:8554/stream1"),
        ("RTSP", "rtsp://192.168.1.65:554/stream1", "8554", "other", "rtsp://192.168.1.65:554/stream1"),
        ("IP", "192.168.1.70", "8080", "video", "http://192.168.1.70:8080/video"),
        ("IP", "192.168.1.70:8080/video", "9999", "other", "192.168.1.70:8080/video"),
        ("HTTP", "http://cam.school.in/mjpeg", "", "", "http://cam.school.in/mjpeg"),
        ("USB", "0", "554", "x", "0"),
    ],
)
def test_port_and_path_columns_fill_gaps_but_never_override_the_address(source_type, address, port, path, expected):
    assert compose_address(source_type, address, port, path)[0] == expected


def test_a_bad_port_column_is_an_error_on_that_row_only():
    plan = parse_camera_csv("name,type,address,port\nA,RTSP,192.168.1.2,abc\nB,RTSP,192.168.1.3,70000\nC,RTSP,192.168.1.4,554\n")
    assert [row.ready for row in plan.rows] == [False, False, True]
    assert "port" in plan.rows[0].status.lower()


def test_type_is_read_from_an_explicit_address_when_the_cell_is_blank():
    plan = parse_camera_csv("name,type,address\nA,,rtsp://192.168.1.2/s\nB,,http://192.168.1.3/v\nC,,0\nD,,192.168.1.4\n")
    assert [row.source_type for row in plan.rows[:3]] == ["RTSP", "HTTP", "USB"]
    assert plan.rows[3].problems  # a bare address could be RTSP or an IP webcam, so it asks instead of guessing


@pytest.mark.parametrize(
    "word,offset",
    [("", 0.0), ("Default", 0.0), ("sensitive", -0.10), ("High", -0.10), ("Sensitive (more alerts)", -0.10),
     ("cautious", 0.10), ("Low", 0.10), ("Strict", 0.20), ("Very low", 0.20), ("-0.1", -0.10), ("0,2", 0.20), ("0.1", 0.10)],
)
def test_sensitivity_words_and_numbers(word, offset):
    assert parse_sensitivity(word) == pytest.approx(offset)
    assert parse_sensitivity(word) in [float(level[1]) for level in SENSITIVITY_LEVELS]


@pytest.mark.parametrize("word", ["loud", "5", "-3", "1.0"])
def test_sensitivity_rejects_what_it_cannot_place(word):
    with pytest.raises(ValueError, match="Sensitivity"):
        parse_sensitivity(word)


def test_ai_flag_defaults_to_on():
    assert parse_flag("") and parse_flag("Yes") and parse_flag("TRUE") and parse_flag("1")
    assert not parse_flag("no") and not parse_flag("Off") and not parse_flag("0")
    with pytest.raises(ValueError):
        parse_flag("maybe")


def test_quoted_cells_blank_lines_comments_and_ragged_rows():
    plan = parse_camera_csv(
        'name,type,address,username,password,group\r\n'
        '"Gate, North",RTSP,192.168.1.2,admin,"pa""ss, word",\r\n'
        '\r\n'
        '# a note,,\r\n'
        ',,,\r\n'
        'Short,RTSP,192.168.1.3\r\n'
    )
    assert [row.name for row in plan.rows] == ["Gate, North", "Short"]
    assert plan.rows[0].password == 'pa"ss, word' and plan.rows[0].ready and plan.rows[1].ready
    assert plan.rows[1].username == "" and plan.rows[1].group_name == ""
    assert [row.line for row in plan.rows] == [2, 6]  # the lines you would see in a text editor


def test_passwords_keep_their_spaces_but_names_are_tidied():
    plan = parse_camera_csv("name,type,address,password\n  Front   Door ,RTSP,192.168.1.2, spaced pw \n")
    assert plan.rows[0].name == "Front Door" and plan.rows[0].password == " spaced pw "


def test_files_that_are_not_csv_text_are_refused_with_advice():
    assert "Excel workbook" in parse_camera_csv(b"PK\x03\x04 binary").problem
    assert "too large" in parse_camera_csv(b"a" * 1_000_001).problem
    assert "CSV text" in parse_camera_csv("name,address\n\x00\x00\n").problem
    many = "name,type,address\n" + "".join(f"C{i},RTSP,10.0.{i // 250}.{i % 250 + 1}\n" for i in range(MAX_ROWS + 1))
    assert f"at most {MAX_ROWS}" in parse_camera_csv(many).problem


def test_excel_code_page_files_are_read_correctly():
    data = "name,type,address,group\nCafé gate,RTSP,192.168.1.2,Zone É\n".encode("cp1252")
    assert decode_csv(data).startswith("name") and "Café" in decode_csv(data)
    row = parse_camera_csv(data).rows[0]
    assert row.name == "Café gate" and row.group_name == "Zone É"
    utf8 = "﻿name,type,address\nGate,RTSP,192.168.1.2\n".encode("utf-8")
    assert parse_camera_csv(utf8).rows[0].name == "Gate"


def test_internet_addresses_are_accepted():
    row = parse_camera_csv("name,type,address,path\nRemote,RTSP,8.8.8.8,live\n").rows[0]
    assert row.ready and row.source_address == "rtsp://8.8.8.8:554/live"
