# -*- coding: utf-8 -*-
"""Compact, explicitly reviewed clip-effect picker for Video Auto.

The plan's dialogue markers take priority over inferred audio events. YAMNet
and Silero provide suggestions only; the export separately rechecks selected
clips before mixing to prevent speech/music leaking into the narration.
"""
from __future__ import annotations

import math
import queue
import threading
import tkinter as tk
from tkinter import ttk

DEFAULT_SELECTED_CLIPS = (2, 5, 9, 14, 17, 22, 26, 31)
SPEECH_REASONS = frozenset(("voice_detected", "speech_vad_detected"))


def suggested_status(scene, result):
    """The project dialogue plan takes precedence over the audio classifier."""
    reason = str((result or {}).get("reason") or "not_checked")
    if scene.get("dialogue") or reason in SPEECH_REASONS:
        return "speech"
    if result is None:
        # A prompt is only a hint until the sound itself has been inspected.
        return "effect" if str(scene.get("sound_effects") or "").strip() else "unknown"
    return "effect" if reason == "included" else "unknown"


def scan_effect_statuses(ffmpeg, scenes, durations, *, log=lambda _msg: None,
                         check_stop=lambda: None, progress=None, on_status=None):
    """Read clip audio on CPU; no paid generation or GPU processing."""
    from snapgen_audio_sfx import _analyze_one, _load

    statuses = []
    try:
        runtime = _load()
    except Exception as exc:
        log("ตัวตรวจเสียงเอฟเฟกต์ไม่พร้อม — ใช้ป้ายบทพูดจากแผนฉากแทน (" +
            type(exc).__name__ + ")")
        return [suggested_status(scene, None) for scene in scenes]
    total = len(scenes)
    for index, scene in enumerate(scenes):
        check_stop()
        try:
            if index >= len(durations):
                result = {"reason": "missing_duration"}
            else:
                result = _analyze_one(scene, ffmpeg, durations[index], runtime,
                                      preview_only=True)
        except Exception:
            result = {"reason": "scan_failed"}
        status = suggested_status(scene, result)
        statuses.append(status)
        if callable(on_status):
            on_status(index, status)
        if callable(progress):
            progress(index + 1, total)
    return statuses


def normalized_selection(selected, count):
    """Keep checked shot numbers in natural 1-based storyboard order."""
    return sorted({int(number) for number in selected or ()
                   if str(number).isdigit() and 1 <= int(number) <= count})


def show_selector(parent, scenes, statuses, selected=None, scan=None):
    """Tk main-thread modal; None means canceled, [] means no clip effects."""
    count = len(scenes)
    initial = normalized_selection(
        DEFAULT_SELECTED_CLIPS if selected is None else selected, count)
    result = {"selected": None}
    dialog = tk.Toplevel(parent)
    dialog.title("เลือกเสียงประกอบก่อนรวมวิดีโอ")
    dialog.configure(bg="#FFFFFF")
    dialog.resizable(False, True)
    dialog.transient(parent.winfo_toplevel())
    stop_scan = threading.Event()

    def dismiss():
        stop_scan.set()
        dialog.destroy()

    dialog.protocol("WM_DELETE_WINDOW", dismiss)

    outer = tk.Frame(dialog, bg="#FFFFFF")
    outer.pack(fill="both", expand=True, padx=15, pady=13)
    tk.Label(outer, text="เลือกเสียงประกอบก่อนรวมวิดีโอ", bg="#FFFFFF",
             fg="#344054", font=("Segoe UI", 11, "bold")).pack(anchor="w")
    # Short legend only; all cards show their index, not verbose descriptions.
    tk.Label(
        outer, text="เขียว = เอฟเฟกต์  ·  แดง = บทพูด  ·  เทา = ไม่พบเสียง",
        bg="#FFFFFF", fg="#667085", font=("Segoe UI", 9)
    ).pack(anchor="w", pady=(4, 2))
    tk.Label(
        outer, text="เป็นเพียงการคาดเดาของโปรแกรมเท่านั้น",
        bg="#FFFFFF", fg="#98A2B3", font=("Segoe UI", 8)
    ).pack(anchor="w", pady=(0, 8))
    base = tk.Frame(outer, bg="#FFFFFF")
    base.pack(fill="both", expand=True)
    rows = math.ceil(count / 8)
    canvas = tk.Canvas(base, width=720, height=min(420, max(76, rows * 47 + 8)),
                       bg="#FFFFFF", highlightthickness=0)
    scroll = ttk.Scrollbar(base, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    grid = tk.Frame(canvas, bg="#FFFFFF")
    grid_id = canvas.create_window((0, 0), window=grid, anchor="nw")
    grid.bind("<Configure>", lambda _ev: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda ev: canvas.itemconfigure(grid_id, width=ev.width))
    for col in range(8):
        grid.grid_columnconfigure(col, weight=1, uniform="effect")
    values = []
    cards = []
    colors = {"effect": ("#ECF8EF", "#31754B"),
              "speech": ("#FFF0F0", "#AC4949"),
              "unknown": ("#F3F4F6", "#667085")}
    for index in range(count):
        number = index + 1
        variable = tk.BooleanVar(value=number in initial)
        status = statuses[index] if index < len(statuses) else "unknown"
        bg, fg = colors.get(status, colors["unknown"])
        card = tk.Checkbutton(
            grid, text=f"{number:03d}", variable=variable,
            bg=bg, fg=fg, selectcolor="#FFFFFF", activebackground=bg,
            font=("Segoe UI", 9), width=6, height=2, anchor="w",
            relief="flat", bd=1, padx=3, cursor="hand2",
        )
        card.grid(row=index // 8, column=index % 8,
                  padx=3, pady=3, sticky="nsew")
        values.append(variable)
        cards.append(card)

    footer = tk.Frame(outer, bg="#FFFFFF")
    footer.pack(fill="x", pady=(10, 0))
    count_label = tk.Label(footer, bg="#FFFFFF", fg="#667085",
                           font=("Segoe UI", 9))
    count_label.pack(side="left")
    def refresh_count():
        count_label.configure(text=f"เลือก {sum(v.get() for v in values)} / {count} คลิป")
    for variable in values:
        variable.trace_add("write", lambda *_: refresh_count())
    refresh_count()

    def finish():
        result["selected"] = [i + 1 for i, var in enumerate(values) if var.get()]
        dismiss()

    def update_status(index, status):
        if stop_scan.is_set() or not dialog.winfo_exists():
            return
        if index < 0 or index >= len(cards):
            return
        bg, fg = colors.get(status, colors["unknown"])
        cards[index].configure(bg=bg, fg=fg, activebackground=bg)

    updates = queue.Queue()

    def poll_updates():
        if stop_scan.is_set() or not dialog.winfo_exists():
            return
        while not updates.empty():
            index, status = updates.get_nowait()
            update_status(index, status)
        dialog.after(60, poll_updates)

    def begin_scan():
        if scan is None or stop_scan.is_set():
            return

        def send_update(index, status):
            if not stop_scan.is_set():
                # Tk controls must never be touched by a classifier worker.
                updates.put((index, status))

        def analyze():
            try:
                scan(send_update, stop_scan)
            except Exception:
                # No classifier result is treated as a guaranteed safe effect.
                pass

        threading.Thread(target=analyze, name="AudioEffectPreview",
                         daemon=True).start()

    dialog.after_idle(begin_scan)
    dialog.after(60, poll_updates)

    tk.Button(footer, text="ยืนยันและรวมวิดีโอ", command=finish,
              bg="#2563EB", fg="#FFFFFF", relief="flat",
              padx=13, pady=6, font=("Segoe UI", 9, "bold")).pack(side="right")
    tk.Button(footer, text="ยกเลิก", command=dismiss,
              bg="#F3F4F6", fg="#475467", relief="flat",
              padx=12, pady=6, font=("Segoe UI", 9)).pack(side="right", padx=7)
    dialog.grab_set()
    dialog.wait_window()
    return result["selected"]


def request_selection(root, page, scenes, statuses, selected=None, scan=None):
    """Pause worker until the main-thread reviewer confirms or cancels."""
    completed = threading.Event()
    answer = {"selected": None}

    def ask():
        try:
            answer["selected"] = show_selector(page, scenes, statuses, selected, scan=scan)
        finally:
            completed.set()
    root.after(0, ask)
    completed.wait()
    return answer["selected"]
