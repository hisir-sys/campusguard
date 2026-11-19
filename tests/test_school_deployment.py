"""Quiet hours, smooth incident clips, per-building alerts, health notices and the camera cap."""
from __future__ import annotations

from datetime import datetime, time as dtime
from pathlib import Path

import cv2
import numpy as np
import pytest

from campusguard.camera_import import parse_camera_csv
from campusguard.evidence import EvidenceRecorder, EvidenceRing
from campusguard.health_watch import HealthWatch
from campusguard.notify import AlertDispatcher, AlertInfo, AlertPlan, parse_building_numbers
from campusguard.server.config import ServerConfig, normalise
from campusguard.server.csv_import import parse_cameras_csv
from campusguard.settings import AppSettings, CameraConfig
from campusguard.tuning import clamp_post_roll, clamp_pre_roll, in_quiet_hours, normalise_quiet_window, parse_hhmm


# ---------------------------------------------------------------- quiet hours
def test_quiet_hours_inside_and_outside_a_same_day_window():
    assert in_quiet_hours("13:00", "14:00", dtime(13, 30))
    assert not in_quiet_hours("13:00", "14:00", dtime(14, 0))      # the end is exclusive
    assert in_quiet_hours("13:00", "14:00", dtime(13, 0))


def test_quiet_hours_cross_midnight():
    assert in_quiet_hours("22:00", "06:00", dtime(23, 30))
    assert in_quiet_hours("22:00", "06:00", dtime(2, 0))
    assert not in_quiet_hours("22:00", "06:00", dtime(12, 0))
    assert in_quiet_hours("22:00", "06:00", datetime(2026, 11, 17, 5, 59))


def test_incomplete_or_bad_quiet_hours_never_pause_the_ai():
    assert not in_quiet_hours("", "", dtime(3, 0))
    assert not in_quiet_hours("22:00", "", dtime(23, 0))
    assert not in_quiet_hours("25:00", "06:00", dtime(1, 0))
    assert not in_quiet_hours("08:00", "08:00", dtime(8, 0))
    assert parse_hhmm("7.05") == dtime(7, 5) and parse_hhmm("noon") is None
    assert normalise_quiet_window("7:00", "") == ("", "")
    assert normalise_quiet_window("7:00", "19:30") == ("07:00", "19:30")


def test_roll_lengths_fall_back_to_the_default_and_stay_in_range():
    assert clamp_pre_roll(0, 5.0) == 5.0 and clamp_pre_roll("x", 5.0) == 5.0
    assert clamp_pre_roll(99) == 15.0 and clamp_post_roll(99) == 30.0
    assert clamp_pre_roll(0.2, 5.0) == 1.0


def test_runtime_options_pause_ai_in_quiet_hours_and_report_roll_lengths(monkeypatch):
    from campusguard.camera_runtime import RuntimeOptions

    # Patch the globals the class really uses (other tests may have reloaded the module object).
    namespace = RuntimeOptions.snapshot.__globals__
    paused = RuntimeOptions(AppSettings(), True, 0.0, "22:00", "06:00")
    monkeypatch.setitem(namespace, "in_quiet_hours", lambda start, end: True)
    assert paused.snapshot()[1] is False                 # quiet right now: AI paused
    monkeypatch.setitem(namespace, "in_quiet_hours", lambda start, end: False)
    assert paused.snapshot()[1] is True                  # outside the window: watching again
    never = RuntimeOptions(AppSettings(), True, 0.0, "", "", 0.0, 0.0)
    assert never.snapshot()[1] is True
    assert never.roll_seconds() == (5.0, 8.0)
    never.update_tuning("", "", 10.0, 20.0)
    assert never.roll_seconds() == (10.0, 20.0)
    off = RuntimeOptions(AppSettings(), False)
    assert off.snapshot()[1] is False


# ---------------------------------------------------------------- smooth clips
def _frame(value: int, width: int = 640, height: int = 360) -> np.ndarray:
    return np.full((height, width, 3), value, dtype=np.uint8)


def test_ring_keeps_every_frame_at_the_clip_rate_and_thins_faster_cameras():
    ring = EvidenceRing(fps=20)
    kept = sum(ring.push(_frame(i), t=i * 0.04) for i in range(50))       # 25 fps camera
    assert 38 <= kept <= 42                                              # about 20 per second for 2 s
    assert ring.measured_fps() == pytest.approx(20, abs=2)


def test_ring_is_bounded_by_age_and_size():
    ring = EvidenceRing(fps=20, keep_seconds=2.0)
    for i in range(200):
        ring.push(_frame(i % 255), t=i * 0.05)
    times = [t for t, _ in ring.since(0)]
    assert times[-1] - times[0] <= 2.05
    small = EvidenceRing(fps=20, keep_seconds=100.0, max_bytes=20_000)
    for i in range(100):
        small.push(np.random.randint(0, 255, (360, 640, 3), dtype=np.uint8), t=i * 0.05)
    assert small.byte_count <= 20_000 + 400_000       # never more than one frame over the cap
    assert small.frame_count >= 1


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_clip_has_pre_roll_the_incident_and_post_roll_and_plays_smoothly(tmp_path: Path):
    clock = Clock()
    ring = EvidenceRing(fps=20)
    recorder = EvidenceRecorder(tmp_path, ring, pre_seconds=3.0, post_seconds=4.0, clock=clock)
    finished = None
    # 20 s of 20 fps video; the AI only "looks" once a second, yet the clip must still hold every frame.
    for i in range(20 * 20):
        clock.now = 1000.0 + i * 0.05
        ring.push(_frame(i % 250), t=clock.now)
        if i % 20 == 0:
            state = "FIGHT DETECTED" if 160 <= i < 200 else "NORMAL"       # fight from 8 s to 10 s
            started = i == 160
            result = recorder.update(state, started)
            finished = result or finished
    assert finished is not None and finished.is_file()
    capture = cv2.VideoCapture(str(finished))
    frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = capture.get(cv2.CAP_PROP_FPS)
    capture.release()
    seconds = frames / fps
    assert fps == pytest.approx(20, abs=2)
    # 3 s before + 2 s fight + about 4 s after (the AI only checks once a second)
    assert 7.0 <= seconds <= 11.0
    assert frames > 120                              # far more than the 20 frames the AI examined


def test_stop_finishes_a_clip_in_progress_and_idle_recorder_returns_nothing(tmp_path: Path):
    clock = Clock()
    ring = EvidenceRing(fps=20)
    recorder = EvidenceRecorder(tmp_path, ring, clock=clock)
    assert recorder.stop() is None and not recorder.active
    for i in range(60):
        clock.now = 50.0 + i * 0.05
        ring.push(_frame(i), t=clock.now)
    recorder.update("FIGHT DETECTED", True)
    assert recorder.active
    clip = recorder.stop()
    assert clip is not None and clip.is_file() and not recorder.active


def test_no_frames_means_no_empty_file(tmp_path: Path):
    recorder = EvidenceRecorder(tmp_path, EvidenceRing(), clock=Clock())
    recorder.update("FIGHT DETECTED", True)
    assert recorder.stop() is None
    assert list(tmp_path.glob("*.mp4")) == []


# ---------------------------------------------------------------- alert routing
def info(group: str, severity: str = "HIGH") -> AlertInfo:
    return AlertInfo("INC-1", "Corridor 2", "cam-2", 0.9, severity, datetime(2026, 11, 17, 11, 0), None, group)


def test_building_numbers_parse_one_building_per_line():
    routes = parse_building_numbers("Main Building: 98765 43210, 91234 56789\nBlock B = 99999 88888\nnonsense\nBlock C: abc")
    assert routes == (
        ("main building", ("919876543210", "919123456789")),
        ("block b", ("919999988888",)),
    )
    assert parse_building_numbers("") == ()


def test_headmistress_gets_every_alert_and_the_building_is_added():
    plan = AlertPlan(
        numbers=("911111111111",), whatsapp_mode="cloud",
        building_numbers=parse_building_numbers("Block B: 92222 22222"),
    )
    assert plan.recipients(info("Block B")) == ("911111111111", "919222222222")
    assert plan.recipients(info("  block   b ")) == ("911111111111", "919222222222")   # case and spaces
    assert plan.recipients(info("Main Building")) == ("911111111111",)
    assert plan.recipients(info("")) == ("911111111111",)


def test_nobody_gets_the_same_alert_twice_and_escalation_uses_its_own_list():
    plan = AlertPlan(
        numbers=("911111111111",), escalation_numbers=("913333333333",),
        building_numbers=(("block b", ("911111111111", "922222222222")),),
    )
    assert plan.recipients(info("Block B")) == ("911111111111", "922222222222")
    assert plan.recipients(info("Block B"), escalated=True) == ("913333333333",)


def test_building_only_plan_is_active_even_without_a_head_number():
    plan = AlertPlan(whatsapp_mode="cloud", building_numbers=(("block b", ("922222222222",)),))
    assert plan.active
    assert not AlertPlan(whatsapp_mode="off", building_numbers=(("block b", ("922222222222",)),)).active


def test_dispatcher_sends_to_head_and_building(monkeypatch):
    import campusguard.notify as notify

    sent: list[str] = []
    monkeypatch.setattr(notify, "send_whatsapp_cloud", lambda phone, token, number, *a, **k: (sent.append(number) or (True, "ok")))
    dispatcher = AlertDispatcher()
    plan = AlertPlan(numbers=("911111111111",), whatsapp_mode="cloud", phone_id="p", token="t",
                     building_numbers=(("block b", ("922222222222",)),))
    dispatcher._send_all(plan, info("Block B"), False)
    assert sent == ["911111111111", "922222222222"]


# ---------------------------------------------------------------- health notices
def snap(**states: str) -> dict:
    return {camera_id: {"health": state} for camera_id, state in states.items()}


def test_one_message_per_outage_then_one_when_it_recovers():
    watch = HealthWatch(offline_after_seconds=300, label="Block B")
    names = {"c1": "Gate", "c2": "Lab"}
    assert watch.evaluate(snap(c1="offline", c2="ok"), names, 100, now=0) == []
    assert watch.evaluate(snap(c1="offline", c2="ok"), names, 100, now=299) == []
    first = watch.evaluate(snap(c1="offline", c2="ok"), names, 100, now=301)
    assert len(first) == 1 and "Gate" in first[0].text and "Block B" in first[0].title
    assert watch.evaluate(snap(c1="offline", c2="ok"), names, 100, now=900) == []      # no repeats
    back = watch.evaluate(snap(c1="ok", c2="ok"), names, 100, now=1000)
    assert len(back) == 1 and back[0].kind == "cameras_recovered"
    assert watch.evaluate(snap(c1="ok", c2="ok"), names, 100, now=1100) == []


def test_a_short_blip_is_never_reported():
    watch = HealthWatch(offline_after_seconds=300)
    watch.evaluate(snap(c1="stalled"), {"c1": "Gate"}, None, now=0)
    assert watch.evaluate(snap(c1="ok"), {"c1": "Gate"}, None, now=100) == []


def test_many_cameras_dropping_at_once_is_one_message():
    watch = HealthWatch(offline_after_seconds=60)
    names = {f"c{i}": f"Cam {i}" for i in range(40)}
    watch.evaluate(snap(**{k: "offline" for k in names}), names, None, now=0)
    notices = watch.evaluate(snap(**{k: "offline" for k in names}), names, None, now=61)
    assert len(notices) == 1 and "40 of 40" in notices[0].text and "switch" in notices[0].text
    assert notices[0].text.count("Cam ") <= 8                 # names are summarised, not dumped


def test_low_disk_warns_once_and_clears_with_some_headroom():
    watch = HealthWatch(min_free_gb=20)
    assert len(watch.evaluate({}, {}, 10, now=0)) == 1
    assert watch.evaluate({}, {}, 9, now=10) == []
    assert watch.evaluate({}, {}, 21, now=20) == []           # not yet comfortably above the limit
    cleared = watch.evaluate({}, {}, 30, now=30)
    assert len(cleared) == 1 and cleared[0].kind == "disk_ok"


def test_removed_cameras_do_not_linger_in_the_watch():
    watch = HealthWatch(offline_after_seconds=10)
    watch.evaluate(snap(c1="offline"), {"c1": "Gate"}, None, now=0)
    watch.evaluate({}, {}, None, now=5)
    assert watch.evaluate(snap(c1="offline"), {"c1": "Gate"}, None, now=8) == []      # clock restarted


# ---------------------------------------------------------------- settings, import, capacity
def test_settings_clamp_the_new_values():
    settings = AppSettings.from_dict({
        "default_pre_roll_seconds": 99, "default_post_roll_seconds": -1, "clip_fps": 120, "clip_width": 10,
        "health_offline_minutes": 0, "health_min_disk_gb": "nonsense",
    })
    assert settings.default_pre_roll_seconds == 15.0
    assert settings.default_post_roll_seconds == 1.0
    assert settings.clip_fps == 30 and settings.clip_width == 480
    assert settings.health_offline_minutes == 1 and settings.health_min_disk_gb == 20


def test_desktop_csv_reads_the_building_and_tuning_columns():
    plan = parse_camera_csv(
        "name,type,address,group,quiet_start,quiet_end,pre_roll,post_roll\n"
        "Gym,RTSP,192.168.1.9,Sports Block,22:00,06:00,6,15\n"
        "Bad,RTSP,192.168.1.10,Main,22:00,,,\n"
        "Slow,RTSP,192.168.1.11,Main,,,99,\n"
    )
    gym, bad, slow = plan.rows
    assert gym.ready and gym.values()["quiet_start"] == "22:00" and gym.values()["pre_roll_seconds"] == 6.0
    assert gym.values()["post_roll_seconds"] == 15.0 and gym.values()["group_name"] == "Sports Block"
    assert not bad.ready and "Quiet hours" in bad.status
    assert not slow.ready and "pre_roll" in slow.status


def test_desktop_csv_accepts_a_whole_school():
    rows = "".join(f"C{i},RTSP,10.{i // 250}.{i % 250}.5,Block {i % 4}\n" for i in range(800))
    plan = parse_camera_csv("name,type,address,group\n" + rows)
    assert not plan.problem and len(plan.rows) == 800


def test_server_csv_reads_building_sensitivity_and_tuning():
    plan = parse_cameras_csv(
        "name,type,address,building,sensitivity,quiet_start,quiet_end,pre_roll,post_roll\n"
        "Hall,RTSP,rtsp://10.0.0.5/s,Block C,cautious,21:00,05:30,4,12\n"
        "Odd,RTSP,rtsp://10.0.0.6/s,Block C,zzz,,,,\n"
    )
    assert len(plan.valid) == 1 and len(plan.errors) == 1
    hall = plan.valid[0]
    assert (hall.group_name, hall.threshold_offset, hall.quiet_start, hall.quiet_end) == ("Block C", 0.10, "21:00", "05:30")
    assert (hall.pre_roll_seconds, hall.post_roll_seconds) == (4.0, 12.0)
    assert "sensitivity" in plan.errors[0]["error"].lower()


def test_camera_limit_per_server_is_configurable_and_bounded():
    assert ServerConfig().max_cameras == 250
    assert normalise({"max_cameras": 150}).max_cameras == 150
    assert normalise({"max_cameras": 1000}).max_cameras == 1000
    assert normalise({"max_cameras": 0}).max_cameras == 1
    assert normalise({"max_cameras": 999999}).max_cameras == 2000
    assert normalise({"max_cameras": "x"}).max_cameras == 250


def test_camera_tuning_is_saved_and_reloaded(tmp_path: Path):
    from campusguard.storage import Repository

    repository = Repository(footage_dir=tmp_path / "clips")
    camera = repository.add_camera("Gym", "RTSP", "rtsp://10.0.0.5/s", True)
    saved = repository.set_camera_tuning(camera.camera_id, "22:00", "06:00", 6, 15)
    assert saved == ("22:00", "06:00", 6.0, 15.0)
    loaded = [c for c in repository.list_cameras() if c.camera_id == camera.camera_id][0]
    assert (loaded.quiet_start, loaded.quiet_end, loaded.pre_roll_seconds, loaded.post_roll_seconds) == ("22:00", "06:00", 6.0, 15.0)
    assert repository.set_camera_tuning(camera.camera_id, "22:00", "", 0, 0) == ("", "", 0.0, 0.0)   # half a window is dropped
    assert isinstance(loaded, CameraConfig)


def test_settings_page_keeps_hidden_settings_and_saves_new_numbers():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from campusguard.settings import AppSettings
    from campusguard.ui.settings_page import SettingsPage

    QApplication.instance() or QApplication([])
    page = SettingsPage(AppSettings(clip_fps=12, default_pre_roll_seconds=7, health_min_disk_gb=33))
    got = []
    page.settings_changed.connect(got.append)
    page.building_numbers_input.setPlainText("Science: 9876543210")
    page.health_numbers_input.setText("9876500000")
    page.health_offline_input.setValue(9)
    page._emit_settings()
    s = got[-1]
    assert (s.clip_fps, s.default_pre_roll_seconds, s.health_min_disk_gb) == (12, 7, 33)
    assert s.building_numbers == "Science: 9876543210" and s.health_numbers == "9876500000"
    assert s.health_offline_minutes == 9
