import threading
import time

import numpy as np
import pytest

from campusguard.engine.batching import BatchClosed, BatchRunner
from campusguard.engine.gate import AdaptiveStride, CameraScheduler, MotionGate
from campusguard.engine.hardware import (
    PROFILES, HardwareInfo, read_engine_override, resolve_profile, smart_analysis_enabled,
)
from campusguard.engine.registry import ActiveCameras


def scene(offset=None, noise=0, seed=0):
    frame = np.full((360, 640, 3), 90, np.uint8)
    if offset is not None:
        frame[100:220, offset:offset + 70] = 220
    if noise:
        rng = np.random.default_rng(seed)
        frame = np.clip(frame.astype(int) + rng.integers(-noise, noise + 1, frame.shape), 0, 255).astype(np.uint8)
    return frame


class Clock:
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t
    def advance(self, s): self.t += s


def test_gate_still_scene_is_quiet_and_motion_is_seen():
    gate = MotionGate()
    assert gate.has_motion(scene())            # first frame: unknown -> motion
    assert not gate.has_motion(scene())
    assert not gate.has_motion(scene(noise=3, seed=1))   # sensor noise ignored
    assert gate.has_motion(scene(offset=200))
    assert gate.has_motion(scene(offset=260))


def test_gate_treats_empty_frame_as_motion():
    assert MotionGate().has_motion(np.zeros((0, 0, 3), np.uint8))


def test_gate_sees_small_distant_person():
    gate = MotionGate()
    gate.has_motion(scene())
    small = scene()
    small[150:190, 300:316] = 230   # ~16x40 px person in a 640x360 frame
    assert gate.has_motion(small)


def make_scheduler(clock, **kw):
    return CameraScheduler(smart_analysis=kw.pop("smart", True), hangover_s=5.0, gate_hz=10.0, clock=clock, **kw)


def test_scheduler_sleeps_after_hangover_and_wakes_on_motion():
    clock = Clock()
    sched = make_scheduler(clock)
    first = sched.plan(scene(), True, False)
    assert first.active and first.analyze            # first frame analysed (like before)
    # still scene: stays active through the hangover, then goes idle exactly once
    entered = []
    for _ in range(100):
        clock.advance(0.1)
        plan = sched.plan(scene(), True, False)
        entered.append(plan.entered_idle)
        if not plan.active:
            break
    assert not plan.active and not plan.analyze
    assert sum(entered) == 1
    assert 5.0 <= clock.t - 100.0 <= 6.0
    later = [sched.plan(scene(), True, False) for _ in range(5)]
    assert not any(p.active or p.entered_idle for p in later)
    # motion wakes it immediately and analysis starts on the first active frame
    clock.advance(0.2)
    woke = sched.plan(scene(offset=300), True, False)
    assert woke.active and woke.analyze and not woke.entered_idle


def test_scheduler_keeps_analysing_while_busy_and_when_not_gateable():
    clock = Clock()
    sched = make_scheduler(clock)
    sched.plan(scene(), True, False)
    for _ in range(80):
        clock.advance(0.1)
        assert sched.plan(scene(), True, True).active       # event in progress
    for _ in range(80):
        clock.advance(0.1)
        assert sched.plan(scene(), False, False).active     # AI off / model missing -> never gated


def test_smart_analysis_off_is_identical_to_old_every_second_frame():
    clock = Clock()
    sched = make_scheduler(clock, smart=False)
    flags = []
    for _ in range(10):
        clock.advance(10)   # long still periods must not matter
        flags.append(sched.plan(scene(), True, False).analyze)
    # old rule: analysis_frame_index == 1 or index % 2 == 0
    assert flags == [True, True, False, True, False, True, False, True, False, True]


def test_stride_pattern_when_active_matches_old_behaviour():
    clock = Clock()
    sched = make_scheduler(clock)
    flags = []
    for i in range(8):
        clock.advance(0.03)
        flags.append(sched.plan(scene(offset=(i * 40) % 500), True, False).analyze)
    assert flags == [True, True, False, True, False, True, False, True]


def test_adaptive_stride_rises_under_overload_and_recovers():
    clock = Clock()
    strider = AdaptiveStride(2, 4, clock=clock)
    for _ in range(40):
        clock.advance(0.033); strider.observe_frame(clock())
    assert strider.stride == 2
    frames_since = 0
    for _ in range(3000):                # camera keeps delivering at 30 fps
        clock.advance(0.033); strider.observe_frame(clock())
        frames_since += 1
        if frames_since >= strider.stride:   # one analysis per `stride` frames, too slow
            frames_since = 0
            strider.record(0.2)
    assert strider.stride == 4           # capped
    frames_since = 0
    for _ in range(3000):
        clock.advance(0.033); strider.observe_frame(clock())
        frames_since += 1
        if frames_since >= strider.stride:
            frames_since = 0
            strider.record(0.005)
    assert strider.stride == 2


def test_adaptive_stride_never_changes_under_normal_load():
    clock = Clock()
    strider = AdaptiveStride(2, 4, clock=clock)
    for _ in range(500):
        clock.advance(0.033); strider.observe_frame(clock()); strider.record(0.02)
    assert strider.stride == 2


def test_resolve_profile_rules():
    gpu = HardwareInfo(16, 64.0, True, "RTX", 12.0)
    cpu_strong = HardwareInfo(8, 16.0, False)
    cpu_weak = HardwareInfo(4, 8.0, False)
    low_ram = HardwareInfo(8, 4.0, False)
    assert resolve_profile("auto", gpu, 3).name == "standard"
    assert resolve_profile("auto", gpu, 100).name == "server"
    assert resolve_profile("auto", cpu_strong, 50).name == "standard"
    assert resolve_profile("auto", cpu_weak, 1).name == "lite"
    assert resolve_profile("auto", low_ram, 1).name == "lite"
    assert resolve_profile("server", cpu_weak, 1).name == "server"   # explicit wins
    assert resolve_profile("nonsense", cpu_weak, 1).name == "lite"
    assert PROFILES["server"].batch_detector and not PROFILES["standard"].batch_detector


def test_engine_override_sources(tmp_path, monkeypatch):
    monkeypatch.delenv("CAMPUSGUARD_PROFILE", raising=False)
    monkeypatch.delenv("CAMPUSGUARD_SMART_ANALYSIS", raising=False)
    assert read_engine_override(tmp_path) == "auto"
    (tmp_path / "engine.json").write_text('{"profile": "Server", "smart_analysis": false}')
    assert read_engine_override(tmp_path) == "server"
    assert smart_analysis_enabled(tmp_path) is False
    monkeypatch.setenv("CAMPUSGUARD_PROFILE", "lite")
    monkeypatch.setenv("CAMPUSGUARD_SMART_ANALYSIS", "1")
    assert read_engine_override(tmp_path) == "lite"
    assert smart_analysis_enabled(tmp_path) is True
    (tmp_path / "engine.json").write_text("not json")
    monkeypatch.delenv("CAMPUSGUARD_PROFILE"); monkeypatch.delenv("CAMPUSGUARD_SMART_ANALYSIS")
    assert read_engine_override(tmp_path) == "auto" and smart_analysis_enabled(tmp_path) is True


def test_active_camera_counter():
    reg = ActiveCameras()
    reg.enter(); reg.enter(); reg.leave()
    assert reg.count == 1
    reg.leave(); reg.leave()
    assert reg.count == 0


def test_batch_runner_batches_concurrent_callers_and_keeps_order():
    def run(items):
        time.sleep(0.02)
        return [i * 10 for i in items]

    runner = BatchRunner(run, max_batch=8, max_wait=0.05)
    results = {}

    def call(i):
        results[i] = runner.submit(i)

    threads = [threading.Thread(target=call, args=(i,)) for i in range(16)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert results == {i: i * 10 for i in range(16)}
    assert max(runner.batch_sizes) > 1 and max(runner.batch_sizes) <= 8
    runner.close()


def test_batch_runner_error_reaches_every_caller_and_recovers():
    state = {"fail": True}

    def run(items):
        if state["fail"]:
            raise ValueError("boom")
        return list(items)

    runner = BatchRunner(run, max_wait=0.01)
    with pytest.raises(ValueError):
        runner.submit(1)
    state["fail"] = False
    assert runner.submit(2) == 2
    runner.close()


def test_batch_runner_closed_and_wrong_length():
    runner = BatchRunner(lambda items: [], max_wait=0.001)
    with pytest.raises(RuntimeError):
        runner.submit(1)
    runner.close()
    with pytest.raises(BatchClosed):
        runner.submit(1)


def test_batch_runner_exits_when_model_gone():
    alive = {"v": True}
    runner = BatchRunner(lambda items: items, alive=lambda: alive["v"])
    assert runner.submit(1) == 1
    alive["v"] = False
    deadline = time.monotonic() + 4
    while runner.usable and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not runner.usable


def test_footage_prebuffer_memory_cap(tmp_path):
    from campusguard.footage import FightFootageRecorder
    rec = FightFootageRecorder(tmp_path)
    rec.max_prebuffer_bytes = 4 * 1024 * 1024
    frame = np.zeros((720, 1280, 3), np.uint8)       # 2.6 MB each
    for _ in range(40):
        rec.update(frame, "NORMAL", False, 30.0)
    assert len(rec.prebuffer) == 1 or len(rec.prebuffer) == 2
    assert len(rec.prebuffer) >= 2 or frame.nbytes * 2 > rec.max_prebuffer_bytes
    uncapped = FightFootageRecorder(tmp_path / "b")
    for _ in range(80):
        uncapped.update(frame, "NORMAL", False, 30.0)
    assert len(uncapped.prebuffer) == 60                # default behaviour unchanged
