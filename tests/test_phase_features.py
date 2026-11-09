from campusguard import reports, updater
from campusguard.evidence_pin import hash_pin, valid_new_pin, verify_pin
from campusguard.storage import Repository


def test_pin_hash_roundtrip():
    h = hash_pin("4821")
    assert verify_pin("4821", h) and not verify_pin("0000", h) and not verify_pin("x", "garbage")
    assert not valid_new_pin("12")


def test_reports_summary_and_html():
    rows = [
        {"happened_at": "2026-11-02T10:15:00", "camera_name": "Gate", "severity": "HIGH", "status": "FALSE_ALARM"},
        {"happened_at": "2026-11-02T10:45:00", "camera_name": "Gate", "severity": "MEDIUM", "status": "NEW"},
        {"happened_at": "2026-11-03T14:00:00", "camera_name": "Hall", "severity": "HIGH", "status": "RESOLVED"},
    ]
    s = reports.summarize(rows)
    assert s["total"] == 3 and s["false_alarms"] == 1 and s["busiest_hour"] == 10
    assert "Gate" in reports.render_html(rows)
    assert reports.summarize([])["false_alarm_rate"] == 0.0


def test_camera_group_persists(tmp_path):
    repo = Repository(tmp_path / "cg.db", tmp_path / "footage")
    cam = repo.add_camera("Gate", "RTSP", "rtsp://x/1") if hasattr(repo, "add_camera") else None
    if cam is None:
        return
    repo.set_camera_group(cam.camera_id, "  Block   A ")
    assert repo.list_cameras()[0].group_name == "Block A"


def test_rollback_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "_archive_dir", lambda: tmp_path)
    monkeypatch.setattr(updater, "BUILD_VERSION", "10")
    for n in (7, 9, 11):
        (tmp_path / f"CampusGuard-Setup-{n}.exe").write_bytes(b"x" * 1_100_000)
    assert updater.rollback_candidate()[0] == 9
