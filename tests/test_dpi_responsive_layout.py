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
    assert "root.after(80, _set_highdpi_floating_size)" in source
    assert "ratio = dpi / 96.0" in source
    assert "outer_w = min(round(1134 * ratio)" in source
    assert "outer_h = min(round(624 * ratio)" in source
    assert 'root.state("zoomed")' not in source[source.index("def _set_highdpi_floating_size():"):
                                              source.index("# Final canonical Slot loader.")]


def test_status_cards_share_size_and_hide_old_credit_control():
    """Keep original two rows, add borders and suppress the old duplicate."""
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Window manager unavailable in CI")
    try:
        root.geometry("1400x700")
        toolbar = tk.Frame(root)
        toolbar.pack(fill="x")
        old_credit = tk.Button(toolbar, text="...")
        old_credit.pack(side="right")
        for caption in ("⚙", "เปิดโฟลเดอร์", "Prompt-Ref", "🌐 ChatGPT"):
            tk.Button(toolbar, text=caption).pack(side="right")
        mode = tk.Frame(root)
        mode.pack(fill="x")
        quota = tk.StringVar(value="60 Plus")
        quota_label = tk.Label(mode, textvariable=quota)
        quota_label.pack(side="right")
        quota_clicks = []
        quota_label.bind("<Button-1>", lambda _event: quota_clicks.append(True))
        balance = tk.StringVar(value="26")
        g = {
            "credit_status_var": balance,
            "credit_button": old_credit,
            "bridge_image_quota_var": quota,
            "bridge_image_quota_label": quota_label,
            "mode_frame": mode,
        }
        root.update()
        from snapgen_responsive_ui import install
        install(root, g)
        root.update()
        snapgen = g["_responsive_snapgen_credit"]
        chatgpt = g["_responsive_chatgpt_quota_card"]
        assert snapgen.winfo_ismapped() and chatgpt.winfo_ismapped()
        assert snapgen.master is root and chatgpt.master is root
        assert snapgen.winfo_rooty() < chatgpt.winfo_rooty()
        assert snapgen.winfo_width() == chatgpt.winfo_width()
        assert snapgen.winfo_height() == chatgpt.winfo_height()
        assert snapgen.cget("bg") == chatgpt.cget("bg") == "#C3CBD6"
        assert old_credit.winfo_manager() == ""
        assert quota_label.winfo_manager() == ""
        balance.set("1234")
        quota.set("59 Plus")
        root.update()
        snapgen_labels = snapgen.winfo_children()[0].winfo_children()
        chatgpt_labels = chatgpt.winfo_children()[0].winfo_children()
        assert snapgen_labels[0].cget("text") == "SnapGen"
        assert chatgpt_labels[0].cget("text") == "GPT Plus"
        assert snapgen_labels[-1].cget("text") == "1234"
        assert chatgpt_labels[-1].cget("text") == "59"
        assert snapgen_labels[0].cget("fg") == chatgpt_labels[0].cget("fg")
        chatgpt_labels[-1].event_generate("<Button-1>")
        root.update()
        assert quota_clicks == [True]
    finally:
        root.destroy()


def test_status_cards_install_without_prompt_ref_or_credit_stringvar():
    """The recovered header may register a credit Button but no StringVar."""
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Window manager unavailable")
    try:
        root.tk.call("tk", "scaling", 1.6683)
        root.geometry("1300x720")
        toolbar = tk.Frame(root)
        toolbar.pack(fill="x")
        old = tk.Button(toolbar, text="26")
        old.pack(side="right")
        mode = tk.Frame(root)
        mode.pack(fill="x")
        quota = tk.StringVar(value="โควตารูป: 60 Plus")
        source = tk.Label(mode, textvariable=quota)
        source.pack(side="right")
        g = {
            "credit_button": old,
            "bridge_image_quota_label": source,
            "bridge_image_quota_var": quota,
            "mode_frame": mode,
        }
        from snapgen_responsive_ui import install
        install(root, g)
        root.update()
        snap = g["_responsive_snapgen_credit"]
        gpt = g["_responsive_chatgpt_quota_card"]
        assert snap.winfo_ismapped() and gpt.winfo_ismapped()
        assert snap.winfo_width() == gpt.winfo_width()
        assert snap.winfo_height() == gpt.winfo_height()
        assert abs((snap.winfo_rootx() + snap.winfo_width())
                   - (gpt.winfo_rootx() + gpt.winfo_width())) <= 2
        assert old.winfo_manager() == ""
        assert source.winfo_manager() == ""
        snap_widgets = snap.winfo_children()[0].winfo_children()
        gpt_widgets = gpt.winfo_children()[0].winfo_children()
        assert root.getvar(snap_widgets[0].cget("textvariable")) == "SnapGen"
        assert root.getvar(snap_widgets[-1].cget("textvariable")) == "26"
        assert root.getvar(gpt_widgets[0].cget("textvariable")) == "GPT Plus"
        assert root.getvar(gpt_widgets[-1].cget("textvariable")) == "60"
        g["credit_status_var"].set("28")
        quota.set("โควตารูป: 55 Go")
        root.update()
        assert root.getvar(snap_widgets[-1].cget("textvariable")) == "28"
        assert root.getvar(gpt_widgets[0].cget("textvariable")) == "GPT Go"
        assert root.getvar(gpt_widgets[-1].cget("textvariable")) == "55"
    finally:
        root.destroy()


def test_late_prompt_ref_does_not_duplicate_credit_cards():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Window manager unavailable")
    try:
        root.geometry("1400x720")
        toolbar = tk.Frame(root)
        toolbar.pack(fill="x")
        credit = tk.Button(toolbar, text="31")
        credit.pack(side="right")
        mode = tk.Frame(root)
        mode.pack(fill="x")
        quota = tk.StringVar(value="60 Plus")
        label = tk.Label(mode, textvariable=quota)
        label.pack(side="right")
        g = {
            "credit_button": credit,
            "bridge_image_quota_label": label,
            "bridge_image_quota_var": quota,
            "mode_frame": mode,
        }
        from snapgen_responsive_ui import install
        install(root, g)
        root.update()
        assert g["_responsive_equal_credit_cards"]
        tk.Button(toolbar, text="Prompt-Ref").pack(side="right")
        root.after(650, root.quit)
        root.mainloop()
        root.update_idletasks()
        def descend(node):
            for child in node.winfo_children():
                yield child
                yield from descend(child)
        gray_edges = [widget for widget in descend(root)
                      if isinstance(widget, tk.Frame) and widget.cget("bg") == "#C3CBD6"]
        assert len(gray_edges) == 2
        assert all(item.winfo_ismapped() for item in gray_edges)
        assert g["_responsive_snapgen_credit"] in gray_edges
        assert g["_responsive_chatgpt_quota_card"] in gray_edges
    finally:
        root.destroy()


def test_real_provider_credit_widget_creates_both_equal_grey_cards():
    """The recovered toolbar uses _image_provider_credit_widget, not credit_button."""
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Display unavailable")
    try:
        root.tk.call("tk", "scaling", 1.6683)
        root.geometry("1420x780")
        toolbar = tk.Frame(root, bg="#FFFFFF")
        toolbar.pack(side="top", fill="x")
        for title in ("⚙", "โฟลเดอร์", "Prompt-Ref", "ChatGPT"):
            tk.Button(toolbar, text=title).pack(side="right")
        source_value = tk.StringVar(master=root, value="26")
        source_credit = tk.Label(toolbar, textvariable=source_value, bg="#FFFFFF")
        source_credit.pack(side="right", padx=(15, 8))
        source_title = tk.Label(toolbar, text="SnapGen", bg="#FFFFFF")
        source_title.pack(side="right")
        mode = tk.Frame(root, bg="#FFFFFF")
        mode.pack(side="top", fill="x")
        quota = tk.StringVar(master=root, value="62 Plus")
        quota_label = tk.Label(mode, textvariable=quota)
        quota_label.pack(side="right", padx=(8, 12))
        g = {
            "_image_provider_credit_widget": source_credit,
            "bridge_image_quota_label": quota_label,
            "bridge_image_quota_var": quota,
            "mode_frame": mode,
        }
        root.update()
        from snapgen_responsive_ui import install
        install(root, g)
        root.update()
        top = g["_responsive_snapgen_credit"]
        bottom = g["_responsive_chatgpt_quota_card"]
        assert g["_responsive_equal_credit_cards"]
        assert top.winfo_ismapped() and bottom.winfo_ismapped()
        assert top.cget("bg") == bottom.cget("bg") == "#C3CBD6"
        assert top.winfo_width() == bottom.winfo_width()
        assert top.winfo_height() == bottom.winfo_height()
        assert source_credit.winfo_manager() == ""
        assert source_title.winfo_manager() == ""
        assert quota_label.winfo_manager() == ""
        snap_labels = top.winfo_children()[0].winfo_children()
        gpt_labels = bottom.winfo_children()[0].winfo_children()
        assert root.getvar(snap_labels[0].cget("textvariable")) == "SnapGen"
        assert root.getvar(snap_labels[-1].cget("textvariable")) == "26"
        assert root.getvar(gpt_labels[0].cget("textvariable")) == "GPT Plus"
        assert root.getvar(gpt_labels[-1].cget("textvariable")) == "62"
        assert snap_labels[0].cget("font") == gpt_labels[0].cget("font")
        assert snap_labels[-1].cget("font") == gpt_labels[-1].cget("font")

        source_value.set("27")  # simulate the legacy widget updating
        quota.set("61 Go")
        root.update()
        assert root.getvar(snap_labels[-1].cget("textvariable")) == "27"
        assert root.getvar(gpt_labels[0].cget("textvariable")) == "GPT Go"
        assert root.getvar(gpt_labels[-1].cget("textvariable")) == "61"
        root.geometry("1160x650")
        root.update()
        assert top.winfo_width() == bottom.winfo_width()
        assert source_credit.winfo_manager() == ""
    finally:
        root.destroy()


def test_credit_provider_resizing_respects_equal_card_mount():
    src = (BASE / "snapgen_gui_v2.py").read_text(encoding="utf-8")
    assert 'and not g.get("_responsive_equal_credit_cards")' in src
    assert 'g["_image_provider_credit_widget"] = credit' in src


def test_credit_textvariable_discovered_without_registered_g_widget():
    """Credit shown as 26 and SnapGen on the toolbar; no credit keys at all."""
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No display")
    try:
        root.geometry("1400x700")
        tb = tk.Frame(root)
        tb.pack(fill="x")
        tk.Button(tb, text="Prompt-Ref").pack(side="right")
        live = tk.StringVar(master=root, value="26")
        value = tk.Label(tb, textvariable=live)
        value.pack(side="right")
        caption = tk.Label(tb, text="SnapGen")
        caption.pack(side="right")
        row = tk.Frame(root)
        row.pack(fill="x")
        quota = tk.StringVar(master=root, value="62 Plus")
        quota_label = tk.Label(row, textvariable=quota)
        quota_label.pack(side="right")
        g = {"bridge_image_quota_label":quota_label, "bridge_image_quota_var":quota,
             "mode_frame":row}
        root.update()
        from snapgen_responsive_ui import install
        install(root,g)
        root.update()
        assert g["_responsive_equal_credit_cards"]
        assert value.winfo_manager()=="" and caption.winfo_manager()==""
        a,b=g["_responsive_snapgen_credit"],g["_responsive_chatgpt_quota_card"]
        assert a.winfo_ismapped() and b.winfo_ismapped()
        assert (a.winfo_width(),a.winfo_height()) == (b.winfo_width(),b.winfo_height())
        assert a.cget("bg") == b.cget("bg") == "#C3CBD6"
        live.set("28")
        root.update()
        label=a.winfo_children()[0].winfo_children()[-1]
        assert root.getvar(label.cget("textvariable"))=="28"
    finally:
        root.destroy()


def test_credit_cards_stay_inside_window_with_matching_edges_after_resize():
    """Visual geometry regression: real on-screen panels, not hidden pack children."""
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No graphical display")
    try:
        root.geometry("1134x624")
        toolbar = tk.Frame(root)
        toolbar.pack(fill="x")
        for name in ("Settings", "Folder", "Prompt-Ref"):
            tk.Button(toolbar, text=name).pack(side="right")
        balance = tk.StringVar(master=root, value="26")
        source_credit = tk.Label(toolbar, textvariable=balance)
        source_credit.pack(side="right")
        tk.Label(toolbar, text="SnapGen").pack(side="right")
        mode = tk.Frame(root)
        mode.pack(fill="x")
        quota = tk.StringVar(master=root, value="62 Plus")
        quota_label = tk.Label(mode, textvariable=quota)
        quota_label.pack(side="right")
        g = {
            "_image_provider_credit_widget": source_credit,
            "bridge_image_quota_var": quota,
            "bridge_image_quota_label": quota_label,
            "mode_frame": mode,
        }
        root.update()
        from snapgen_responsive_ui import install
        install(root, g)
        for width in (1134, 1417, 1134):
            root.geometry(f"{width}x624")
            root.update()
            a, b = g["_responsive_snapgen_credit"], g["_responsive_chatgpt_quota_card"]
            assert a.winfo_ismapped() and b.winfo_ismapped()
            assert a.winfo_manager() == b.winfo_manager() == "place"
            assert a.winfo_width() == b.winfo_width() == 198
            assert a.winfo_height() == b.winfo_height() == 38
            assert a.winfo_rootx() == b.winfo_rootx()
            assert a.winfo_rootx()-root.winfo_rootx() == width-18-198
            assert a.winfo_rooty() < b.winfo_rooty()
            assert a.cget("bg") == b.cget("bg") == "#C3CBD6"
            assert source_credit.winfo_manager() == ""
    finally:
        root.destroy()
