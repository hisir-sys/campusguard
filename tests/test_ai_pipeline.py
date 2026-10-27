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

    def test_all_violence_models_round_trip(self):
        for key in ("mc3", "fdsc_mc3", "r3d", "x3d"):
            settings = AppSettings.from_dict({"violence_model": key})
            self.assertEqual(settings.violence_model, key)

    def test_enhanced_falls_back_to_operational_default(self):
        settings = AppSettings.from_dict({"violence_model": "enhanced"})
        self.assertEqual(settings.violence_model, "fdsc_mc3")

    def test_mc3_fight_class_is_verified_from_manifest(self):
        profile = MODEL_PROFILES["mc3"]
        self.assertEqual(profile.fight_class, 0)
        self.assertEqual(profile.class_labels, ("fight", "noFight"))
        self.assertTrue(profile.semantic_verified)

    def test_unverified_models_cannot_guess_fight_class(self):
        for key in ("r3d",):
            profile = MODEL_PROFILES[key]
            self.assertIsNone(profile.fight_class)
            self.assertFalse(profile.semantic_verified)

    def test_r3d_is_explicitly_marked_as_technical_issue(self):
        r3d = MODEL_PROFILES["r3d"]
        self.assertEqual(r3d.semantic_status, "technical_unavailable")
        self.assertFalse(r3d.semantic_verified)
        self.assertIsNone(r3d.fight_class)

    def test_verified_external_model_contracts(self):
        fdsc = MODEL_PROFILES["fdsc_mc3"]
        self.assertEqual(fdsc.fight_class, 0)
        self.assertEqual(fdsc.class_labels, ("fight", "noFight"))
        self.assertTrue(fdsc.semantic_verified)

        x3d = MODEL_PROFILES["x3d"]
        self.assertEqual(x3d.fight_class, 1)
        self.assertEqual(x3d.class_labels, ("non-violent", "violent"))
        self.assertTrue(x3d.semantic_verified)
        self.assertEqual(MODEL_INPUT_ADAPTERS["x3d"].input_size, (224, 224))
        self.assertEqual(MODEL_INPUT_ADAPTERS["x3d"].mean, (0.45, 0.45, 0.45))
        self.assertEqual(MODEL_INPUT_ADAPTERS["x3d"].std, (0.225, 0.225, 0.225))

    def test_every_operational_checkpoint_family_has_an_input_adapter(self):
        self.assertEqual(
            set(MODEL_INPUT_ADAPTERS),
            {"mc3", "fdsc_mc3", "r3d", "x3d"},
        )
        for key, adapter in MODEL_INPUT_ADAPTERS.items():
            self.assertEqual(adapter.clip_length, 16)
            self.assertEqual(len(adapter.mean), 3)
            self.assertEqual(len(adapter.std), 3)

        self.assertEqual(MODEL_INPUT_ADAPTERS["mc3"].input_size, (112, 112))
        self.assertEqual(MODEL_INPUT_ADAPTERS["fdsc_mc3"].input_size, (112, 112))
        self.assertEqual(MODEL_INPUT_ADAPTERS["r3d"].input_size, (112, 112))
        self.assertEqual(MODEL_INPUT_ADAPTERS["x3d"].input_size, (224, 224))

    def test_fdsc_adapters_use_published_resize_and_center_crop(self):
        for key in ("fdsc_mc3", "r3d"):
            adapter = MODEL_INPUT_ADAPTERS[key]
            self.assertEqual(adapter.resize_size, (171, 128))
            self.assertEqual(adapter.input_size, (112, 112))
            self.assertEqual(adapter.mean, (0.43216, 0.394666, 0.37645))
            self.assertEqual(adapter.std, (0.22803, 0.22145, 0.216989))

    def test_input_adapter_produces_mc3_tensor_layout(self):
        adapter = MODEL_INPUT_ADAPTERS["mc3"]
        frames = [
            np.zeros((80, 120, 3), dtype=np.uint8)
            for _ in range(adapter.clip_length)
        ]
        tensor = __import__("torch").zeros((1, 3, 16, 112, 112))
        prepared = adapter.prepare(frames, __import__("torch").device("cpu"))
        self.assertEqual(tuple(prepared.shape), tuple(tensor.shape))

    def test_fdsc_adapters_produce_expected_tensor_layout(self):
        for key in ("fdsc_mc3", "r3d"):
            adapter = MODEL_INPUT_ADAPTERS[key]
            frames = [
                np.zeros((80, 120, 3), dtype=np.uint8)
                for _ in range(adapter.clip_length)
            ]
            prepared = adapter.prepare(frames, __import__("torch").device("cpu"))
            self.assertEqual(tuple(prepared.shape), (1, 3, 16, 112, 112))

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


class DecisionTests(unittest.TestCase):
    def test_qualifying_prediction_triggers_once_until_normal_release(self):
        decision = FightDecision(0.65)
        event = decision.update("FIGHT DETECTED", 0.90)
        self.assertEqual(event, ("FIGHT DETECTED", 0.90, "HIGH"))
        for _ in range(3):
            self.assertIsNone(decision.update("FIGHT DETECTED", 0.90))
        self.assertTrue(decision.event_latched)

    def test_higher_confidence_updates_same_latched_event(self):
        decision = FightDecision(0.65)
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
