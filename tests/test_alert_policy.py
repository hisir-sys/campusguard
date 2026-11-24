from datetime import datetime

from campusguard import keep_awake
from campusguard.alert_policy import RELAXED, SILENT, decide, severity_for_score
from campusguard.settings import AppSettings, CameraConfig
from campusguard.storage import Repository

AT_2PM = datetime(2026, 11, 22, 14, 30)
AT_9AM = datetime(2026, 11, 22, 9, 0)


def test_grades():
    assert [severity_for_score(x) for x in (50, 70, 85, 95)] == ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def test_normal_alert_is_announced():
    d = decide(0.9, now=AT_9AM)
    assert d.severity == "HIGH" and d.announce and d.suppressed == ""


def test_silent_mode_keeps_severity_but_holds_back():
    d = decide(0.9, silent_mode=True, now=AT_9AM)
    assert d.severity == "HIGH" and not d.announce and d.suppressed == SILENT


def test_relaxed_hours_cap_to_low_and_hold_back():
    d = decide(0.97, relaxed_start="14:00", relaxed_end="15:00", now=AT_2PM)
    assert d.severity == "LOW" and not d.announce and d.suppressed == RELAXED
    outside = decide(0.97, relaxed_start="14:00", relaxed_end="15:00", now=AT_9AM)
    assert outside.severity == "CRITICAL" and outside.announce


def test_relaxed_wins_over_silent_so_the_report_only_counts_real_misses():
    assert decide(0.97, silent_mode=True, relaxed_start="14:00", relaxed_end="15:00", now=AT_2PM).suppressed == RELAXED


def test_relaxed_window_across_midnight():
    assert not decide(0.9, relaxed_start="22:00", relaxed_end="06:00", now=datetime(2026, 1, 1, 23, 0)).announce


def test_settings_roundtrip():
    s = AppSettings.from_dict({"silent_mode": 1, "keep_awake": 0})
    assert s.silent_mode is True and s.keep_awake is False
    assert AppSettings().keep_awake is True and AppSettings().silent_mode is False


def test_repository_stores_relaxed_hours_and_silent_report(tmp_path):
    repo = Repository(tmp_path / "t.db")
    camera = repo.add_camera("Gym", "USB", "0", True)
    assert repo.set_camera_relaxed(camera.camera_id, "14:00", "15:00") == ("14:00", "15:00")
    assert repo.set_camera_relaxed(camera.camera_id, "14:00", "") == ("", "")     # half a window is dropped
    repo.set_camera_relaxed(camera.camera_id, "14:00", "15:00")
    stored = next(c for c in repo.list_cameras() if c.camera_id == camera.camera_id)
    assert (stored.relaxed_start, stored.relaxed_end) == ("14:00", "15:00")

    held = repo.create_incident(stored, "FIGHT", 0.9, "HIGH", 0, "silent")
    repo.create_incident(stored, "FIGHT", 0.9, "HIGH", 0, "")
    report = repo.silent_report(14)
    assert report["total"] == 1 and report["by_camera"] == {"Gym": 1}
    repo.update_incident_status(held["public_id"], "FALSE_ALARM")
    again = repo.silent_report(14)
    assert again["reviewed"] == 1 and again["false_alarms"] == 1

    events, _ = repo.list_sync_events(0)
    assert sorted(e["suppressed"] for e in events) == ["", "silent"]


def test_keep_awake_is_safe_anywhere():
    keep_awake.set_active(True)
    keep_awake.set_active(True)
    assert keep_awake.is_active()
    keep_awake.set_active(False)
    assert not keep_awake.is_active()


def _bare_classifier(monkeypatch):
    """A VideoClassifier with no model file: only the frame bookkeeping is tested."""
    import numpy as np
    from campusguard.model_registry import VideoClassifier

    clf = object.__new__(VideoClassifier)
    clf.model, clf.fight_class = object(), 0
    clf.frames, clf.frame_times = [], []
    clf.frame_count, clf.skipped_slow, clf.behind = 0, 0, False
    from campusguard.model_adapters import get_model_input_adapter
    clf.adapter = get_model_input_adapter("fdsc_mc3")
    clf.span, clf.CLIP_LENGTH, clf.INFERENCE_STRIDE = 16, 16, 8
    clf.MAX_CLIP_SECONDS = VideoClassifier.MAX_CLIP_SECONDS
    clf.grid_interval, clf._last_grid_time, clf.since_check = None, None, 0
    monkeypatch.setattr(VideoClassifier, "_classify_clip", lambda self, clip: ("NORMAL", 0.1))
    return clf, np.zeros((8, 8, 3), dtype="uint8")


def test_classifier_skips_clips_stretched_by_a_slow_analyser(monkeypatch):
    clf, frame = _bare_classifier(monkeypatch)
    results = [clf.add_frame(frame, timestamp=i / 15.0) for i in range(32)]      # 15 fps: keeps up
    assert any(results) and not clf.behind and clf.skipped_slow == 0

    clf, frame = _bare_classifier(monkeypatch)
    results = [clf.add_frame(frame, timestamp=i * 0.5) for i in range(32)]       # 2 fps: far behind
    assert not any(results) and clf.behind and clf.skipped_slow >= 1

    clf, frame = _bare_classifier(monkeypatch)
    results = [clf.add_frame(frame, timestamp=i / 15.0) for i in range(16)]
    results += [clf.add_frame(frame, timestamp=1.07 + (i + 1) * 0.5) for i in range(16)]
    assert clf.behind                                                              # then catches up:
    results = [clf.add_frame(frame, timestamp=20 + i / 15.0) for i in range(16)]
    assert any(results) and not clf.behind


def test_classifier_without_timestamps_behaves_as_before(monkeypatch):
    clf, frame = _bare_classifier(monkeypatch)
    results = [clf.add_frame(frame) for _ in range(32)]
    assert sum(r is not None for r in results) == 3 and not clf.behind   # frames 16, 24, 32
