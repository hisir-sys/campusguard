"""Alarm sounds for incident alerts: generated tones, louder and more urgent as severity rises.

Sounds are synthesised in code (no audio files to ship). Each level is one WAV that is
played asynchronously, so the UI never blocks and the whole pattern can be cut short.
The system volume sets the ceiling; the level's own amplitude makes CRITICAL clearly
louder than MEDIUM at any volume setting.
"""
from __future__ import annotations

import array
import io
import math
import threading
import wave

try:
    import winsound
except ImportError:  # non-Windows development / tests
    winsound = None

SAMPLE_RATE = 22050
# Peak amplitude (0..1) per level; the ordering is what makes severity audible.
LEVEL_VOLUME = {"medium": 0.38, "high": 0.68, "critical": 0.96}
LEVEL_SECONDS = {"medium": 2.0, "high": 5.0, "critical": 10.0}

_cache: dict[str, bytes] = {}
_lock = threading.Lock()


def _envelope(i: int, n: int, attack: float = 0.008, release: float = 0.03) -> float:
    a = max(1, int(attack * SAMPLE_RATE))
    r = max(1, int(release * SAMPLE_RATE))
    return min(1.0, i / a, (n - i) / r)


def _note(freq: float, seconds: float, decay: float = 0.0, harmonics=((2, 0.28), (3, 0.1))) -> list[float]:
    n = int(seconds * SAMPLE_RATE)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        value = math.sin(2 * math.pi * freq * t)
        for multiple, weight in harmonics:
            value += weight * math.sin(2 * math.pi * freq * multiple * t)
        value /= 1.0 + sum(weight for _, weight in harmonics)
        out.append(value * _envelope(i, n) * (math.exp(-decay * t) if decay else 1.0))
    return out


def _silence(seconds: float) -> list[float]:
    return [0.0] * int(seconds * SAMPLE_RATE)


def _medium() -> list[float]:
    """Soft two-note chime, played twice."""
    one = _note(659.3, 0.42, decay=4.5) + _note(880.0, 0.55, decay=4.0)
    return one + _silence(0.25) + one


def _high() -> list[float]:
    """Urgent rising triple-beep, repeated."""
    burst = []
    for freq in (880.0, 988.0, 1175.0):
        burst += _note(freq, 0.14, harmonics=((2, 0.35), (3, 0.18))) + _silence(0.06)
    pattern = burst + _silence(0.28)
    out: list[float] = []
    while len(out) < int(LEVEL_SECONDS["high"] * SAMPLE_RATE):
        out += pattern
    return out


def _critical() -> list[float]:
    """Rising and falling siren sweep with a pulsing edge: unmistakable."""
    total = int(LEVEL_SECONDS["critical"] * SAMPLE_RATE)
    cycle = 1.2
    out, phase = [], 0.0
    for i in range(total):
        t = (i / SAMPLE_RATE) % cycle
        x = t / cycle
        sweep = 1.0 - abs(2.0 * x - 1.0)                 # 0 -> 1 -> 0
        freq = 620.0 + 760.0 * sweep
        phase += 2 * math.pi * freq / SAMPLE_RATE
        value = math.sin(phase) + 0.42 * math.sin(2 * phase) + 0.2 * math.sin(3 * phase)
        value = math.tanh(1.6 * value / 1.62)             # gentle saturation = louder perceived
        out.append(value * _envelope(i, total, 0.01, 0.25))
    return out


_BUILDERS = {"medium": _medium, "high": _high, "critical": _critical}


def build_wav(level: str) -> bytes:
    """The complete WAV file (bytes) for a level: 'medium', 'high' or 'critical'."""
    level = level if level in _BUILDERS else "medium"
    with _lock:
        if level not in _cache:
            samples = _BUILDERS[level]()
            peak = max((abs(s) for s in samples), default=1.0) or 1.0
            gain = LEVEL_VOLUME[level] / peak
            pcm = array.array("h", (int(max(-1.0, min(1.0, s * gain)) * 32767) for s in samples))
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(SAMPLE_RATE)
                handle.writeframes(pcm.tobytes())
            _cache[level] = buffer.getvalue()
        return _cache[level]


def prewarm() -> None:
    """Build all sounds on a background thread so the first alarm starts instantly."""
    threading.Thread(target=lambda: [build_wav(level) for level in _BUILDERS], daemon=True, name="alarm-prewarm").start()


def play(level: str) -> None:
    """Start the level's alarm (asynchronous). Never raises."""
    try:
        data = build_wav(level)
        if winsound is not None:
            winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_ASYNC)
            return
        # Not Windows (development only): a plain system beep. Qt's sound player can crash
        # outright on machines without an audio device, so it is deliberately not used.
        from PySide6.QtWidgets import QApplication

        if QApplication.instance() is not None:
            QApplication.beep()
        return
    except Exception:
        try:
            from PySide6.QtWidgets import QApplication

            QApplication.beep()
        except Exception:
            pass


def stop() -> None:
    try:
        if winsound is not None:
            winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass
