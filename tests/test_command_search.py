from campusguard.settings import AppSettings
from campusguard.ui.command_search import Command, search_commands


def _cmds():
    noop = lambda: None
    return [
        Command("Cameras", "Page", noop, ("video", "footage")),
        Command("Alarm sound", "Setting", noop, ("mute", "audio")),
        Command("Alerts", "Page", noop),
        Command("Check for updates", "Action", noop, ("version",)),
    ]


def test_prefix_beats_keyword():
    assert search_commands(_cmds(), "al")[0].title in {"Alarm sound", "Alerts"}
    assert search_commands(_cmds(), "cam")[0].title == "Cameras"


def test_keyword_and_word_prefix_match():
    assert search_commands(_cmds(), "mute")[0].title == "Alarm sound"
    assert search_commands(_cmds(), "updates")[0].title == "Check for updates"


def test_no_match_and_empty():
    assert search_commands(_cmds(), "zzzz") == []
    assert search_commands(_cmds(), "  ") == []


def test_new_settings_are_validated():
    s = AppSettings.from_dict({"start_page": "nonsense", "alert_sound_enabled": 0, "sidebar_hover_open": 1})
    assert s.start_page == "dashboard" and s.alert_sound_enabled is False and s.sidebar_hover_open is True
    assert AppSettings.from_dict({"start_page": "cameras"}).start_page == "cameras"
