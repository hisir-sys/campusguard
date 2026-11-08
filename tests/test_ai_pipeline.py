import unittest

import numpy as np

from campusguard.ai_pipeline import FightDecision, InteractionEngine, TrackedPerson
from campusguard.model_adapters import MODEL_INPUT_ADAPTERS
from campusguard.model_registry import MODEL_PROFILES
from campusguard.settings import AppSettings
from campusguard.server.recorder import severity_for


class SettingsTests(unittest.TestCase):
    def test_incident_severity_matches_alert_thresholds(self):
        self.assertEqual(severity_for(0.69), "LOW")
        self.assertEqual(severity_for(0.70), "MEDIUM")
        self.assertEqual(severity_for(0.849), "MEDIUM")
        self.assertEqual(severity_for(0.85), "HIGH")
        self.assertEqual(severity_for(0.949), "HIGH")
        self.assertEqual(severity_for(0.95), "CRITICAL")

    def test_spontim_is_the_only_model(self):
        self.assertEqual(set(MODEL_PROFILES), {"fdsc_mc3"})
        self.assertEqual(set(MODEL_INPUT_ADAPTERS), {"fdsc_mc3"})
        self.assertEqual(MODEL_PROFILES["fdsc_mc3"].name, "Spontim 1.0")

    def test_any_saved_model_name_resolves_to_spontim(self):
        for key in ("mc3", "fdsc_mc3", "r3d", "x3d", "enhanced", ""):
            self.assertEqual(AppSettings.from_dict({"violence_model": key}).violence_model, "fdsc_mc3")

    def test_old_settings_files_with_removed_model_paths_still_load(self):
        settings = AppSettings.from_dict({"r3d_model_path": "x", "x3d_model_path": "y", "fight_model_path": "z"})
        self.assertEqual(settings.violence_model, "fdsc_mc3")

    def test_spontim_contract(self):
        profile = MODEL_PROFILES["fdsc_mc3"]
        self.assertEqual(profile.fight_class, 0)
        self.assertEqual(profile.class_labels, ("fight", "noFight"))
        self.assertTrue(profile.semantic_verified)
        adapter = MODEL_INPUT_ADAPTERS["fdsc_mc3"]
        self.assertEqual(adapter.clip_length, 16)
        self.assertEqual(adapter.resize_size, (171, 128))
        self.assertEqual(adapter.input_size, (112, 112))
        self.assertEqual(adapter.mean, (0.43216, 0.394666, 0.37645))
        self.assertEqual(adapter.std, (0.22803, 0.22145, 0.216989))

    def test_input_adapter_produces_expected_tensor_layout(self):
        adapter = MODEL_INPUT_ADAPTERS["fdsc_mc3"]
        frames = [np.zeros((80, 120, 3), dtype=np.uint8) for _ in range(adapter.clip_length)]
        prepared = adapter.prepare(frames, __import__("torch").device("cpu"))
        self.assertEqual(tuple(prepared.shape), (1, 3, 16, 112, 112))

    def test_model_defaults_are_portable(self):
        settings = AppSettings()
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


class DecisionTests(unittest.TestCase):
    def test_qualifying_prediction_triggers_once_until_normal_release(self):
        decision = FightDecision(0.65)
        self.assertIsNone(decision.update("FIGHT DETECTED", 0.90))  # a single spike is not enough
        event = decision.update("FIGHT DETECTED", 0.90)
        self.assertEqual(event, ("FIGHT DETECTED", 0.90, "HIGH"))
        for _ in range(3):
            self.assertIsNone(decision.update("FIGHT DETECTED", 0.90))
        self.assertTrue(decision.event_latched)

    def test_higher_confidence_updates_same_latched_event(self):
        decision = FightDecision(0.65)
        self.assertIsNone(decision.update("FIGHT DETECTED", 0.80))
        self.assertEqual(
            decision.update("FIGHT DETECTED", 0.80),
            ("FIGHT DETECTED", 0.80, "HIGH"),
        )
        self.assertEqual(
            decision.update("FIGHT DETECTED", 0.94),
            ("UPDATE", 0.94, "HIGH"),
        )
        self.assertIsNone(decision.update("FIGHT DETECTED", 0.91))
        self.assertEqual(decision.peak_confidence, 0.94)

    def test_single_spike_between_normals_never_triggers(self):
        decision = FightDecision(0.65)
        for _ in range(5):
            self.assertIsNone(decision.update("NORMAL", 0.1))
            self.assertIsNone(decision.update("FIGHT DETECTED", 0.97))
        self.assertFalse(decision.event_latched)

    def test_normal_resets_event_latch(self):
        decision = FightDecision(0.65)
        for _ in range(FightDecision.TRIGGER_PREDICTIONS):
            decision.update("FIGHT DETECTED", 0.90)
        self.assertTrue(decision.event_latched)
        for _ in range(FightDecision.NORMAL_RELEASE_PREDICTIONS):
            decision.update("NORMAL", 0.20)
        self.assertFalse(decision.event_latched)


class InteractionStateTests(unittest.TestCase):
    def test_close_to_is_not_stale_after_people_separate(self):
        engine = InteractionEngine()
        people = [
            TrackedPerson(1, 1, (10, 10, 110, 210), 0.95, center=(60, 110)),
            TrackedPerson(2, 2, (80, 20, 180, 220), 0.94, center=(130, 120)),
        ]
        engine.update(people)
        self.assertIn(2, people[0].close_to)
        people[1].center = (600, 600)
        engine.update(people)
        self.assertNotIn(2, people[0].close_to)


if __name__ == "__main__":
    unittest.main()
