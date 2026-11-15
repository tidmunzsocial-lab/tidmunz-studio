"""Standalone Topaz drop zone on the Auto page; never mutates Auto project state."""
from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


def install(parent, root):
    """Create the right-side video drop card. UI events stay on Tk's thread."""
    card = tk.Frame(parent, bg="#E8F0FB", highlightbackground="#6B90BF",
                    highlightthickness=1, width=320, height=122)
    card.pack(side="right", fill="y", padx=(7, 0))
    card.pack_propagate(False)
    title = tk.Label(card, text="ลากวิดีโอใส่เพื่อสโลว์", bg="#E8F0FB",
                     fg="#15345D", font=("TkDefaultFont", 10, "bold"))
    title.pack(pady=(7, 0))
    hint = tk.Label(card, text="Topaz · สโลว์ 2× + ขยาย 2K", bg="#E8F0FB",
                    fg="#475569", font=("TkDefaultFont", 9))
    hint.pack()
    progress_var = tk.StringVar(value="วางไฟล์วิดีโอได้เลย")
    status = tk.Label(card, textvariable=progress_var, bg="#E8F0FB",
                      fg="#334155", font=("TkDefaultFont", 8))
    status.pack(fill="x", padx=7)
    bar = ttk.Progressbar(card, maximum=100)
    bar.pack(fill="x", padx=12, pady=(2, 1))
    busy = {"value": False}
    chosen = {"last": None}

    def update(message=None, percent=None):
        if not card.winfo_exists():
            return
        if message is not None:
            progress_var.set(str(message)[:60])
        if percent is not None:
            bar.configure(value=max(0, min(100, int(percent))))

    def handle_video(path):
        source = Path(str(path).strip())
        if busy["value"]:
            update("กำลังประมวลผลคลิปก่อนหน้า")
            return
        if source.suffix.lower() not in VIDEO_EXTENSIONS or not source.is_file():
            update("รองรับ MP4 / MOV / MKV / AVI / WEBM")
            return
        busy["value"] = True
        button.configure(state="disabled")
        chosen["last"] = None
        update("เริ่มประมวลผล Topaz ...", 0)

        def worker():
            try:
                from ai_slow2x import make_topaz_slow2x_2k

                def on_progress(backend, percent):
                    root.after(0, update, f"Topaz: {percent}% · {source.name}", percent)
                result = make_topaz_slow2x_2k(
                    str(source), progress=on_progress)
                def done():
                    chosen["last"] = result
                    busy["value"] = False
                    button.configure(state="normal", text="เปิดไฟล์ที่เสร็จ")
                    button.configure(command=lambda: os.startfile(result))
                    update("✓ เสร็จแล้ว · " + Path(result).name, 100)
                root.after(0, done)
            except Exception as exc:
                def failed(detail=str(exc)):
                    busy["value"] = False
                    button.configure(state="normal", text="เลือกวิดีโอ")
                    button.configure(command=choose_file)
                    update("ผิดพลาด: " + detail, 0)
                    messagebox.showerror("Topaz Slow 2× / 2K", detail, parent=card)
                root.after(0, failed)
        threading.Thread(target=worker, daemon=True).start()

    def choose_file():
        source = filedialog.askopenfilename(
            parent=card, title="เลือกวิดีโอเพื่อสโลว์ 2× และขยาย 2K",
            filetypes=[("วิดีโอ", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v"),
                       ("ทุกไฟล์", "*.*")])
        if source:
            handle_video(source)

    button = tk.Button(card, text="เลือกวิดีโอ", command=choose_file,
                       bg="#FFFFFF", fg="#15345D", relief="solid",
                       bd=1, padx=9, font=("TkDefaultFont", 8))
    button.pack(pady=(3, 4))

    # Uses the app's bundled tkinterdnd2 and its native tkdnd library.
    # The file-picker remains available when shell drag/drop is restricted.
    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD
        TkinterDnD._require(root)
        for widget in (card, title, hint, status, bar):
            widget.drop_target_register(DND_FILES)
            def dropped(event):
                paths = root.tk.splitlist(event.data)
                if paths:
                    handle_video(paths[0])
                return "copy"
            widget.dnd_bind("<<Drop>>", dropped)
        hint.configure(text="Topaz · สโลว์ 2× + ขยาย 2K · วางไฟล์ได้")
    except Exception:
        hint.configure(text="Topaz · สโลว์ 2× + 2K · กดเลือกไฟล์")
    return card
