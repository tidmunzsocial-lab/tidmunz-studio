"""Keep every Tidmunz toolbar action reachable at 125%+ Windows DPI.

The recovered Tk app supplies a single packed header that was designed for
96 DPI. Extra Chrome/Prompt-Ref/microphone controls grew that one row past the
window edge. This adapter creates a second action row, leaving checkboxes in
the first. Existing callback-owning widgets stay alive but hidden: clones
invoke them, so no workflow, credit balance or settings state is rewritten.
"""
from __future__ import annotations

import re
import tkinter as tk


def split_gpt_quota(value):
    """Convert the live quota string to a short title and right-aligned count."""
    raw = str(value or "").strip()
    plan = re.search(r"\b(Plus|Pro|Go|Free|Business|Enterprise)\b", raw, re.I)
    title = "GPT" + (" " + plan.group(1).title() if plan else "")
    count = re.search(r"\d[\d,]*(?:\.\d+)?", raw)
    return title, (count.group() if count else "—")


def _displayed_label_text(root, widget):
    """Read the text actually shown by a Tk label, including textvariable."""
    try:
        variable = str(widget.cget("textvariable") or "")
        if variable:
            return str(root.getvar(variable)).strip()
    except (tk.TclError, KeyError):
        pass
    try:
        return str(widget.cget("text") or "").strip()
    except (tk.TclError, KeyError):
        return ""


def _find_snapgen_credit_widget(root):
    """Find the real number next to the SnapGen header, even without g keys.

    Some recovered headers set a StringVar rather than the Label text, so the
    original provider scan missed the numeric balance entirely.
    """
    nodes, queue = [], [root]
    while queue:
        widget = queue.pop()
        try:
            queue.extend(widget.winfo_children())
            if widget.winfo_class() in ("Label", "TLabel", "Button", "TButton"):
                if widget.winfo_manager() and widget.winfo_rooty()-root.winfo_rooty() < 180:
                    nodes.append(widget)
        except tk.TclError:
            continue
    names = [w for w in nodes if _displayed_label_text(root, w) == "SnapGen"]
    numbers = [w for w in nodes if re.fullmatch(r"\d[\d,]*(?:\.\d+)?",
                                                 _displayed_label_text(root, w))]
    matches = []
    for title in names:
        for value in numbers:
            dx = value.winfo_rootx() - (title.winfo_rootx() + title.winfo_width())
            dy = abs(value.winfo_rooty() - title.winfo_rooty())
            if -12 <= dx <= 320 and dy <= 28:
                matches.append((abs(dx) + dy, value))
    return min(matches, key=lambda item: item[0])[1] if matches else None


def _find_prompt_ref(root):
    queue = [root]
    while queue:
        node = queue.pop()
        try:
            if (isinstance(node, tk.Button) and
                    "Prompt-Ref" in str(node.cget("text")) and
                    node.winfo_manager() == "pack"):
                return node
            queue.extend(node.winfo_children())
        except tk.TclError:
            continue
    return None


def _action_widget(original):
    """A packed top-right toolbar control; checkboxes stay in their own row."""
    try:
        if original.winfo_manager() != "pack":
            return False
        if original.pack_info().get("side") != "right":
            return False
        if isinstance(original, tk.Checkbutton):
            return False
        if isinstance(original, (tk.Button, tk.Menubutton)):
            return True
        if isinstance(original, tk.Label):
            value = str(original.cget("text") or "").strip()
            return bool(value) and (value.replace(",", "").isdigit() or "เครดิต" in value)
        if isinstance(original, tk.Frame):
            return any(isinstance(c, tk.Button) for c in original.winfo_children())
    except tk.TclError:
        pass
    return False


def _clone_action(row, original, font):
    if isinstance(original, tk.Frame):
        button = next((c for c in original.winfo_children() if isinstance(c, tk.Button)), None)
        if button is None:
            return None
        original = button
    if isinstance(original, tk.Button):
        text = str(original.cget("text") or "")
        compact = {"🌐 ChatGPT": "ChatGPT", "เปิดโฟลเดอร์": "โฟลเดอร์"}
        control = tk.Button(
            row, text=compact.get(text, text),
            command=original.invoke,
            bg=original.cget("bg"), fg=original.cget("fg"),
            activebackground=original.cget("activebackground"),
            activeforeground=original.cget("activeforeground"),
            relief="flat", bd=0, padx=10, pady=5,
            font=font, cursor="hand2",
            highlightthickness=0)
        if text == "🎙️":
            control.configure(text="🎙", padx=6)
        return control
    if isinstance(original, tk.Label):
        control = tk.Label(row, text=original.cget("text"),
                           bg=original.cget("bg"), fg=original.cget("fg"),
                           padx=7, font=font)
        variable = str(original.cget("textvariable") or "")
        if variable:
            control.configure(textvariable=variable)
        return control
    if isinstance(original, tk.Menubutton):
        # Keep original menu on row one; Menu Tk handles cannot be cloned safely.
        return None
    return None


def install(root, g, *, font=("Segoe UI", 9, "bold")):
    """Run once after the page builders finish; then throttle resize geometry."""
    if getattr(root, "_tidmunz_responsive_installed", False):
        return
    root._tidmunz_responsive_installed = True
    mode_frame = g.get("mode_frame")
    modes = g.get("mode_buttons") or {}
    def attach_action_bar(attempt=0):
        if g.get("_responsive_action_bar") is not None:
            return
        prompt_ref = _find_prompt_ref(root)
        if prompt_ref is None:
            # Recovered bytecode sometimes creates the top bar a few hundred
            # milliseconds after modular pages. Never permanently skip it.
            if attempt < 12:
                root.after(300, lambda: attach_action_bar(attempt + 1))
            return
        toolbar = prompt_ref.master
        try:
            originals = [w for w in toolbar.winfo_children() if _action_widget(w)]
            parent = toolbar.master
            if originals and toolbar.winfo_manager() == "pack":
                actions = tk.Frame(parent, bg="#FFFFFF", height=52)
                actions.pack(side="top", fill="x", after=toolbar, padx=7, pady=(0, 2))
                actions.pack_propagate(False)
                # Keep a dedicated credit column clear of toolbar actions.
                credit_gutter = tk.Frame(actions, bg="#FFFFFF", width=216, height=1)
                credit_gutter.pack(side="right")
                g["_responsive_credit_gutter"] = credit_gutter
                # Reuse original live balances, retain each original toolbar
                # row and apply the same soft-grey card treatment to both.
                CARD_BG = "#EDF1F5"
                CARD_EDGE = "#98A5B6"
                CARD_LABEL = "#526176"
                CARD_VALUE = "#334155"
                CARD_W, CARD_H = 196, 36
                card_font = ("Segoe UI", 9)

                def create_credit_card(host, title, variable, *, padding):
                    if not isinstance(variable, tk.Variable):
                        return None
                    border = tk.Frame(host, bg=CARD_EDGE, padx=1, pady=1)
                    border.pack(side="right", padx=padding, pady=7)
                    content = tk.Frame(border, bg=CARD_BG, width=CARD_W, height=CARD_H)
                    content.pack()
                    content.pack_propagate(False)
                    label = tk.Label(
                        content, text=title, bg=CARD_BG, fg=CARD_LABEL,
                        font=card_font, anchor="w", padx=10,
                    )
                    label.pack(side="left", fill="y")
                    value = tk.Label(
                        content, textvariable=variable, bg=CARD_BG, fg=CARD_VALUE,
                        font=("Segoe UI", 9, "bold"), anchor="e", padx=10,
                    )
                    value.pack(side="right", fill="y")
                    return border, (label, value)

                credit_card = None
                credit_result = (None if g.get("_responsive_equal_credit_cards")
                                 else create_credit_card(
                                     actions, "SnapGen", g.get("credit_status_var"),
                                     padding=(5, 3),
                                 ))
                if credit_result is not None:
                    credit_card, _ = credit_result
                    g["_responsive_snapgen_credit"] = credit_card

                quota_label = g.get("bridge_image_quota_label")
                quota_var = g.get("bridge_image_quota_var")
                if (not g.get("_responsive_equal_credit_cards")
                        and isinstance(quota_label, tk.Label)
                        and isinstance(quota_var, tk.Variable)):
                    # Keep the bottom row exactly where it was. Hide only
                    # the original quota label, preserve its click-to-refresh
                    # callback and render the balance in an equally sized card.
                    quota_host = quota_label.master
                    quota_label.pack_forget()
                    quota_result = create_credit_card(
                        quota_host, "GPT", quota_var, padding=(8, 12),
                    )
                    if quota_result is not None:
                        quota_card, quota_parts = quota_result
                        for widget in (quota_card, quota_card.winfo_children()[0], *quota_parts):
                            widget.configure(cursor="hand2")
                            widget.bind(
                                "<Button-1>",
                                lambda _event, original=quota_label:
                                    original.event_generate("<Button-1>"),
                            )
                        g["_responsive_chatgpt_quota_card"] = quota_card
                # The legacy SnapGen credit control (sometimes rendered as
                # "...") must not remain next to the new credit display.
                # Only suppress controls explicitly registered as credit,
                # never unrelated Settings/overflow actions.
                legacy_credit = tuple(
                    g.get(key) for key in (
                        "credit_button", "credit_label", "credit_status_label",
                        "_image_provider_credit_widget",
                    ) if g.get(key) is not None
                )
                moved = []
                for original in originals:
                    if original in legacy_credit:
                        moved.append(original)
                        continue
                    clone = _clone_action(actions, original, font)
                    if clone is None:
                        continue
                    clone.pack(side="right", padx=3, pady=7)
                    moved.append(original)
                if moved:
                    for original in moved:
                        original.pack_forget()
                    g["_responsive_action_bar"] = actions
                    g["_responsive_moved_toolbar"] = moved
                    # Legacy credit may live in a separate packed toolbar
                    # container, not in the list cloned above.
                    if credit_card is not None:
                        for old in legacy_credit:
                            try:
                                if old.winfo_exists() and old.winfo_manager() == "pack":
                                    old.pack_forget()
                            except tk.TclError:
                                pass
                else:
                    actions.destroy()
            elif attempt < 12:
                root.after(300, lambda: attach_action_bar(attempt + 1))
        except tk.TclError:
            if attempt < 12:
                root.after(300, lambda: attach_action_bar(attempt + 1))

    def ensure_equal_credit_cards(attempt=0):
        """Two true on-screen overlays, independent of toolbar pack order.

        Credit is on the checkbox row; GPT is on the mode-tabs row. Earlier
        packed cards could be placed inside an unmapped or clipped toolbar.
        Mounting directly on the visible root avoids that failure.
        """
        if g.get("_responsive_equal_credit_cards"):
            return

        quota_label = g.get("bridge_image_quota_label")
        quota_var = g.get("bridge_image_quota_var")
        old_credit = next(
            (widget for key in (
                "_image_provider_credit_widget", "credit_button",
                "credit_label", "credit_status_label",
            ) if isinstance((widget := g.get(key)), tk.Widget)
             and widget.winfo_exists()), None,
        )
        if old_credit is None:
            old_credit = _find_snapgen_credit_widget(root)
        credit_var = g.get("credit_status_var")
        if not isinstance(quota_label, tk.Label) or not isinstance(quota_var, tk.Variable):
            if attempt < 50:
                root.after(400, lambda: ensure_equal_credit_cards(attempt + 1))
            return
        if not isinstance(credit_var, tk.Variable):
            if old_credit is None:
                if attempt < 50:
                    root.after(400, lambda: ensure_equal_credit_cards(attempt + 1))
                return
            try:
                name = str(old_credit.cget("textvariable") or "")
            except tk.TclError:
                name = ""
            credit_var = (tk.StringVar(master=root, name=name) if name
                          else tk.StringVar(master=root, value=_displayed_label_text(root, old_credit)))
            g["credit_status_var"] = credit_var

        size = 38                 # 36px interior plus 1px border on both sides
        pad_right = 18
        def vertical_center(widget, fallback):
            try:
                if widget is not None and widget.winfo_manager():
                    return round(widget.winfo_rooty() - root.winfo_rooty()
                                 + (widget.winfo_height() - size) / 2)
            except tk.TclError:
                pass
            return fallback

        quota_host = quota_label.master
        try:
            if quota_label.winfo_manager():
                quota_offset = round(
                    quota_label.winfo_rooty() - quota_host.winfo_rooty()
                    + (quota_label.winfo_height() - size) / 2)
            else:
                quota_offset = max(0, round((quota_host.winfo_height() - size) / 2))
        except tk.TclError:
            quota_offset = 0
        gpt_y = round(quota_host.winfo_rooty() - root.winfo_rooty() + quota_offset)
        snap_y = vertical_center(old_credit, max(4, gpt_y - 110))
        if snap_y >= gpt_y - 28:
            snap_y = max(4, gpt_y - 110)

        for key in ("_responsive_snapgen_credit", "_responsive_chatgpt_quota_card"):
            old = g.get(key)
            if isinstance(old, tk.Widget) and old.winfo_exists():
                old.destroy()

        bg, edge, label_fg, value_fg = "#EDF1F5", "#98A5B6", "#526176", "#334155"

        def create_card(title_var, number_var, top):
            edge_frame = tk.Frame(root, bg=edge, padx=2, pady=2)
            edge_frame.place(relx=1.0, x=-pad_right, y=top, anchor="ne")
            surface = tk.Frame(edge_frame, bg=bg, width=194, height=34)
            surface.pack()
            surface.pack_propagate(False)
            left = tk.Label(surface, bg=bg, fg=label_fg, font=("Segoe UI", 9),
                            anchor="w", padx=10, textvariable=title_var)
            left.pack(side="left", fill="y")
            right = tk.Label(surface, bg=bg, fg=value_fg, font=("Segoe UI", 9, "bold"),
                             anchor="e", padx=10, textvariable=number_var)
            right.pack(side="right", fill="y")
            return edge_frame, (surface, left, right)

        snap_title = tk.StringVar(master=root, value="SnapGen")
        snap_card, snap_widgets = create_card(snap_title, credit_var, snap_y)
        gpt_title, gpt_number = tk.StringVar(master=root), tk.StringVar(master=root)
        def update_gpt(*_):
            title, number = split_gpt_quota(quota_var.get())
            gpt_title.set(title)
            gpt_number.set(number)
        quota_var.trace_add("write", update_gpt)
        update_gpt()
        gpt_card, gpt_widgets = create_card(gpt_title, gpt_number, gpt_y)

        def hide_source(widget):
            try:
                if widget is None or not widget.winfo_exists():
                    return
                manager = widget.winfo_manager()
                if manager == "pack":
                    widget.pack_forget()
                elif manager == "grid":
                    widget.grid_remove()
                elif manager == "place":
                    widget.place_forget()
            except tk.TclError:
                pass

        sources = [quota_label, old_credit]
        sources.extend(g.get(k) for k in (
            "_image_provider_credit_widget", "credit_button",
            "credit_label", "credit_status_label",
        ))
        # Hide the old SnapGen title, but never any arbitrary toolbar button.
        if old_credit is not None:
            try:
                cx = old_credit.winfo_rootx()
                cy = old_credit.winfo_rooty()
                queue = [root]
                while queue:
                    widget = queue.pop()
                    queue.extend(widget.winfo_children())
                    if not isinstance(widget, tk.Label) or widget is old_credit:
                        continue
                    if (str(widget).startswith(str(snap_card) + ".") or str(widget).startswith(str(gpt_card) + ".")):
                        continue
                    if _displayed_label_text(root, widget) != "SnapGen":
                        continue
                    delta_x = cx - widget.winfo_rootx() - widget.winfo_width()
                    if -30 <= delta_x <= 330 and abs(cy-widget.winfo_rooty()) <= 30:
                        sources.append(widget)
            except tk.TclError:
                pass
        for widget in sources:
            hide_source(widget)

        def refresh_source(_event=None):
            if not isinstance(old_credit, tk.Widget):
                return
            try:
                if isinstance(old_credit, tk.Button):
                    old_credit.invoke()
                else:
                    old_credit.event_generate("<Button-1>")
            except tk.TclError:
                pass
        for widget in (snap_card, *snap_widgets):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", refresh_source)
        for widget in (gpt_card, *gpt_widgets):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda _event: quota_label.event_generate("<Button-1>"))

        g["_responsive_snapgen_credit"] = snap_card
        g["_responsive_chatgpt_quota_card"] = gpt_card
        g["_responsive_equal_credit_cards"] = True

        def sync_layout():
            try:
                if not snap_card.winfo_exists() or not gpt_card.winfo_exists():
                    return
                right_edge = max(400, int(root.winfo_width())) - 18
                action_bar = g.get("_responsive_action_bar")
                mode_row = g.get("mode_frame")
                if isinstance(action_bar, tk.Widget) and action_bar.winfo_ismapped():
                    snap_top = (action_bar.winfo_rooty() - root.winfo_rooty()
                                + max(0, (action_bar.winfo_height() - 38) // 2))
                else:
                    snap_top = 48
                if isinstance(mode_row, tk.Widget) and mode_row.winfo_ismapped():
                    mode_top = (mode_row.winfo_rooty() - root.winfo_rooty()
                                + max(0, (mode_row.winfo_height() - 38) // 2))
                    gpt_top = max(snap_top + 44, mode_top)
                else:
                    gpt_top = snap_top + 52
                snap_card.place_configure(relx=0.0, x=right_edge,
                                          y=snap_top, anchor="ne")
                gpt_card.place_configure(relx=0.0, x=right_edge,
                                         y=gpt_top, anchor="ne")
                # App-wide theme refreshes must not wash out the pale-grey
                # cards or their stronger, equal-width outlines.
                for card, parts in ((snap_card, snap_widgets), (gpt_card, gpt_widgets)):
                    card.configure(bg=edge)
                    parts[0].configure(bg=bg)
                    parts[1].configure(bg=bg, fg=label_fg)
                    parts[2].configure(bg=bg, fg=value_fg)
                snap_card.lift()
                gpt_card.lift()
            except tk.TclError:
                pass

        def on_root_configure(event):
            if event.widget is root:
                root.after_idle(sync_layout)
        root.bind("<Configure>", on_root_configure, add="+")

        def maintain_cards():
            try:
                if not snap_card.winfo_exists() or not gpt_card.winfo_exists():
                    return
                for widget in sources:
                    hide_source(widget)
                sync_layout()
                root.after(1800, maintain_cards)
            except tk.TclError:
                return
        root.after(500, maintain_cards)
        root.after_idle(sync_layout)
        root.after(1500, sync_layout)
        root.after(3500, sync_layout)

    # Run independently of Prompt-Ref. Previously if the toolbar button was
    # unavailable, both cards disappeared despite v2.0.30 being installed.
    root.after_idle(ensure_equal_credit_cards)
    # Install cards BEFORE cloning/moving toolbar widgets. Previously cloning
    # hid the original numeric credit Label first, so the live 26 could no
    # longer be found from the SnapGen caption.
    root.after_idle(attach_action_bar)
    root.after(900, ensure_equal_credit_cards)

    # The original mode tabs have width=13 characters, consuming more than
    # 1536 physical pixels at 125% DPI. Set widths only when the breakpoint
    # changes and after the existing active-style code has finished.
    state = {"after": None, "layout": None}
    def relayout():
        state["after"] = None
        try:
            # Use the SAME geometry chosen by style_mode_button() on every
            # active-mode change. No intermediate width=13 and no flash when
            # clicking tabs or resizing on a 125%-DPI monitor.
            from snapgen_button_styles import mode_tab_geometry
            btns = (g.get("mode_buttons") or modes)
            if not isinstance(btns, dict) or not btns:
                btns = {}
                for child in mode_frame.winfo_children() if mode_frame else ():
                    if isinstance(child, tk.Button):
                        btns[str(child)] = child
            for button in btns.values():
                if not isinstance(button, tk.Button) or not button.winfo_exists():
                    continue
                width_chars, inner_pad, outer_pad, font_size = mode_tab_geometry(button)
                desired_font = (font[0], font_size, "bold")
                if (int(button.cget("width")) != width_chars
                        or int(button.cget("padx")) != inner_pad):
                    button.configure(width=width_chars, padx=inner_pad, font=desired_font)
                if (button.winfo_manager() == "pack"
                        and int(button.pack_info().get("padx", 0)) != outer_pad):
                    button.pack_configure(padx=outer_pad)
        except (tk.TclError, TypeError, ValueError):
            pass

    def request_layout(event=None):
        if event is not None and event.widget is not root:
            return
        if state["after"] is not None:
            try:
                root.after_cancel(state["after"])
            except tk.TclError:
                pass
        state["after"] = root.after(180, relayout)

    root.bind("<Configure>", request_layout, add="+")
    # Do not schedule a second resize after clicks. style_mode_button now
    # applies the final size in the SAME call that updates active colors.
    root.after_idle(relayout)
    g["_responsive_relayout"] = request_layout
