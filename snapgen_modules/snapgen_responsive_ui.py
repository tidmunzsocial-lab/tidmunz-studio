"""Keep every Tidmunz toolbar action reachable at 125%+ Windows DPI.

The recovered Tk app supplies a single packed header that was designed for
96 DPI. Extra Chrome/Prompt-Ref/microphone controls grew that one row past the
window edge. This adapter creates a second action row, leaving checkboxes in
the first. Existing callback-owning widgets stay alive but hidden: clones
invoke them, so no workflow, credit balance or settings state is rewritten.
"""
from __future__ import annotations

import tkinter as tk


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
                actions = tk.Frame(parent, bg="#FFFFFF", height=38)
                actions.pack(side="top", fill="x", after=toolbar, padx=7, pady=(0, 2))
                actions.pack_propagate(False)
                moved = []
                for original in originals:
                    clone = _clone_action(actions, original, font)
                    if clone is None:
                        continue
                    clone.pack(side="right", padx=3, pady=1)
                    moved.append(original)
                if moved:
                    for original in moved:
                        original.pack_forget()
                    g["_responsive_action_bar"] = actions
                    g["_responsive_moved_toolbar"] = moved
                else:
                    actions.destroy()
            elif attempt < 12:
                root.after(300, lambda: attach_action_bar(attempt + 1))
        except tk.TclError:
            if attempt < 12:
                root.after(300, lambda: attach_action_bar(attempt + 1))

    attach_action_bar()

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
