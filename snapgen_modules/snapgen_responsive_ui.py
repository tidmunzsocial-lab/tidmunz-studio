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
                # Reuse original live balances, retain each original toolbar
                # row and apply the same soft-grey card treatment to both.
                CARD_BG = "#F3F5F8"
                CARD_EDGE = "#DCE2EA"
                CARD_LABEL = "#66758A"
                CARD_VALUE = "#475569"
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
        """Restore both credit cards even when toolbar discovery happened late.

        Credit status is provided by the recovered app, whose StringVar can be
        registered after Prompt-Ref is made. Never require its presence to
        create a visible card; use the original button as a live fallback.
        """
        if g.get("_responsive_equal_credit_cards"):
            cards = (g.get("_responsive_snapgen_credit"),
                     g.get("_responsive_chatgpt_quota_card"))
            if all(isinstance(card, tk.Widget) and card.winfo_exists()
                   and card.winfo_manager() == "pack" for card in cards):
                return
            g["_responsive_equal_credit_cards"] = False
        quota_label = g.get("bridge_image_quota_label")
        quota_var = g.get("bridge_image_quota_var")
        # The real toolbar registers its numeric credit display under this
        # key. Older code looked ONLY for credit_button, skipped the cards,
        # and left the plain SnapGen 26 and GPT Plus 62 from the screenshot.
        old_credit = next(
            (g.get(k) for k in (
                "_image_provider_credit_widget",
                "credit_button", "credit_label", "credit_status_label",
            ) if isinstance(g.get(k), tk.Widget)
             and g.get(k).winfo_exists()), None
        )
        if old_credit is None:
            old_credit = _find_snapgen_credit_widget(root)
        credit_var = g.get("credit_status_var")
        action_bar = g.get("_responsive_action_bar")
        if isinstance(action_bar, tk.Frame) and not action_bar.winfo_exists():
            action_bar = None

        if not isinstance(quota_label, tk.Label) or not isinstance(quota_var, tk.Variable):
            if attempt < 50:
                root.after(400, lambda: ensure_equal_credit_cards(attempt + 1))
            return
        if not isinstance(credit_var, tk.Variable):
            if old_credit is None:
                if attempt < 50:
                    root.after(400, lambda: ensure_equal_credit_cards(attempt + 1))
                return
            # Share the legacy Tcl StringVar when one exists so that future
            # balance updates are immediately reflected in the new card.
            try:
                variable_name = str(old_credit.cget("textvariable") or "")
            except tk.TclError:
                variable_name = ""
            if variable_name:
                credit_var = tk.StringVar(master=root, name=variable_name)
            else:
                credit_var = tk.StringVar(
                    master=root, value=str(old_credit.cget("text") or "—"))
            g["credit_status_var"] = credit_var

        if action_bar is not None:
            credit_host = action_bar
            credit_right_pad = 5  # action bar already has 7 px outer padding
        elif old_credit is not None:
            credit_host = old_credit.master
            credit_right_pad = 12
        else:
            if attempt < 50:
                root.after(400, lambda: ensure_equal_credit_cards(attempt + 1))
            return
        quota_host = quota_label.master

        # Supersede legacy partial cards; no dark tk relief borders.
        for key in ("_responsive_snapgen_credit", "_responsive_chatgpt_quota_card"):
            old = g.get(key)
            if isinstance(old, tk.Widget):
                try:
                    if old.winfo_exists():
                        old.destroy()
                except tk.TclError:
                    pass
        bg, edge = "#F3F5F8", "#DCE2EA"
        label_fg, number_fg = "#66758A", "#475569"
        def new_card(host, title_var, amount_var, right_pad):
            frame = tk.Frame(host, bg=edge, padx=1, pady=1)
            frame.pack(side="right", padx=(5, right_pad), pady=7)
            inner = tk.Frame(frame, bg=bg, width=196, height=36)
            inner.pack()
            inner.pack_propagate(False)
            title_label = tk.Label(inner, textvariable=title_var, bg=bg,
                                   fg=label_fg, font=("Segoe UI", 9),
                                   padx=10, anchor="w")
            title_label.pack(side="left", fill="y")
            amount_label = tk.Label(inner, textvariable=amount_var, bg=bg,
                                    fg=number_fg, font=("Segoe UI", 9, "bold"),
                                    padx=10, anchor="e")
            amount_label.pack(side="right", fill="y")
            return frame, (inner, title_label, amount_label)

        snap_title = tk.StringVar(master=root, value="SnapGen")
        snap_card, snap_widgets = new_card(
            credit_host, snap_title, credit_var, credit_right_pad,
        )
        quota_title = tk.StringVar(master=root)
        quota_amount = tk.StringVar(master=root)
        def refresh_quota(*_args):
            title, amount = split_gpt_quota(quota_var.get())
            quota_title.set(title)
            quota_amount.set(amount)
        quota_var.trace_add("write", refresh_quota)
        refresh_quota()
        quota_card, quota_widgets = new_card(
            quota_host, quota_title, quota_amount, 12,
        )

        for widget in (quota_card, *quota_widgets):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda _event, original=quota_label:
                        original.event_generate("<Button-1>"))
        quota_label.pack_forget()
        # Hide both old SnapGen pieces (the numeric widget and the caption).
        # The original numeric credit is still retained for provider callbacks.
        legacy_widgets = [
            g.get(k) for k in (
                "_image_provider_credit_widget",
                "credit_button", "credit_label", "credit_status_label",
            )
        ]
        if old_credit is not None:
            try:
                credit_x = old_credit.winfo_rootx()
                credit_y = old_credit.winfo_rooty()
                stack = [root]
                while stack:
                    node = stack.pop()
                    stack.extend(node.winfo_children())
                    if not isinstance(node, tk.Label) or node is old_credit:
                        continue
                    if _displayed_label_text(root, node) != "SnapGen":
                        continue
                    dx = credit_x - (node.winfo_rootx() + node.winfo_width())
                    dy = abs(credit_y - node.winfo_rooty())
                    if -30 <= dx <= 280 and dy <= 24:
                        legacy_widgets.append(node)
            except tk.TclError:
                pass
        for widget in legacy_widgets:
            if isinstance(widget, tk.Widget) and widget.winfo_exists():
                manager = widget.winfo_manager()
                if manager == "pack":
                    widget.pack_forget()
                elif manager == "grid":
                    widget.grid_remove()
                elif manager == "place":
                    widget.place_forget()
        # Preserve clicking the original credit control to refresh account.
        if isinstance(old_credit, tk.Widget):
            def refresh_snapgen(_event):
                try:
                    if isinstance(old_credit, tk.Button):
                        old_credit.invoke()
                    else:
                        old_credit.event_generate("<Button-1>")
                except tk.TclError:
                    pass
            for widget in (snap_card, *snap_widgets):
                widget.configure(cursor="hand2")
                widget.bind("<Button-1>", refresh_snapgen)
        g["_responsive_snapgen_credit"] = snap_card
        g["_responsive_chatgpt_quota_card"] = quota_card
        g["_responsive_equal_credit_cards"] = True

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
