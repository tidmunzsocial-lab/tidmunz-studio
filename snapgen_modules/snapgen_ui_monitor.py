"""Low-overhead UI responsiveness diagnostics for intermittent Tk freezes.

Never blocks Tk and does not record prompts, credentials, widget contents, or
function argument values. Logs only a timestamp, delay and Python call frames.
"""
from __future__ import annotations

import atexit
import sys
import threading
import time
import traceback
from pathlib import Path


def install(root, log_path, *, interval_ms=250, threshold_seconds=1.25):
    if getattr(root, "_tidmunz_ui_monitor", False):
        return
    root._tidmunz_ui_monitor = True
    path = Path(log_path)
    owner_thread = threading.get_ident()
    last_tick = [time.monotonic()]
    stop = threading.Event()
    atexit.register(stop.set)

    def pulse():
        last_tick[0] = time.monotonic()
        try:
            root.after(interval_ms, pulse)
        except Exception:
            stop.set()

    def monitor():
        last_recorded = 0.0
        while not stop.wait(0.5):
            now = time.monotonic()
            delay = now - last_tick[0]
            if delay < threshold_seconds or now - last_recorded < 15.0:
                continue
            last_recorded = now
            frame = sys._current_frames().get(owner_thread)
            if frame is None:
                continue
            # Function names/line numbers are safe diagnostics. Do NOT include
            # source-code lines or local variables (may contain private data).
            stack = traceback.extract_stack(frame, limit=12)
            lines = [f"{Path(f.filename).name}:{f.lineno}:{f.name}" for f in stack]
            entry = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] GUI stalled {delay:.2f}s\n" + "\n".join(lines) + "\n\n"
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.is_file() and path.stat().st_size > 250_000:
                    path.replace(path.with_suffix(".old.log"))
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(entry)
            except OSError:
                pass

    root.after(interval_ms, pulse)
    threading.Thread(target=monitor, name="tidmunz-ui-stall-monitor", daemon=True).start()
