import unittest

from campusguard.ai_pipeline import InteractionEngine, TrackedPerson
from campusguard.settings import AppSettings


class SettingsTests(unittest.TestCase):
    def test_all_violence_models_round_trip(self):
        for key in ("mc3", "fdsc_mc3", "r3d", "x3d"):
            settings = AppSettings.from_dict({"violence_model": key})
            self.assertEqual(settings.violence_model, key)

    def test_enhanced_is_not_operational(self):
        settings = AppSettings.from_dict({"violence_model": "enhanced"})
        self.assertEqual(settings.violence_model, "mc3")

    def test_model_defaults_are_portable(self):
        settings = AppSettings()
        self.assertEqual(settings.fight_model_path, "models/fight_mc3_18.pth")
        self.assertEqual(settings.fdsc_mc3_model_path, "models/model_16_m3_0.8888.pth")


class InteractionTests(unittest.TestCase):
    def test_close_people_become_an_interaction_candidate(self):
        engine = InteractionEngine()
        people = [
            TrackedPerson(1, 1, (10, 10, 110, 210), 0.95, center=(60, 110)),
            TrackedPerson(2, 2, (80, 20, 180, 220), 0.94, center=(130, 120)),
        ]
        self.assertEqual(engine.update(people), [])
        self.assertEqual(engine.update(people), [(1, 2)])
        self.assertIn(2, people[0].close_to)
        self.assertIn(1, people[1].close_to)


if __name__ == "__main__":
    unittest.main()
