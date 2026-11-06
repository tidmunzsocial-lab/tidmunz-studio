"""Windows DPI awareness for the main Tidmunz Studio Tk process.

Call before importing tkinter or creating a window.  Never change system-wide
display scaling: Windows must render the app at its real monitor DPI.
"""
from __future__ import annotations

import ctypes
import os


def enable_high_dpi() -> str:
    """Enable per-monitor v2; fall back safely on older Windows versions."""
    if os.name != "nt":
        return "non-windows"
    try:
        user = ctypes.WinDLL("user32", use_last_error=True)
        modern = getattr(user, "SetProcessDpiAwarenessContext", None)
        if modern is not None:
            modern.argtypes = [ctypes.c_void_p]
            modern.restype = ctypes.c_bool
            if modern(ctypes.c_void_p(-4)):  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
                return "per-monitor-v2"
        try:
            shcore = ctypes.WinDLL("shcore")
            fn = shcore.SetProcessDpiAwareness
            fn.argtypes = [ctypes.c_int]
            fn.restype = ctypes.c_long
            if fn(2) == 0:  # PROCESS_PER_MONITOR_DPI_AWARE
                return "per-monitor"
        except (AttributeError, OSError):
            pass
        legacy = user.SetProcessDPIAware
        legacy.restype = ctypes.c_bool
        if legacy():
            return "system"
        return "already-configured"
    except (AttributeError, OSError, ValueError):
        return "unavailable"
