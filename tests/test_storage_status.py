import tempfile
import unittest
from pathlib import Path

from campusguard.storage import Repository


class IncidentAlertConsistencyTests(unittest.TestCase):
    def test_resolving_incident_acknowledges_its_alert(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Repository(database_path=Path(directory) / "campusguard-test.db")
            camera = repository.add_camera(
                name="Test camera",
                source_type="file",
                source_address="test.mp4",
            )
            incident = repository.create_incident(
                camera=camera,
                event="FIGHT DETECTED",
                confidence=0.91,
                severity="HIGH",
                cooldown_seconds=0,
            )
            self.assertIsNotNone(incident)
            public_id = incident["public_id"]

            alert = repository.list_alerts()[0]
            self.assertEqual(alert["acknowledged"], 0)

            repository.update_incident_status(public_id, "RESOLVED")

            resolved = repository.list_incidents()[0]
            updated_alert = repository.list_alerts()[0]
            self.assertEqual(resolved["status"], "RESOLVED")
            self.assertEqual(updated_alert["acknowledged"], 1)
            self.assertEqual(repository.open_incident_count(), 0)


if __name__ == "__main__":
    unittest.main()
