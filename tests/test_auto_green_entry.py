"""Slot 2 auto-entry must be visibly green and keep its click action."""
import tkinter as tk

import pytest

import snapgen_page_narrate as narrate


def test_auto_entry_green_click_hover_and_keyboard(monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable")
    try:
        root.geometry("820x600")
        host = tk.Frame(root)
        host.pack(fill="both", expand=True)
        prompts = []
        for _index in range(2):
            slot = tk.Frame(host, height=200)
            slot.pack(fill="x")
            slot.pack_propagate(False)
            body = tk.Frame(slot)
            body.pack()
            content = tk.Frame(body)
            content.pack()
            prompt = tk.Text(content, width=20, height=1)
            prompt.pack()
            prompts.append(prompt)
        refreshed = []
        monkeypatch.setattr(
            narrate, "_build",
            lambda *_a, **_kw: {
                "stage_var": tk.StringVar(master=root, value="Idle"),
                "refresh_clip_info": lambda: refreshed.append(True),
            },
        )
        g = {"slot_prompts": prompts}
        panel = narrate.install_video_auto(g, root)
        root.update()
        slot = prompts[1].master.master.master
        card = next(w for w in slot.winfo_children()
                    if isinstance(w, tk.Frame) and w.winfo_manager() == "place")
        inner = next(w for w in card.winfo_children() if isinstance(w, tk.Frame))
        button = next(w for w in inner.winfo_children()
                      if isinstance(w, tk.Canvas))
        rect = next(item for item in button.find_all()
                    if button.type(item) == "rectangle")
        caption = next(item for item in button.find_all()
                       if button.type(item) == "text")
        assert button.itemcget(rect, "fill") == "#16A34A"
        assert button.itemcget(caption, "fill") == "#FFFFFF"
        assert button.itemcget(caption, "text") == "เปิดหน้าออโต้"
        assert button.cget("cursor") == "hand2"
        button.event_generate("<Enter>")
        assert button.itemcget(rect, "fill") == "#15803D"
        button.event_generate("<Leave>")
        assert button.itemcget(rect, "fill") == "#16A34A"
        button.event_generate("<Button-1>")
        root.update()
        assert panel.winfo_manager() == "place"
        assert refreshed == [True]
        g["video_auto_hide"]()
        button.focus_force()
        root.update()
        button.event_generate("<Return>")
        root.update()
        assert panel.winfo_manager() == "place"
        assert refreshed == [True, True]
    finally:
        root.destroy()
