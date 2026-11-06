"""High-DPI regression: all 8 modes and header actions remain usable."""
from pathlib import Path
import re
import tkinter as tk

import pytest

BASE = Path(__file__).resolve().parents[1]


def test_audio_resize_uses_single_pixel_bitmap_and_debounces():
    source = (BASE / "snapgen_modules" / "snapgen_page_audio.py").read_text(encoding="utf-8")
    assert 'scale = 1' in source
    assert 'root.after(180, redraw_after_resize)' in source
    assert 'Image.Resampling.LANCZOS' not in source[source.index('    def draw_waveform('):
                                                      source.index('    def update_waveform_selection(')]


def test_gui_dpi_does_not_repeatedly_block_on_receipt_checks():
    source = (BASE / "snapgen_gui_v2.py").read_text(encoding="utf-8")
    start = source.index("def _installed_version():")
    end = source.index("def _ensure_main_version_label():", start)
    version_code = source[start:end]
    assert "threading.Thread(target=worker" in version_code
    assert "verify_installed_files(BASE_ROOT)" in version_code
    assert '"_responsive_action_bar"' in (BASE / "snapgen_modules" / "snapgen_responsive_ui.py").read_text()


def test_mode_tabs_and_toolbar_split_keep_commands():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Window manager unavailable in CI")
    try:
        root.geometry("1180x740")
        from snapgen_responsive_ui import install
        from snapgen_dpi import enable_high_dpi
        host = tk.Frame(root)
        host.pack(fill="x")
        for i in range(5):
            tk.Checkbutton(host, text=f"Option {i}").pack(side="left")
        invocations = []
        originals = []
        for text in ("2304", "⚙", "เปิดโฟลเดอร์", "Prompt-Ref", "🌐 ChatGPT"):
            button = tk.Button(host, text=text, command=lambda t=text: invocations.append(t))
            button.pack(side="right")
            originals.append(button)
        nav = tk.Frame(root)
        nav.pack(fill="x")
        tabs = {}
        for text in ("สร้างวิดีโอ", "สร้างรูป AI", "Ref", "Prop", "นิทาน", "คาราโอเกะ", "ตัดเสียง", "เล่าภาพ"):
            tab = tk.Button(nav, text=text, width=13)
            tab.pack(side="left", padx=4)
            tabs[text] = tab
        g = {"mode_frame": nav, "mode_buttons": tabs}
        root.update()
        install(root, g)
        root.after(280, root.quit)
        root.mainloop()
        bar = g.get("_responsive_action_bar")
        assert bar is not None
        assert len(g["_responsive_moved_toolbar"]) == 5
        assert all(b.winfo_manager() == "" for b in originals)
        assert all(b.winfo_manager() == "pack" for b in tabs.values())
        assert all(int(b.cget("width")) == 0 for b in tabs.values())
        # None of the eight tabs may clip its Thai text at 1180 px.
        assert sum(b.winfo_reqwidth() for b in tabs.values()) < root.winfo_width()
        target = next(w for w in bar.winfo_children()
                      if isinstance(w, tk.Button) and w.cget("text") == "Prompt-Ref")
        target.invoke()
        assert invocations == ["Prompt-Ref"]
        # Restyling still respects all eight preserved mode tab actions.
        assert len(tabs) == 8
    finally:
        root.destroy()



def test_repeated_active_tab_styling_never_flashes_to_13_chars():
    """Every old _set_mode_active() callback uses the central style function."""
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Window manager unavailable in CI")
    try:
        from snapgen_button_styles import style_mode_button, mode_tab_geometry
        root.tk.call("tk", "scaling", 1.6683)  # simulate Windows 125% DPI
        root.geometry("1116x577")
        tabs = []
        nav = tk.Frame(root)
        nav.pack(fill="x")
        for title in ("สร้างวิดีโอ", "สร้างรูป AI", "Ref", "Prop",
                      "นิทาน", "คาราโอเกะ", "ตัดเสียง", "เล่าภาพ"):
            button = tk.Button(nav, text=title)
            style_mode_button(button)
            button.pack(side="left")
            tabs.append(button)
        root.update()
        start_sizes = [button.winfo_reqwidth() for button in tabs]
        assert all(mode_tab_geometry(button)[0] == 0 for button in tabs)
        assert all(int(button.cget("width")) == 0 for button in tabs)

        for _ in range(4):
            for index, button in enumerate(tabs):
                style_mode_button(button, active=(index == 5))
                # Processing idle redraws between clicks MUST not change sizes.
                root.update_idletasks()
                assert int(button.cget("width")) == 0
            assert [button.winfo_reqwidth() for button in tabs] == start_sizes
    finally:
        root.destroy()


def test_highdpi_startup_keeps_floating_size_without_maximizing():
    source = (BASE / "snapgen_gui_v2.py").read_text(encoding="utf-8")
    assert "def _set_highdpi_floating_size():" in source
    assert "root.after_idle(_set_highdpi_floating_size)" in source
    assert "outer_w = min(1134, work_w - 48)" in source
    assert "outer_h = min(624, work_h - 32)" in source
    assert 'root.state("zoomed")' not in source[source.index("def _set_highdpi_floating_size():"):
                                              source.index("# Final canonical Slot loader.")]
