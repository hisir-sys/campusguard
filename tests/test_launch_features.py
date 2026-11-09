import csv
import tempfile
import unittest
from pathlib import Path

from campusguard import system_health
from campusguard.camera_runtime import RuntimeOptions
from campusguard.settings import AppSettings, effective_threshold
from campusguard.storage import Repository


class RepositoryLaunchFeatures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.repo = Repository(root / "cg.db", root / "footage")
        self.camera = self.repo.add_camera("Gate", "RTSP", "rtsp://x/1")

    def tearDown(self):
        self.tmp.cleanup()

    def test_camera_sensitivity_persists_and_is_clamped(self):
        self.assertEqual(self.repo.list_cameras()[0].threshold_offset, 0.0)
        self.repo.set_camera_threshold_offset(self.camera.camera_id, 0.1)
        self.assertAlmostEqual(self.repo.list_cameras()[0].threshold_offset, 0.1)
        self.repo.set_camera_threshold_offset(self.camera.camera_id, 9)
        self.assertAlmostEqual(self.repo.list_cameras()[0].threshold_offset, 0.25)

    def test_false_alarm_is_recorded_and_audited(self):
        incident = self.repo.create_incident(self.camera, "Fight", 0.9, "HIGH", 0)
        self.repo.update_incident_status(incident["public_id"], "FALSE_ALARM")
        self.assertEqual(self.repo.get_incident(incident["public_id"])["status"], "FALSE_ALARM")
        actions = [(row["action"], row["target"], row["detail"]) for row in self.repo.list_audit()]
        self.assertIn(("incident_status", incident["public_id"], "FALSE_ALARM"), actions)
        counts = self.repo.review_counts()["Gate"]
        self.assertEqual((counts["total"], counts["false_alarm"]), (1, 1))

    def test_clip_hash_detects_tampering(self):
        incident = self.repo.create_incident(self.camera, "Fight", 0.9, "HIGH", 0)
        clip = self.repo.footage_dir / "clip.mp4"
        clip.write_bytes(b"original footage")
        self.repo.attach_incident_footage(incident["public_id"], str(clip))
        row = self.repo.get_incident(incident["public_id"])
        self.assertEqual(len(row["footage_sha256"]), 64)
        self.assertEqual(self.repo.footage_integrity(row), "OK")
        clip.write_bytes(b"edited footage")
        self.assertEqual(self.repo.footage_integrity(row), "MODIFIED")
        clip.unlink()
        self.assertEqual(self.repo.footage_integrity(row), "MISSING")

    def test_export_report_and_audit(self):
        incident = self.repo.create_incident(self.camera, "Fight", 0.876, "HIGH", 0)
        self.repo.update_incident_status(incident["public_id"], "RESOLVED")
        out = Path(self.tmp.name) / "report.csv"
        audit = Path(self.tmp.name) / "audit.csv"
        self.assertEqual(self.repo.export_incidents_csv(out, audit), 1)
        rows = list(csv.DictReader(open(out, encoding="utf-8-sig")))
        self.assertEqual(rows[0]["incident_id"], incident["public_id"])
        self.assertEqual(rows[0]["confidence_percent"], "87.6")
        self.assertEqual(rows[0]["status"], "RESOLVED")
        self.assertEqual(rows[0]["clip_integrity"], "NO CLIP")
        self.assertIn("RESOLVED", audit.read_text(encoding="utf-8-sig"))

    def test_old_database_is_migrated(self):
        import sqlite3
        path = Path(self.tmp.name) / "old.db"
        connection = sqlite3.connect(path)
        connection.executescript(
            "CREATE TABLE cameras (camera_id TEXT PRIMARY KEY, name TEXT NOT NULL, source_type TEXT NOT NULL,"
            " source_address TEXT NOT NULL, ai_enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);"
            "INSERT INTO cameras VALUES ('CAM-001','Old','RTSP','rtsp://old',1,'2026-01-01T00:00:00+00:00');"
        )
        connection.commit()
        connection.close()
        migrated = Repository(path, Path(self.tmp.name) / "f2")
        self.assertEqual(migrated.list_cameras()[0].threshold_offset, 0.0)


class SensitivityAndHealth(unittest.TestCase):
    def test_effective_threshold_is_clamped(self):
        self.assertAlmostEqual(effective_threshold(0.65, 0.1), 0.75)
        self.assertEqual(effective_threshold(0.95, 0.2), 0.99)
        self.assertEqual(effective_threshold(0.1, -0.2), 0.05)

    def test_runtime_options_apply_camera_offset(self):
        settings = AppSettings(confidence_threshold=0.65)
        options = RuntimeOptions(settings, True, 0.1)
        self.assertAlmostEqual(options.snapshot()[0].confidence_threshold, 0.75)
        self.assertIs(options.snapshot()[0], options.snapshot()[0])  # cached, not rebuilt every frame
        options.update_threshold_offset(0.0)
        self.assertAlmostEqual(options.snapshot()[0].confidence_threshold, 0.65)
        options.update_threshold_offset(-0.1)
        options.update_settings(AppSettings(confidence_threshold=0.8))
        self.assertAlmostEqual(options.snapshot()[0].confidence_threshold, 0.7)

    def test_disk_levels(self):
        gb = 1024 ** 3
        self.assertEqual(system_health.evaluate_disk(500 * gb, 1000 * gb), [])
        self.assertEqual(system_health.evaluate_disk(8 * gb, 1000 * gb)[0][0], "warning")
        self.assertEqual(system_health.evaluate_disk(2 * gb, 1000 * gb)[0][0], "critical")
        self.assertEqual(system_health.evaluate_disk(50 * gb, 1000 * gb)[0][0], "warning")  # under 10%

    def test_camera_problems(self):
        self.assertEqual(system_health.camera_problems({"a": "LIVE", "b": "LIVE"}), [])
        self.assertEqual(system_health.camera_problems({"a": "LIVE", "b": "ERROR"})[0][0], "warning")
        self.assertEqual(system_health.camera_problems({"a": "ERROR", "b": "OFFLINE"})[0][0], "critical")
        self.assertEqual(system_health.camera_problems({"a": "CONNECTING"}), [])

    def test_collect_runs_on_a_real_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "a.mp4").write_bytes(b"x" * 10)
            report = system_health.collect(Path(folder), with_gpu=False)
            self.assertEqual((report.footage_clips, report.footage_bytes), (1, 10))
            self.assertGreater(report.disk_total, 0)


if __name__ == "__main__":
    unittest.main()
