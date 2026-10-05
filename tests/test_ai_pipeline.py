import unittest

import numpy as np

from campusguard.ai_pipeline import FightDecision, InteractionEngine, TrackedPerson
from campusguard.model_adapters import MODEL_INPUT_ADAPTERS
from campusguard.model_registry import MODEL_PROFILES
from campusguard.settings import AppSettings


class SettingsTests(unittest.TestCase):
    def test_all_violence_models_round_trip(self):
        for key in ("mc3", "fdsc_mc3", "r3d", "x3d"):
            settings = AppSettings.from_dict({"violence_model": key})
            self.assertEqual(settings.violence_model, key)

    def test_enhanced_is_not_operational(self):
        settings = AppSettings.from_dict({"violence_model": "enhanced"})
        self.assertEqual(settings.violence_model, "mc3")

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

    def test_input_adapter_produces_mc3_tensor_layout(self):
        adapter = MODEL_INPUT_ADAPTERS["mc3"]
        frames = [
            np.zeros((80, 120, 3), dtype=np.uint8)
            for _ in range(adapter.clip_length)
        ]
        tensor = adapter.prepare(frames, __import__("torch").device("cpu"))
        self.assertEqual(tuple(tensor.shape), (1, 3, 16, 112, 112))

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
    def test_stable_predictions_trigger_event(self):
        decision = FightDecision(0.65)
        self.assertIsNone(decision.update("FIGHT DETECTED", 0.90))
        self.assertIsNone(decision.update("FIGHT DETECTED", 0.90))
        event = decision.update("FIGHT DETECTED", 0.90)
        self.assertEqual(event, ("FIGHT DETECTED", 0.90, "HIGH"))

    def test_normal_resets_event_latch(self):
        decision = FightDecision(0.65)
        decision.update("FIGHT DETECTED", 0.90)
        decision.update("FIGHT DETECTED", 0.90)
        decision.update("FIGHT DETECTED", 0.90)
        self.assertTrue(decision.event_latched)
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
