import array
import io
import os
import wave

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from campusguard import alarm_sound


def _stats(level):
    with wave.open(io.BytesIO(alarm_sound.build_wav(level))) as handle:
        frames = handle.readframes(handle.getnframes())
        seconds = handle.getnframes() / handle.getframerate()
    samples = array.array("h", frames)
    rms = (sum(x * x for x in samples) / len(samples)) ** 0.5
    return max(abs(x) for x in samples), rms, seconds


def test_louder_and_longer_with_severity():
    medium, high, critical = (_stats(level) for level in ("medium", "high", "critical"))
    assert medium[0] < high[0] < critical[0] <= 32767
    assert medium[1] < high[1] < critical[1]
    assert medium[2] < high[2] < critical[2]
    assert 1.5 < medium[2] < 3 and 4.5 < high[2] < 6 and 9.5 < critical[2] < 11


def test_unknown_level_and_playback_never_raise():
    assert alarm_sound.build_wav("nonsense") == alarm_sound.build_wav("medium")
    alarm_sound.play("critical")
    alarm_sound.stop()


def test_fight_alert_shows_updates_and_dismisses():
    from PySide6.QtWidgets import QApplication, QWidget
    from campusguard.ui.severity_alert import FightAlert

    app = QApplication.instance() or QApplication([])
    host = QWidget(); host.resize(900, 600); host.show()
    alert = FightAlert(host)
    alert.show_alert("INC-1", "Fight detected", "Gate", 0.5)
    assert not alert.isVisible()                    # below 70%: no popup
    alert.show_alert("INC-1", "Fight detected", "Gate", 0.97)
    assert alert.isVisible() and alert._pill.text() == "Danger"
    assert "INC-1" in alert._meta.text() and "Gate" in alert._meta.text() and "97%" in alert._meta.text()
    alert.update_alert("INC-1", "Fight detected", "Gate", 0.99)
    assert "99%" in alert._meta.text()
    seen = []
    alert.view_requested.connect(seen.append)
    alert._review.click()
    assert seen == ["INC-1"]
    alert.dismiss()
    assert not alert._auto.isActive()


def test_toast_stack_caps_and_undo():
    from PySide6.QtWidgets import QApplication, QWidget
    from campusguard.ui.notify import MAX_TOASTS, ToastStack

    app = QApplication.instance() or QApplication([])
    host = QWidget(); host.resize(900, 600); host.show()
    stack = ToastStack(host)
    undone = []
    for i in range(MAX_TOASTS + 2):
        stack.show_toast(f"Message {i}")
    assert len(stack._toasts) == MAX_TOASTS
    toast = stack.show_toast("Removed", undo=lambda: undone.append(1))
    from PySide6.QtWidgets import QPushButton
    toast.findChild(QPushButton, "toastUndo").click()
    assert undone == [1] and toast not in stack._toasts
