import math
import unittest

from campusguard.settings import AppSettings


class DefensiveSettingsTests(unittest.TestCase):
    def test_non_dictionary_settings_use_defaults(self):
        self.assertEqual(AppSettings.from_dict(None), AppSettings())
        self.assertEqual(AppSettings.from_dict(["unexpected"]), AppSettings())

    def test_invalid_numeric_values_fall_back_without_crashing(self):
        settings = AppSettings.from_dict({
            "confidence_threshold": "not-a-number",
            "alert_cooldown_seconds": "not-an-integer",
            "fight_positive_class": None,
        })
        self.assertEqual(settings.confidence_threshold, AppSettings().confidence_threshold)
        self.assertEqual(settings.alert_cooldown_seconds, AppSettings().alert_cooldown_seconds)
        self.assertEqual(settings.fight_positive_class, AppSettings().fight_positive_class)

    def test_non_finite_confidence_uses_default(self):
        for value in (math.nan, math.inf, -math.inf):
            settings = AppSettings.from_dict({"confidence_threshold": value})
            self.assertEqual(settings.confidence_threshold, AppSettings().confidence_threshold)

    def test_numeric_ranges_are_clamped(self):
        low = AppSettings.from_dict({"confidence_threshold": -10, "alert_cooldown_seconds": -1})
        high = AppSettings.from_dict({"confidence_threshold": 10})
        self.assertEqual(low.confidence_threshold, 0.05)
        self.assertEqual(low.alert_cooldown_seconds, 0)
        self.assertEqual(high.confidence_threshold, 0.99)

    def test_boolean_strings_are_interpreted_explicitly(self):
        settings = AppSettings.from_dict({
            "detection_enabled": "false",
            "tracking_enabled": "yes",
            "auto_reconnect": "off",
        })
        self.assertFalse(settings.detection_enabled)
        self.assertTrue(settings.tracking_enabled)
        self.assertFalse(settings.auto_reconnect)

    def test_unknown_model_and_invalid_paths_fall_back_safely(self):
        settings = AppSettings.from_dict({
            "violence_model": "enhanced",
            "detector_model_path": "",
        })
        self.assertEqual(settings.violence_model, AppSettings().violence_model)
        self.assertEqual(settings.detector_model_path, AppSettings().detector_model_path)

    def test_unknown_keys_are_ignored(self):
        settings = AppSettings.from_dict({"not_a_setting": "value"})
        self.assertEqual(settings, AppSettings())


if __name__ == "__main__":
    unittest.main()
