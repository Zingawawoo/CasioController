"""Casio Universal Controller — mapping GUI.

A modern, dark-themed tkinter app for editing mappings.json. Pick a key
from the list, choose a mode + action, optionally tweak color/brightness,
and hit Save. The Launch button spawns main.py as a subprocess so you can
test your mappings without leaving the editor.
"""

import json
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox


ROOT = os.path.dirname(os.path.abspath(__file__))
MAPPINGS_PATH = os.path.join(ROOT, "mappings.json")


# ---- Keyboard range --------------------------------------------------------
# The Casio CT-S100 has 61 keys, C2 (MIDI 36) to C7 (MIDI 96).
FIRST_NOTE = 36
LAST_NOTE = 96
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(midi_note: int) -> str:
    """Convert a MIDI note number to its pitch name (e.g. 60 -> 'C4')."""
    return f"{NOTE_NAMES[midi_note % 12]}{(midi_note // 12) - 1}"


def is_black_key(midi_note: int) -> bool:
    return NOTE_NAMES[midi_note % 12].endswith("#")


# ---- Theme -----------------------------------------------------------------
# Catppuccin Mocha-inspired palette.
BG        = "#1e1e2e"
SURFACE   = "#282838"
SURFACE_2 = "#313244"
BORDER    = "#45475a"
TEXT      = "#cdd6f4"
SUBTEXT   = "#a6adc8"
MUTED     = "#6c7086"
ACCENT    = "#89b4fa"
ACCENT_2  = "#74a6f0"
SUCCESS   = "#a6e3a1"
DANGER    = "#f38ba8"

FONT_FAMILY = "Segoe UI"  # falls back to system default if unavailable
FONT_BODY   = (FONT_FAMILY, 10)
FONT_SMALL  = (FONT_FAMILY, 9)
FONT_TITLE  = (FONT_FAMILY, 16, "bold")
FONT_SUB    = (FONT_FAMILY, 10)
FONT_MONO   = ("Consolas", 10)


# ---- Action catalogs -------------------------------------------------------
# The dropdowns in the right panel are driven by this table.
ACTIONS_BY_MODE = {
    "NONE":   [],
    "LIGHTS": ["turn_on", "turn_off", "color",
               "movie_mode", "party_mode", "sleep_mode"],
    "TV":     ["power_on", "netflix", "youtube", "disney", "prime", "key"],
    "GAME":   ["KEY_SPACE", "KEY_ENTER", "KEY_ESC", "KEY_TAB",
               "KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT",
               "KEY_SHIFT", "KEY_CTRL", "KEY_ALT",
               "KEY_W", "KEY_A", "KEY_S", "KEY_D",
               "KEY_Z", "KEY_X", "KEY_Q", "KEY_E"],
    "AUDIO":  ["play_pause", "next_track", "prev_track", "set_volume"],
}

TV_KEYS = ["KEY_VOLUP", "KEY_VOLDOWN", "KEY_MUTE",
           "KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT",
           "KEY_ENTER", "KEY_RETURN", "KEY_HOME", "KEY_MENU",
           "KEY_CHUP", "KEY_CHDOWN"]


# ============================================================================


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Casio Universal Controller")
        self.geometry("960x620")
        self.minsize(860, 540)
        self.configure(bg=BG)

        self.mappings: dict = self._load_mappings()
        self.selected_note: int | None = None
        self._row_widgets: dict[int, dict] = {}  # note -> {frame, label_*}

        self._apply_theme()
        self._build_layout()
        self._select_note(60)  # start on middle C

    # ---- Data ------------------------------------------------------------

    def _load_mappings(self) -> dict:
        if not os.path.exists(MAPPINGS_PATH):
            return {}
        try:
            with open(MAPPINGS_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            messagebox.showerror("Load error", f"Couldn't read mappings.json:\n{e}")
            return {}

    def _save_mappings(self) -> None:
        try:
            with open(MAPPINGS_PATH, "w") as f:
                json.dump(self.mappings, f, indent=2, sort_keys=True)
            self._set_status("Saved ✓", SUCCESS)
        except Exception as e:
            messagebox.showerror("Save error", str(e))

    # ---- Theme -----------------------------------------------------------

    def _apply_theme(self):
        style = ttk.Style(self)
        # 'clam' lets us override colours that 'default' and 'vista' lock down.
        style.theme_use("clam")

        style.configure(".", background=BG, foreground=TEXT,
                        font=FONT_BODY, borderwidth=0)

        style.configure("TFrame", background=BG)
        style.configure("Surface.TFrame", background=SURFACE)

        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Title.TLabel", background=BG, foreground=TEXT,
                        font=FONT_TITLE)
        style.configure("Sub.TLabel", background=BG, foreground=SUBTEXT,
                        font=FONT_SUB)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED,
                        font=FONT_SMALL)
        style.configure("SurfaceSub.TLabel", background=SURFACE,
                        foreground=SUBTEXT, font=FONT_SMALL)

        # Buttons — flat, minimal, no border, subtle hover.
        style.configure("TButton",
                        background=SURFACE_2, foreground=TEXT,
                        padding=(14, 8), borderwidth=0, focuscolor=SURFACE_2)
        style.map("TButton",
                  background=[("active", BORDER), ("pressed", BORDER)])

        style.configure("Accent.TButton",
                        background=ACCENT, foreground=BG,
                        padding=(16, 9), borderwidth=0,
                        font=(FONT_FAMILY, 10, "bold"))
        style.map("Accent.TButton",
                  background=[("active", ACCENT_2), ("pressed", ACCENT_2)])

        style.configure("Ghost.TButton",
                        background=BG, foreground=SUBTEXT,
                        padding=(10, 6), borderwidth=0)
        style.map("Ghost.TButton",
                  background=[("active", SURFACE)],
                  foreground=[("active", TEXT)])

        # Combobox: dark dropdown.
        style.configure("TCombobox",
                        fieldbackground=SURFACE_2, background=SURFACE_2,
                        foreground=TEXT, arrowcolor=SUBTEXT,
                        borderwidth=0, padding=6)
        style.map("TCombobox",
                  fieldbackground=[("readonly", SURFACE_2)],
                  foreground=[("readonly", TEXT)])
        # The dropdown popup is a Tk listbox, styled via option_add.
        self.option_add("*TCombobox*Listbox.background", SURFACE_2)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", BG)
        self.option_add("*TCombobox*Listbox.borderWidth", 0)
        self.option_add("*TCombobox*Listbox.font", FONT_BODY)

        style.configure("TEntry",
                        fieldbackground=SURFACE_2, foreground=TEXT,
                        insertcolor=TEXT, borderwidth=0, padding=6)

        style.configure("Horizontal.TScale",
                        background=BG, troughcolor=SURFACE_2,
                        borderwidth=0)

        style.configure("Vertical.TScrollbar",
                        background=SURFACE, troughcolor=BG,
                        arrowcolor=SUBTEXT, borderwidth=0)
        style.map("Vertical.TScrollbar",
                  background=[("active", SURFACE_2)])

    # ---- Layout ----------------------------------------------------------

    def _build_layout(self):
        # Header
        header = ttk.Frame(self, padding=(24, 20, 24, 16))
        header.pack(side="top", fill="x")

        ttk.Label(header, text="Casio Universal Controller",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(header,
                  text="Map each key to lights, TV, games, or audio.",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 0))

        # Separator hairline
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Body (two columns)
        body = ttk.Frame(self, padding=(0, 0, 0, 0))
        body.pack(side="top", fill="both", expand=True)
        body.columnconfigure(0, weight=1, minsize=380)
        body.columnconfigure(1, weight=1, minsize=380)
        body.rowconfigure(0, weight=1)

        self._build_key_list(body)
        self._build_detail_panel(body)

        # Footer
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        footer = ttk.Frame(self, padding=(24, 14, 24, 18))
        footer.pack(side="bottom", fill="x")

        ttk.Button(footer, text="Save Mappings",
                   style="Accent.TButton",
                   command=self._save_mappings).pack(side="left")
        ttk.Button(footer, text="Launch Controller",
                   command=self._launch_controller).pack(side="left", padx=(10, 0))

        self.status_var = tk.StringVar(value="Ready")
        self.status_lbl = ttk.Label(footer, textvariable=self.status_var,
                                    style="Muted.TLabel")
        self.status_lbl.pack(side="right")

    # ---- Left panel: scrollable key list ---------------------------------

    def _build_key_list(self, parent):
        container = ttk.Frame(parent, padding=(24, 18, 12, 18))
        container.grid(row=0, column=0, sticky="nsew")
        container.rowconfigure(1, weight=1)
        container.columnconfigure(0, weight=1)

        ttk.Label(container, text="KEYS",
                  style="Muted.TLabel").grid(row=0, column=0, sticky="w",
                                              pady=(0, 8))

        # Canvas + inner frame = a scrollable list.
        canvas = tk.Canvas(container, bg=BG, highlightthickness=0,
                           borderwidth=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical",
                                   command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")

        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_configure(_e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(inner_id, width=canvas.winfo_width())

        inner.bind("<Configure>", _on_configure)
        canvas.bind("<Configure>", _on_configure)

        # Mouse wheel: cross-platform-ish.
        def _on_wheel(e):
            delta = -1 * (e.delta // 120) if e.delta else (1 if e.num == 5 else -1)
            canvas.yview_scroll(delta, "units")
        canvas.bind_all("<MouseWheel>", _on_wheel)
        canvas.bind_all("<Button-4>", _on_wheel)
        canvas.bind_all("<Button-5>", _on_wheel)

        for note in range(FIRST_NOTE, LAST_NOTE + 1):
            self._build_key_row(inner, note)

    def _build_key_row(self, parent, note: int):
        """One row in the scrollable key list."""
        row = tk.Frame(parent, bg=SURFACE, height=40)
        row.pack(fill="x", pady=2, padx=(0, 4))
        row.pack_propagate(False)

        # Small accent stripe for black keys so the keyboard layout reads fast.
        stripe = tk.Frame(row, bg=(ACCENT if is_black_key(note) else SURFACE_2),
                          width=3)
        stripe.pack(side="left", fill="y")

        # Note label (pitch name + midi number)
        name_lbl = tk.Label(row, text=f"  {note_name(note):<4} · {note}",
                            bg=SURFACE, fg=TEXT, font=FONT_MONO, anchor="w")
        name_lbl.pack(side="left", padx=(8, 0))

        # Current mapping summary on the right.
        summary_lbl = tk.Label(row, text="", bg=SURFACE, fg=SUBTEXT,
                               font=FONT_SMALL, anchor="e")
        summary_lbl.pack(side="right", padx=(0, 12))

        # Click anywhere on the row to select.
        for w in (row, stripe, name_lbl, summary_lbl):
            w.bind("<Button-1>", lambda _e, n=note: self._select_note(n))
            w.bind("<Enter>", lambda _e, r=row: self._hover_row(r, True))
            w.bind("<Leave>", lambda _e, r=row: self._hover_row(r, False))

        self._row_widgets[note] = {
            "row": row, "name": name_lbl, "summary": summary_lbl,
            "stripe": stripe,
        }
        self._refresh_row(note)

    def _hover_row(self, row, entering: bool):
        if getattr(row, "_selected", False):
            return
        row.configure(bg=SURFACE_2 if entering else SURFACE)
        for child in row.winfo_children():
            if isinstance(child, tk.Label):
                child.configure(bg=SURFACE_2 if entering else SURFACE)

    def _refresh_row(self, note: int):
        """Update the summary text and selection highlight for a row."""
        w = self._row_widgets[note]
        m = self.mappings.get(str(note))
        if m:
            mode = m.get("mode", "")
            action = m.get("action", "")
            summary = f"{mode.lower()} · {action}"
        else:
            summary = "—"
        w["summary"].configure(text=summary, fg=(TEXT if m else MUTED))

        selected = (note == self.selected_note)
        bg = SURFACE_2 if selected else SURFACE
        w["row"].configure(bg=bg)
        w["row"]._selected = selected
        w["name"].configure(bg=bg)
        w["summary"].configure(bg=bg)
        if selected:
            w["stripe"].configure(bg=ACCENT)
        else:
            w["stripe"].configure(bg=(ACCENT if is_black_key(note) else SURFACE_2))

    # ---- Right panel: detail / editor ------------------------------------

    def _build_detail_panel(self, parent):
        wrap = ttk.Frame(parent, padding=(12, 18, 24, 18))
        wrap.grid(row=0, column=1, sticky="nsew")

        self.detail_title = ttk.Label(wrap, text="—", style="Title.TLabel")
        self.detail_title.pack(anchor="w")
        self.detail_sub = ttk.Label(wrap, text="Select a key to edit its mapping.",
                                     style="Sub.TLabel")
        self.detail_sub.pack(anchor="w", pady=(2, 16))

        # Mode row
        self._row_label(wrap, "Mode")
        self.mode_var = tk.StringVar(value="NONE")
        self.mode_combo = ttk.Combobox(wrap, textvariable=self.mode_var,
                                        state="readonly", width=22,
                                        values=list(ACTIONS_BY_MODE.keys()))
        self.mode_combo.pack(anchor="w", pady=(2, 12))
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_change)

        # Action row
        self._row_label(wrap, "Action")
        self.action_var = tk.StringVar(value="")
        self.action_combo = ttk.Combobox(wrap, textvariable=self.action_var,
                                          state="readonly", width=22)
        self.action_combo.pack(anchor="w", pady=(2, 12))
        self.action_combo.bind("<<ComboboxSelected>>", self._on_action_change)

        # Conditional fields (shown/hidden based on mode + action)
        self.color_frame = ttk.Frame(wrap)
        self._row_label(self.color_frame, "Color")
        color_row = ttk.Frame(self.color_frame)
        color_row.pack(anchor="w", pady=(2, 0))
        self.color_var = tk.StringVar(value="#ff0000")
        self.color_swatch = tk.Label(color_row, text="    ", bg="#ff0000",
                                      width=3, relief="flat", borderwidth=0)
        self.color_swatch.pack(side="left", padx=(0, 8))
        self.color_entry = ttk.Entry(color_row, textvariable=self.color_var,
                                      width=12)
        self.color_entry.pack(side="left")
        self.color_var.trace_add("write", lambda *_: self._on_color_entry())
        ttk.Button(color_row, text="Pick…", style="Ghost.TButton",
                   command=self._pick_color).pack(side="left", padx=(8, 0))

        self.brightness_frame = ttk.Frame(wrap)
        self._row_label(self.brightness_frame, "Brightness")
        bright_row = ttk.Frame(self.brightness_frame)
        bright_row.pack(anchor="w", fill="x", pady=(2, 0))
        self.brightness_var = tk.IntVar(value=80)
        self.brightness_scale = ttk.Scale(bright_row, from_=1, to=100,
                                           orient="horizontal",
                                           variable=self.brightness_var,
                                           length=220,
                                           command=lambda _v: self._update_brightness_label())
        self.brightness_scale.pack(side="left")
        self.brightness_label = ttk.Label(bright_row, text="80",
                                           style="Sub.TLabel", width=4)
        self.brightness_label.pack(side="left", padx=(10, 0))

        self.tvkey_frame = ttk.Frame(wrap)
        self._row_label(self.tvkey_frame, "TV key")
        self.tvkey_var = tk.StringVar(value="KEY_VOLUP")
        self.tvkey_combo = ttk.Combobox(self.tvkey_frame,
                                         textvariable=self.tvkey_var,
                                         state="readonly", width=22,
                                         values=TV_KEYS)
        self.tvkey_combo.pack(anchor="w", pady=(2, 0))

        # Spacer + clear button at the bottom of the detail panel
        ttk.Frame(wrap).pack(fill="both", expand=True)
        ttk.Button(wrap, text="Clear mapping",
                   style="Ghost.TButton",
                   command=self._clear_mapping).pack(anchor="w", pady=(16, 0))

    def _row_label(self, parent, text):
        ttk.Label(parent, text=text.upper(),
                  style="Muted.TLabel").pack(anchor="w", pady=(8, 0))

    # ---- Selection + state syncing ---------------------------------------

    def _select_note(self, note: int):
        previous = self.selected_note
        self.selected_note = note
        if previous is not None and previous in self._row_widgets:
            self._refresh_row(previous)
        self._refresh_row(note)

        # Populate detail panel from the current mapping.
        self.detail_title.configure(text=f"{note_name(note)}  ·  MIDI {note}")
        mapping = self.mappings.get(str(note))

        if mapping is None:
            self.detail_sub.configure(text="Unassigned. Pick a mode to map it.")
            self.mode_var.set("NONE")
        else:
            self.detail_sub.configure(text="Editing this key's mapping.")
            self.mode_var.set(mapping.get("mode", "NONE"))

        self._refresh_actions_for_mode()

        if mapping:
            action = mapping.get("action", "")
            if action in self.action_combo["values"]:
                self.action_var.set(action)
            if "color" in mapping:
                self.color_var.set(mapping["color"])
            if "brightness" in mapping:
                self.brightness_var.set(int(mapping["brightness"]))
                self._update_brightness_label()
            if "key" in mapping:
                self.tvkey_var.set(mapping["key"])

        self._refresh_conditional_fields()
        self._set_status(f"Selected {note_name(note)}", SUBTEXT)

    # ---- Detail-panel event handlers -------------------------------------

    def _on_mode_change(self, _evt=None):
        self._refresh_actions_for_mode()
        self._commit_from_form()

    def _on_action_change(self, _evt=None):
        self._refresh_conditional_fields()
        self._commit_from_form()

    def _refresh_actions_for_mode(self):
        mode = self.mode_var.get()
        actions = ACTIONS_BY_MODE.get(mode, [])
        self.action_combo["values"] = actions
        if actions and self.action_var.get() not in actions:
            self.action_var.set(actions[0])
        if not actions:
            self.action_var.set("")
        self._refresh_conditional_fields()

    def _refresh_conditional_fields(self):
        """Show/hide color, brightness, TV-key widgets based on selection."""
        mode = self.mode_var.get()
        action = self.action_var.get()

        for f in (self.color_frame, self.brightness_frame, self.tvkey_frame):
            f.pack_forget()

        if mode == "LIGHTS":
            if action == "color":
                self.color_frame.pack(anchor="w", fill="x")
            if action in ("color", "turn_on"):
                self.brightness_frame.pack(anchor="w", fill="x")
        elif mode == "TV" and action == "key":
            self.tvkey_frame.pack(anchor="w", fill="x")

    def _on_color_entry(self):
        c = self.color_var.get().strip()
        if len(c) == 7 and c.startswith("#"):
            try:
                int(c[1:], 16)
                self.color_swatch.configure(bg=c)
                self._commit_from_form()
            except ValueError:
                pass

    def _pick_color(self):
        initial = self.color_var.get() or "#ffffff"
        rgb, hex_val = colorchooser.askcolor(color=initial, title="Pick a color")
        if hex_val:
            self.color_var.set(hex_val)
            self.color_swatch.configure(bg=hex_val)
            self._commit_from_form()

    def _update_brightness_label(self):
        v = int(self.brightness_var.get())
        self.brightness_label.configure(text=str(v))
        # Commit brightness on release only would be nicer, but this is fine.
        self._commit_from_form()

    # ---- Writing back into self.mappings ---------------------------------

    def _commit_from_form(self):
        """Build a mapping dict from the current form state and store it."""
        if self.selected_note is None:
            return

        mode = self.mode_var.get()
        if mode == "NONE":
            self.mappings.pop(str(self.selected_note), None)
            self._refresh_row(self.selected_note)
            return

        action = self.action_var.get()
        if not action:
            return

        entry: dict = {"mode": mode, "action": action}

        if mode == "LIGHTS":
            if action == "color":
                entry["color"] = self.color_var.get()
                entry["brightness"] = int(self.brightness_var.get())
            elif action == "turn_on":
                entry["brightness"] = int(self.brightness_var.get())
        elif mode == "TV" and action == "key":
            entry["key"] = self.tvkey_var.get()

        self.mappings[str(self.selected_note)] = entry
        self._refresh_row(self.selected_note)

    def _clear_mapping(self):
        if self.selected_note is None:
            return
        self.mappings.pop(str(self.selected_note), None)
        self.mode_var.set("NONE")
        self._refresh_actions_for_mode()
        self._refresh_row(self.selected_note)
        self._set_status(f"Cleared {note_name(self.selected_note)}", SUBTEXT)

    # ---- Subprocess + status ---------------------------------------------

    def _launch_controller(self):
        script = os.path.join(ROOT, "main.py")
        try:
            subprocess.Popen([sys.executable, script], cwd=ROOT)
            self._set_status("Controller launched", SUCCESS)
        except Exception as e:
            self._set_status(f"Launch failed: {e}", DANGER)

    def _set_status(self, text: str, color: str = SUBTEXT):
        self.status_var.set(text)
        self.status_lbl.configure(foreground=color)


if __name__ == "__main__":
    App().mainloop()
