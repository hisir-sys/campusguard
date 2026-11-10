import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from campusguard.ui import brand_logo
from campusguard.ui.theme import set_current
from campusguard.ui.thinking_orb import ThinkingOrb


def _app():
    return QApplication.instance() or QApplication([])


def test_logo_orb_and_mark_paint_in_both_themes():
    _app()
    for theme in ("dark", "light"):
        set_current(theme)
        reveal = brand_logo.LogoReveal(size=120)
        reveal.seconds = lambda: 3.3  # the film starts empty; check the held end state
        for widget in (reveal, ThinkingOrb(size=120), brand_logo.LogoMark(size=64)):
            image = widget.grab().toImage()
            assert not image.isNull()
            assert any(image.pixelColor(x, y).alpha() > 0 for x in range(0, image.width(), 4) for y in range(0, image.height(), 4))
            if hasattr(widget, "stop"):
                widget.stop()
    set_current("dark")


def test_saved_theme_falls_back_to_dark(monkeypatch, tmp_path):
    import campusguard.storage as storage

    monkeypatch.setattr(storage, "application_data_dir", lambda: tmp_path)
    assert brand_logo.saved_theme() == "dark"             # no database yet
    (tmp_path / "campusguard.db").write_bytes(b"not a database")
    assert brand_logo.saved_theme() == "dark"             # unreadable database


def test_saved_theme_reads_the_users_choice(monkeypatch, tmp_path):
    import json
    import sqlite3

    import campusguard.storage as storage

    monkeypatch.setattr(storage, "application_data_dir", lambda: tmp_path)
    connection = sqlite3.connect(tmp_path / "campusguard.db")
    connection.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    connection.execute("INSERT INTO settings VALUES ('theme', ?)", (json.dumps("light"),))
    connection.commit()
    connection.close()
    assert brand_logo.saved_theme() == "light"


def test_startup_window_plays_the_logo_animation(monkeypatch):
    _app()
    monkeypatch.setattr(brand_logo, "saved_theme", lambda: "light")
    import main as app_main

    window = app_main.StartupWindow()
    window.show()
    assert window.logo.isVisible()
    window.set_status("Loading models…")
    assert window.status.text() == "Loading models"
    window.close()
    set_current("dark")
