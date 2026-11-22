# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
"""Stops Windows from going to sleep while CampusGuard is watching cameras.

A sleeping PC watches nothing. On Windows this asks the system to stay awake (the screen may
still turn off). A laptop with its lid closed can still sleep depending on the power plan:
set "When I close the lid: Do nothing" in Windows power settings for an unattended laptop.
Does nothing on other systems.
"""
from __future__ import annotations

import logging
import sys
import threading

log = logging.getLogger(__name__)

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

_stop: threading.Event | None = None
_thread: threading.Thread | None = None
_lock = threading.Lock()


def _set_execution_state(flags: int) -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        return bool(ctypes.windll.kernel32.SetThreadExecutionState(flags))
    except Exception as error:      # never let this stop detection
        log.warning("could not change the sleep setting: %s", error)
        return False


def _hold(stop: threading.Event) -> None:
    # The request lasts as long as the thread that made it, so a dedicated thread holds it.
    _set_execution_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    stop.wait()
    _set_execution_state(ES_CONTINUOUS)


def set_active(active: bool) -> None:
    """Turn the 'stay awake' request on or off (safe to call repeatedly)."""
    global _stop, _thread
    with _lock:
        if active and _thread is None:
            _stop = threading.Event()
            _thread = threading.Thread(target=_hold, args=(_stop,), name="keep-awake", daemon=True)
            _thread.start()
        elif not active and _thread is not None and _stop is not None:
            _stop.set()
            _thread.join(timeout=2)
            _thread, _stop = None, None


def is_active() -> bool:
    with _lock:
        return _thread is not None
