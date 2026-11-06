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


def test_toast_shows_updates_and_dismisses():
    from PySide6.QtWidgets import QApplication, QWidget
    from campusguard.ui.severity_alert import SeverityAlertToast

    app = QApplication.instance() or QApplication([])
    host = QWidget(); host.resize(900, 600); host.show()
    toast = SeverityAlertToast(host)
    toast.show_alert("INC-1", "Fight detected", "Gate", 0.5)
    assert not toast.isVisible()                    # below 70%: no popup
    toast.show_alert("INC-1", "Fight detected", "Gate", 0.97)
    assert toast.isVisible() and toast._title.text() == "DANGER" and toast._pulse_timer.isActive()
    toast.update_alert("INC-1", "Fight detected", "Gate", 0.99)
    assert toast._confidence_value.text() == "99%"
    toast.dismiss()
    assert not toast._pulse_timer.isActive()
