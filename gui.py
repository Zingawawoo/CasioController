"""Casio Universal Controller — mapping GUI.

A modern, dark-themed tkinter app for editing profiles.json. Pick a
profile (TV, Lights, PC, or a custom one), click a key on the piano,
add one or more actions, and save. One key can drive multiple devices
at once. The Launch button spawns main.py as a subprocess.
"""

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox, simpledialog

import profiles as profile_store


ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "config.json")


def _load_light_names() -> list[str]:
    """Read configured Govee device names from config.json."""
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
    except Exception:
        return []
    govee = cfg.get("govee", {})
    devices = govee.get("devices")
    if isinstance(devices, list):
        return [d.get("name", "") for d in devices if d.get("name")]
    if "device_mac" in govee:
        return ["default"]
    return []


# ---- Keyboard range --------------------------------------------------------
# The Casio CT-S100 has 61 keys, C2 (MIDI 36) to C7 (MIDI 96).
FIRST_NOTE = 36
LAST_NOTE = 96
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(midi_note: int) -> str:
    return f"{NOTE_NAMES[midi_note % 12]}{(midi_note // 12) - 1}"


def is_black_key(midi_note: int) -> bool:
    return NOTE_NAMES[midi_note % 12].endswith("#")


# ---- Theme -----------------------------------------------------------------
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

# Piano key colors
PIANO_WHITE       = "#e4e6ee"
PIANO_WHITE_HOVER = "#c7cae0"
PIANO_BLACK       = "#181824"
PIANO_BLACK_HOVER = "#2a2a3a"
PIANO_C_LABEL     = "#6c7086"

# Mode color badges (shown on mapped keys).
MODE_COLORS = {
    "LIGHTS": "#ff9e6d",
    "TV":     "#6da9ff",
    "GAME":   "#a6e3a1",
    "AUDIO":  "#cba6f7",
}

FONT_FAMILY = "Segoe UI"
FONT_BODY   = (FONT_FAMILY, 10)
FONT_SMALL  = (FONT_FAMILY, 9)
FONT_TITLE  = (FONT_FAMILY, 16, "bold")
FONT_SUB    = (FONT_FAMILY, 10)
FONT_MONO   = ("Consolas", 10)


ACTIONS_BY_MODE = {
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


def _mapping_entries(mapping) -> list[dict]:
    """Normalize a mapping value into a list of action entries."""
    if mapping is None:
        return []
    if isinstance(mapping.get("actions"), list):
        return list(mapping["actions"])
    if mapping.get("mode"):
        return [mapping]
    return []


# ============================================================================


class PianoCanvas(tk.Frame):
    """Scrollable 61-key piano. Click a key to select it; selection is
    highlighted and mapped keys show a colored mode indicator."""

    WHITE_H  = 130       # white key height
    BLACK_H  = 82        # black key height
    WHITE_W_MIN = 18     # minimum white-key width (horizontal scroll kicks in)
    PAD_TOP  = 10
    PAD_BOT  = 18        # reserve bottom area for labels

    def __init__(self, parent, *, first_note: int, last_note: int,
                 on_select, get_entries):
        super().__init__(parent, bg=BG, highlightthickness=0)
        self.first_note = first_note
        self.last_note = last_note
        self._on_select = on_select
        self._get_entries = get_entries
        self.selected: int | None = None
        self._hover: int | None = None

        # White-key notes in the visible range, in order.
        self._white_notes = [n for n in range(first_note, last_note + 1)
                              if not is_black_key(n)]

        # Canvas + horizontal scrollbar.
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0,
                                bd=0, height=self.WHITE_H + self.PAD_TOP
                                + self.PAD_BOT)
        self._hbar = ttk.Scrollbar(self, orient="horizontal",
                                    command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=self._hbar.set)
        self.canvas.pack(side="top", fill="both", expand=True)
        self._hbar.pack(side="bottom", fill="x")

        # Key item lookups — note -> canvas item id for the key rect.
        self._key_items: dict[int, int] = {}
        self._label_items: dict[int, int] = {}
        self._badge_items: dict[int, int] = {}

        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda _e: self._set_hover(None))

        self._white_w = self.WHITE_W_MIN
        self._redraw()

    # ---- layout ----------------------------------------------------------

    def _on_canvas_resize(self, _e=None):
        # Make white keys as wide as possible while keeping all visible.
        avail = max(self.canvas.winfo_width(), 1)
        target = max(avail / len(self._white_notes), self.WHITE_W_MIN)
        if abs(target - self._white_w) > 0.5:
            self._white_w = target
            self._redraw()
        else:
            # Same layout — just update scroll region to current canvas width.
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _white_x(self, note: int) -> float:
        """Left-edge x coordinate of a white key."""
        idx = self._white_notes.index(note)
        return idx * self._white_w

    def _black_x(self, note: int) -> float:
        """Left-edge x coordinate of a black key (overlaps its two whites)."""
        # Each black key sits between the white key to its left and the
        # white key to its right. Find the white key just before it.
        prev_white = note - 1
        bw = self._white_w * 0.60
        return self._white_x(prev_white) + (self._white_w - bw / 2)

    # ---- drawing ---------------------------------------------------------

    def _redraw(self):
        self.canvas.delete("all")
        self._key_items.clear()
        self._label_items.clear()
        self._badge_items.clear()

        wh = self.WHITE_H
        bh = self.BLACK_H
        bw = self._white_w * 0.60
        top = self.PAD_TOP

        # White keys first (behind).
        for n in self._white_notes:
            x = self._white_x(n)
            rect = self.canvas.create_rectangle(
                x, top, x + self._white_w, top + wh,
                fill=PIANO_WHITE, outline=BORDER, width=1,
                tags=(f"note:{n}", "white"))
            self._key_items[n] = rect

            # C-note label at bottom, lightly colored so octaves are visible.
            if NOTE_NAMES[n % 12] == "C":
                self._label_items[n] = self.canvas.create_text(
                    x + self._white_w / 2, top + wh - 8,
                    text=note_name(n), fill=PIANO_C_LABEL, font=FONT_SMALL,
                    tags=("label", f"label:{n}"))

        # Black keys on top.
        for n in range(self.first_note, self.last_note + 1):
            if not is_black_key(n):
                continue
            x = self._black_x(n)
            rect = self.canvas.create_rectangle(
                x, top, x + bw, top + bh,
                fill=PIANO_BLACK, outline=PIANO_BLACK, width=0,
                tags=(f"note:{n}", "black"))
            self._key_items[n] = rect

        # Mapping badges on top of everything.
        for n in range(self.first_note, self.last_note + 1):
            self._draw_badge(n)

        # Scroll region = whole drawn area.
        total_w = len(self._white_notes) * self._white_w
        self.canvas.configure(
            scrollregion=(0, 0, total_w, wh + self.PAD_TOP + self.PAD_BOT))

        # Re-apply selection highlight.
        if self.selected is not None:
            self._style_key(self.selected)

    def _draw_badge(self, note: int):
        """Colored dot on a mapped key, colored by the first action's mode."""
        entries = _mapping_entries(self._get_entries(note))
        if not entries:
            return
        mode = entries[0].get("mode", "")
        color = MODE_COLORS.get(mode, ACCENT)

        if is_black_key(note):
            bw = self._white_w * 0.60
            x = self._black_x(note) + bw / 2
            y = self.PAD_TOP + self.BLACK_H - 10
        else:
            x = self._white_x(note) + self._white_w / 2
            y = self.PAD_TOP + self.WHITE_H - 22

        r = min(4, self._white_w * 0.18)
        self._badge_items[note] = self.canvas.create_oval(
            x - r, y - r, x + r, y + r,
            fill=color, outline="", tags=("badge", f"badge:{note}"))

    # ---- interaction -----------------------------------------------------

    def _note_at(self, x: int, y: int) -> int | None:
        """Return the MIDI note under (x, y), giving black keys priority."""
        # Canvas x may need adjustment if scrolled.
        cx = self.canvas.canvasx(x)
        cy = self.canvas.canvasy(y)

        # Black keys first (they're on top).
        bh = self.BLACK_H
        bw = self._white_w * 0.60
        if self.PAD_TOP <= cy <= self.PAD_TOP + bh:
            for n in range(self.first_note, self.last_note + 1):
                if not is_black_key(n):
                    continue
                bx = self._black_x(n)
                if bx <= cx <= bx + bw:
                    return n

        # White keys.
        if self.PAD_TOP <= cy <= self.PAD_TOP + self.WHITE_H:
            for n in self._white_notes:
                wx = self._white_x(n)
                if wx <= cx <= wx + self._white_w:
                    return n
        return None

    def _on_click(self, e):
        note = self._note_at(e.x, e.y)
        if note is None:
            return
        self.set_selected(note)
        self._on_select(note)

    def _on_motion(self, e):
        self._set_hover(self._note_at(e.x, e.y))

    def _set_hover(self, note: int | None):
        if note == self._hover:
            return
        prev = self._hover
        self._hover = note
        if prev is not None:
            self._style_key(prev)
        if note is not None:
            self._style_key(note)

    # ---- public API ------------------------------------------------------

    def set_selected(self, note: int):
        prev = self.selected
        self.selected = note
        if prev is not None:
            self._style_key(prev)
        self._style_key(note)
        # Scroll to keep the selection visible.
        x = (self._black_x(note) if is_black_key(note)
             else self._white_x(note))
        total_w = len(self._white_notes) * self._white_w
        if total_w > self.canvas.winfo_width():
            self.canvas.xview_moveto(max(0, (x - 40) / total_w))

    def refresh_mapping(self, note: int):
        """Redraw mapping badges around a note (e.g. after mapping changed)."""
        # Easiest: wipe all badges and redraw (cheap for ~60 keys).
        self.canvas.delete("badge")
        self._badge_items.clear()
        for n in range(self.first_note, self.last_note + 1):
            self._draw_badge(n)

    def refresh_all(self):
        self._redraw()

    # ---- per-key styling -------------------------------------------------

    def _style_key(self, note: int):
        item = self._key_items.get(note)
        if item is None:
            return
        black = is_black_key(note)
        selected = (note == self.selected)
        hover = (note == self._hover)

        if selected:
            fill = ACCENT
            outline = ACCENT_2
        elif hover:
            fill = PIANO_BLACK_HOVER if black else PIANO_WHITE_HOVER
            outline = BORDER if not black else PIANO_BLACK_HOVER
        else:
            fill = PIANO_BLACK if black else PIANO_WHITE
            outline = PIANO_BLACK if black else BORDER

        self.canvas.itemconfigure(item, fill=fill, outline=outline)


# ============================================================================


class ActionEditor(tk.Frame):
    """One action within a key's mapping. A key can stack several."""

    def __init__(self, parent, *, index: int, light_names: list[str],
                 on_change, on_remove):
        super().__init__(parent, bg=SURFACE, highlightthickness=0, bd=0)
        self._light_names = light_names
        self._on_change = on_change
        self._suspend_trace = False

        header = tk.Frame(self, bg=SURFACE)
        header.pack(fill="x", padx=12, pady=(10, 4))
        self._title_lbl = tk.Label(header, text=f"Action {index}", bg=SURFACE,
                                    fg=SUBTEXT, font=(FONT_FAMILY, 9, "bold"))
        self._title_lbl.pack(side="left")
        tk.Button(header, text="×", command=on_remove,
                  bg=SURFACE, fg=MUTED, activebackground=SURFACE_2,
                  activeforeground=DANGER, borderwidth=0, relief="flat",
                  font=(FONT_FAMILY, 12), padx=8, cursor="hand2"
                  ).pack(side="right")

        body = tk.Frame(self, bg=SURFACE)
        body.pack(fill="x", padx=12, pady=(0, 10))

        combo_row = tk.Frame(body, bg=SURFACE)
        combo_row.pack(anchor="w", fill="x")
        self._sub_label(combo_row, "Mode").grid(row=0, column=0, sticky="w",
                                                 padx=(0, 10))
        self._sub_label(combo_row, "Action").grid(row=0, column=1, sticky="w")

        self.mode_var = tk.StringVar(value="LIGHTS")
        self.mode_combo = ttk.Combobox(combo_row, textvariable=self.mode_var,
                                        state="readonly", width=12,
                                        values=list(ACTIONS_BY_MODE.keys()))
        self.mode_combo.grid(row=1, column=0, sticky="w", padx=(0, 10),
                             pady=(2, 0))
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_change)

        self.action_var = tk.StringVar(value="")
        self.action_combo = ttk.Combobox(combo_row, textvariable=self.action_var,
                                          state="readonly", width=16)
        self.action_combo.grid(row=1, column=1, sticky="w", pady=(2, 0))
        self.action_combo.bind("<<ComboboxSelected>>", self._on_action_change)

        self.color_frame = tk.Frame(body, bg=SURFACE)
        self._sub_label(self.color_frame, "Color").pack(anchor="w",
                                                         pady=(8, 2))
        color_row = tk.Frame(self.color_frame, bg=SURFACE)
        color_row.pack(anchor="w")
        self.color_var = tk.StringVar(value="#ff0000")
        self.color_swatch = tk.Label(color_row, text="    ", bg="#ff0000",
                                      width=3, borderwidth=0)
        self.color_swatch.pack(side="left", padx=(0, 8))
        self.color_entry = ttk.Entry(color_row, textvariable=self.color_var,
                                      width=12)
        self.color_entry.pack(side="left")
        self.color_var.trace_add("write", lambda *_: self._on_color_entry())
        ttk.Button(color_row, text="Pick…", style="Ghost.TButton",
                   command=self._pick_color).pack(side="left", padx=(8, 0))

        self.brightness_frame = tk.Frame(body, bg=SURFACE)
        self._sub_label(self.brightness_frame, "Brightness").pack(
            anchor="w", pady=(8, 2))
        bright_row = tk.Frame(self.brightness_frame, bg=SURFACE)
        bright_row.pack(anchor="w", fill="x")
        self.brightness_var = tk.IntVar(value=80)
        self.brightness_scale = ttk.Scale(
            bright_row, from_=1, to=100, orient="horizontal",
            variable=self.brightness_var, length=220,
            command=lambda _v: self._update_brightness_label())
        self.brightness_scale.pack(side="left")
        self.brightness_label = tk.Label(bright_row, text="80", bg=SURFACE,
                                          fg=SUBTEXT, font=FONT_SUB, width=4)
        self.brightness_label.pack(side="left", padx=(10, 0))

        self.tvkey_frame = tk.Frame(body, bg=SURFACE)
        self._sub_label(self.tvkey_frame, "TV key").pack(anchor="w",
                                                          pady=(8, 2))
        self.tvkey_var = tk.StringVar(value="KEY_VOLUP")
        self.tvkey_combo = ttk.Combobox(self.tvkey_frame,
                                         textvariable=self.tvkey_var,
                                         state="readonly", width=22,
                                         values=TV_KEYS)
        self.tvkey_combo.pack(anchor="w")
        self.tvkey_combo.bind("<<ComboboxSelected>>",
                              lambda _e: self._fire_change())

        self.targets_frame = tk.Frame(body, bg=SURFACE)
        self._sub_label(self.targets_frame, "Lights").pack(anchor="w",
                                                            pady=(8, 2))
        targets_row = tk.Frame(self.targets_frame, bg=SURFACE)
        targets_row.pack(anchor="w")
        self.target_vars: dict[str, tk.BooleanVar] = {}
        for name in self._light_names:
            var = tk.BooleanVar(value=True)
            var.trace_add("write", lambda *_: self._fire_change())
            self.target_vars[name] = var
            tk.Checkbutton(
                targets_row, text=name, variable=var,
                bg=SURFACE, fg=TEXT, activebackground=SURFACE,
                activeforeground=TEXT, selectcolor=SURFACE_2,
                borderwidth=0, highlightthickness=0, font=FONT_BODY,
            ).pack(side="left", padx=(0, 10))

        self._refresh_actions_for_mode()

    def _sub_label(self, parent, text) -> tk.Label:
        return tk.Label(parent, text=text.upper(), bg=SURFACE, fg=MUTED,
                        font=FONT_SMALL)

    def set_index(self, i: int) -> None:
        self._title_lbl.configure(text=f"Action {i}")

    def _fire_change(self):
        if not self._suspend_trace:
            self._on_change()

    def _on_mode_change(self, _evt=None):
        self._refresh_actions_for_mode()
        self._fire_change()

    def _on_action_change(self, _evt=None):
        self._refresh_conditional_fields()
        self._fire_change()

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
        mode = self.mode_var.get()
        action = self.action_var.get()
        for f in (self.color_frame, self.brightness_frame,
                  self.tvkey_frame, self.targets_frame):
            f.pack_forget()
        if mode == "LIGHTS":
            if action == "color":
                self.color_frame.pack(anchor="w", fill="x")
            if action in ("color", "turn_on"):
                self.brightness_frame.pack(anchor="w", fill="x")
            if self._light_names:
                self.targets_frame.pack(anchor="w", fill="x")
        elif mode == "TV" and action == "key":
            self.tvkey_frame.pack(anchor="w", fill="x")

    def _on_color_entry(self):
        c = self.color_var.get().strip()
        if len(c) == 7 and c.startswith("#"):
            try:
                int(c[1:], 16)
                self.color_swatch.configure(bg=c)
                self._fire_change()
            except ValueError:
                pass

    def _pick_color(self):
        initial = self.color_var.get() or "#ffffff"
        _, hex_val = colorchooser.askcolor(color=initial, title="Pick a color")
        if hex_val:
            self.color_var.set(hex_val)
            self.color_swatch.configure(bg=hex_val)
            self._fire_change()

    def _update_brightness_label(self):
        v = int(self.brightness_var.get())
        self.brightness_label.configure(text=str(v))
        self._fire_change()

    def to_dict(self) -> dict | None:
        mode = self.mode_var.get()
        action = self.action_var.get()
        if not action:
            return None
        entry: dict = {"mode": mode, "action": action}
        if mode == "LIGHTS":
            if action == "color":
                entry["color"] = self.color_var.get()
                entry["brightness"] = int(self.brightness_var.get())
            elif action == "turn_on":
                entry["brightness"] = int(self.brightness_var.get())
            checked = [n for n, v in self.target_vars.items() if v.get()]
            if self.target_vars and len(checked) != len(self.target_vars):
                entry["targets"] = checked
        elif mode == "TV" and action == "key":
            entry["key"] = self.tvkey_var.get()
        return entry

    def from_dict(self, entry: dict) -> None:
        self._suspend_trace = True
        try:
            self.mode_var.set(entry.get("mode", "LIGHTS"))
            self._refresh_actions_for_mode()
            action = entry.get("action", "")
            if action in self.action_combo["values"]:
                self.action_var.set(action)
            if "color" in entry:
                self.color_var.set(entry["color"])
                try:
                    self.color_swatch.configure(bg=entry["color"])
                except tk.TclError:
                    pass
            if "brightness" in entry:
                self.brightness_var.set(int(entry["brightness"]))
                self.brightness_label.configure(
                    text=str(int(entry["brightness"])))
            if "key" in entry:
                self.tvkey_var.set(entry["key"])
            if entry.get("mode") == "LIGHTS":
                targets = entry.get("targets")
                selected = set(targets) if targets else set(self.target_vars)
                for name, var in self.target_vars.items():
                    var.set(name in selected)
            self._refresh_conditional_fields()
        finally:
            self._suspend_trace = False


# ============================================================================


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Casio Universal Controller")
        self.geometry("1100x740")
        self.minsize(960, 620)
        self.configure(bg=BG)

        self.profiles_data = profile_store.load()
        self.light_names: list[str] = _load_light_names()
        self.selected_note: int | None = None
        self._editors: list[ActionEditor] = []
        self._loading = False
        self._controller_proc: subprocess.Popen | None = None
        self._controller_reader_thread = None

        self._apply_theme()
        self._build_layout()
        self._select_note(60)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- Data helpers ----------------------------------------------------

    @property
    def active_profile(self) -> str:
        return self.profiles_data.get("active", "pc")

    @property
    def current_mappings(self) -> dict:
        return self.profiles_data["profiles"].setdefault(self.active_profile, {})

    def _save_profiles(self) -> None:
        try:
            profile_store.save(self.profiles_data)
            self._set_status(f"Saved profile '{self.active_profile}' ✓", SUCCESS)
        except Exception as e:
            messagebox.showerror("Save error", str(e))

    # ---- Theme -----------------------------------------------------------

    def _apply_theme(self):
        style = ttk.Style(self)
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
        style.configure("TCombobox",
                        fieldbackground=SURFACE_2, background=SURFACE_2,
                        foreground=TEXT, arrowcolor=SUBTEXT,
                        borderwidth=0, padding=6)
        style.map("TCombobox",
                  fieldbackground=[("readonly", SURFACE_2)],
                  foreground=[("readonly", TEXT)])
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
                        background=BG, troughcolor=SURFACE_2, borderwidth=0)
        style.configure("Vertical.TScrollbar",
                        background=SURFACE, troughcolor=BG,
                        arrowcolor=SUBTEXT, borderwidth=0)
        style.configure("Horizontal.TScrollbar",
                        background=SURFACE, troughcolor=BG,
                        arrowcolor=SUBTEXT, borderwidth=0)

    # ---- Layout ----------------------------------------------------------

    def _build_layout(self):
        # Header
        header = ttk.Frame(self, padding=(24, 20, 24, 14))
        header.pack(side="top", fill="x")
        ttk.Label(header, text="Casio Universal Controller",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(header,
                  text="Pick a profile, click a piano key, and stack actions.",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 0))

        # Profile row
        profile_row = ttk.Frame(self, padding=(24, 0, 24, 14))
        profile_row.pack(side="top", fill="x")
        ttk.Label(profile_row, text="PROFILE",
                  style="Muted.TLabel").pack(side="left", padx=(0, 8))
        self.profile_var = tk.StringVar(value=self.active_profile)
        self.profile_combo = ttk.Combobox(
            profile_row, textvariable=self.profile_var, state="readonly",
            width=18, values=list(self.profiles_data["profiles"].keys()))
        self.profile_combo.pack(side="left")
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_change)
        ttk.Button(profile_row, text="+ New", style="Ghost.TButton",
                   command=self._new_profile).pack(side="left", padx=(8, 0))
        ttk.Button(profile_row, text="Duplicate", style="Ghost.TButton",
                   command=self._duplicate_profile).pack(side="left", padx=(4, 0))
        ttk.Button(profile_row, text="Rename", style="Ghost.TButton",
                   command=self._rename_profile).pack(side="left", padx=(4, 0))
        ttk.Button(profile_row, text="Delete", style="Ghost.TButton",
                   command=self._delete_profile).pack(side="left", padx=(4, 0))
        ttk.Button(profile_row, text="Reset to default", style="Ghost.TButton",
                   command=self._reset_profile).pack(side="left", padx=(12, 0))

        # Legend for the piano badge colors
        legend = ttk.Frame(profile_row)
        legend.pack(side="right")
        for mode, color in MODE_COLORS.items():
            swatch = tk.Frame(legend, bg=color, width=10, height=10)
            swatch.pack(side="left", padx=(8, 4))
            swatch.pack_propagate(False)
            ttk.Label(legend, text=mode.lower(),
                      style="Muted.TLabel").pack(side="left")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Piano
        piano_wrap = ttk.Frame(self, padding=(16, 10, 16, 10))
        piano_wrap.pack(side="top", fill="x")
        self.piano = PianoCanvas(
            piano_wrap, first_note=FIRST_NOTE, last_note=LAST_NOTE,
            on_select=self._select_note,
            get_entries=lambda n: self.current_mappings.get(str(n)))
        self.piano.pack(fill="x")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Detail panel
        body = ttk.Frame(self, padding=(24, 12, 24, 10))
        body.pack(side="top", fill="both", expand=True)
        body.rowconfigure(2, weight=1)
        body.columnconfigure(0, weight=1)

        self.detail_title = ttk.Label(body, text="—", style="Title.TLabel")
        self.detail_title.grid(row=0, column=0, sticky="w")
        self.detail_sub = ttk.Label(
            body, text="Select a key to edit its mapping.",
            style="Sub.TLabel")
        self.detail_sub.grid(row=1, column=0, sticky="w", pady=(2, 12))

        scroll_holder = tk.Frame(body, bg=BG, highlightthickness=0)
        scroll_holder.grid(row=2, column=0, sticky="nsew")
        scroll_holder.rowconfigure(0, weight=1)
        scroll_holder.columnconfigure(0, weight=1)

        self._actions_canvas = tk.Canvas(scroll_holder, bg=BG,
                                          highlightthickness=0, borderwidth=0)
        act_scroll = ttk.Scrollbar(scroll_holder, orient="vertical",
                                    command=self._actions_canvas.yview)
        self._actions_canvas.configure(yscrollcommand=act_scroll.set)
        self._actions_canvas.grid(row=0, column=0, sticky="nsew")
        act_scroll.grid(row=0, column=1, sticky="ns")

        self._actions_inner = tk.Frame(self._actions_canvas, bg=BG)
        self._actions_inner_id = self._actions_canvas.create_window(
            (0, 0), window=self._actions_inner, anchor="nw")

        def _resize(_e=None):
            self._actions_canvas.configure(
                scrollregion=self._actions_canvas.bbox("all"))
            self._actions_canvas.itemconfig(
                self._actions_inner_id,
                width=self._actions_canvas.winfo_width())
        self._actions_inner.bind("<Configure>", _resize)
        self._actions_canvas.bind("<Configure>", _resize)

        btn_row = ttk.Frame(body)
        btn_row.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        ttk.Button(btn_row, text="+ Add action",
                   command=self._add_action).pack(side="left")
        ttk.Button(btn_row, text="Clear mapping", style="Ghost.TButton",
                   command=self._clear_mapping).pack(side="right")

        # Collapsible controller log
        log_wrap = ttk.Frame(self, padding=(24, 4, 24, 0))
        log_wrap.pack(side="top", fill="x")
        log_header = ttk.Frame(log_wrap)
        log_header.pack(fill="x")
        ttk.Label(log_header, text="CONTROLLER LOG",
                  style="Muted.TLabel").pack(side="left")
        ttk.Button(log_header, text="Clear", style="Ghost.TButton",
                   command=self._clear_log).pack(side="right")
        log_frame = tk.Frame(log_wrap, bg=SURFACE, highlightthickness=0)
        log_frame.pack(fill="x", pady=(4, 0))
        self.log_text = tk.Text(
            log_frame, height=8, bg=SURFACE, fg=TEXT, insertbackground=TEXT,
            borderwidth=0, relief="flat", font=FONT_MONO, wrap="word",
            state="disabled")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical",
                                    command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True,
                           padx=(8, 0), pady=8)
        log_scroll.pack(side="right", fill="y")

        # Footer
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        footer = ttk.Frame(self, padding=(24, 14, 24, 18))
        footer.pack(side="bottom", fill="x")
        ttk.Button(footer, text="Save", style="Accent.TButton",
                   command=self._save_profiles).pack(side="left")
        self.launch_btn = ttk.Button(
            footer, text="▶  Start controller",
            command=self._toggle_controller)
        self.launch_btn.pack(side="left", padx=(10, 0))
        self.run_state_var = tk.StringVar(value="● stopped")
        self.run_state_lbl = ttk.Label(
            footer, textvariable=self.run_state_var, style="Muted.TLabel")
        self.run_state_lbl.pack(side="left", padx=(12, 0))
        self.status_var = tk.StringVar(value="Ready")
        self.status_lbl = ttk.Label(footer, textvariable=self.status_var,
                                    style="Muted.TLabel")
        self.status_lbl.pack(side="right")

    # ---- Profile management ---------------------------------------------

    def _refresh_profile_combo(self):
        self.profile_combo["values"] = list(self.profiles_data["profiles"].keys())
        self.profile_var.set(self.active_profile)

    def _on_profile_change(self, _evt=None):
        new = self.profile_var.get()
        if new == self.active_profile or new not in self.profiles_data["profiles"]:
            return
        self.profiles_data["active"] = new
        self.piano.refresh_mapping(0)  # wipes + redraws all badges
        self._select_note(self.selected_note or 60)
        self._set_status(f"Switched to '{new}'", SUBTEXT)

    def _prompt_name(self, title: str, initial: str = "") -> str | None:
        name = simpledialog.askstring(title, "Profile name:",
                                       initialvalue=initial, parent=self)
        if not name:
            return None
        name = name.strip()
        if not name:
            return None
        if name in self.profiles_data["profiles"]:
            messagebox.showerror("Name taken",
                                  f"A profile named '{name}' already exists.")
            return None
        return name

    def _new_profile(self):
        name = self._prompt_name("New profile")
        if not name:
            return
        self.profiles_data["profiles"][name] = {}
        self.profiles_data["active"] = name
        self._refresh_profile_combo()
        self.piano.refresh_mapping(0)
        self._select_note(self.selected_note or 60)
        self._set_status(f"Created '{name}'", SUCCESS)

    def _duplicate_profile(self):
        src = self.active_profile
        name = self._prompt_name(f"Duplicate '{src}'", initial=f"{src}_copy")
        if not name:
            return
        self.profiles_data["profiles"][name] = json.loads(
            json.dumps(self.current_mappings))  # deep copy
        self.profiles_data["active"] = name
        self._refresh_profile_combo()
        self.piano.refresh_mapping(0)
        self._select_note(self.selected_note or 60)
        self._set_status(f"Duplicated to '{name}'", SUCCESS)

    def _rename_profile(self):
        old = self.active_profile
        name = self._prompt_name(f"Rename '{old}'", initial=old)
        if not name:
            return
        self.profiles_data["profiles"][name] = self.profiles_data["profiles"].pop(old)
        self.profiles_data["active"] = name
        self._refresh_profile_combo()
        self._set_status(f"Renamed to '{name}'", SUCCESS)

    def _reset_profile(self):
        name = self.active_profile
        if profile_store.is_default_profile(name):
            if not messagebox.askyesno(
                    "Reset profile",
                    f"Replace all '{name}' mappings with the built-in "
                    "defaults?\n\nThis can't be undone."):
                return
            profile_store.reset_to_default(self.profiles_data, name)
            self._save_profiles()
            self.piano.refresh_mapping(0)
            self._select_note(self.selected_note or 60)
            self._set_status(f"Reset '{name}' to defaults", SUCCESS)
            return

        # Custom profile — offer to restore every built-in instead.
        if not messagebox.askyesno(
                "Reset built-ins",
                f"'{name}' is a custom profile with no built-in default.\n\n"
                "Restore the tv / lights / pc built-in profiles to their "
                "defaults? (Your custom profile is left alone.)"):
            return
        restored = profile_store.reset_all_defaults(self.profiles_data)
        self._save_profiles()
        self.piano.refresh_mapping(0)
        self._select_note(self.selected_note or 60)
        self._set_status(
            f"Restored built-ins: {', '.join(restored)}", SUCCESS)

    def _delete_profile(self):
        name = self.active_profile
        if len(self.profiles_data["profiles"]) <= 1:
            messagebox.showinfo("Can't delete",
                                 "You need at least one profile.")
            return
        if not messagebox.askyesno("Delete profile",
                                    f"Delete profile '{name}'?"):
            return
        del self.profiles_data["profiles"][name]
        self.profiles_data["active"] = next(iter(self.profiles_data["profiles"]))
        self._refresh_profile_combo()
        self.piano.refresh_mapping(0)
        self._select_note(self.selected_note or 60)
        self._set_status(f"Deleted '{name}'", DANGER)

    # ---- Selection + state syncing ---------------------------------------

    def _scope_hint(self) -> str:
        scope = profile_store.profile_scope(self.active_profile)
        if scope is None:
            return "Scope: any mode (custom profile)."
        allowed = ", ".join(sorted(scope)).lower()
        return f"Scope: {allowed} only — other modes are ignored at run time."

    def _select_note(self, note: int):
        self.selected_note = note
        self.piano.set_selected(note)

        self.detail_title.configure(text=f"{note_name(note)}  ·  MIDI {note}")
        mapping = self.current_mappings.get(str(note))
        hint = self._scope_hint()
        if mapping is None:
            self.detail_sub.configure(
                text=f"Unassigned. Add an action to map it.   ·   {hint}")
        else:
            self.detail_sub.configure(
                text=f"Multiple actions run in parallel.   ·   {hint}")
        self._load_editors_from_mapping(mapping)
        self._set_status(f"Selected {note_name(note)}", SUBTEXT)

    def _load_editors_from_mapping(self, mapping):
        self._loading = True
        try:
            for ed in self._editors:
                ed.destroy()
            self._editors.clear()
            for entry in _mapping_entries(mapping):
                self._append_editor(entry)
        finally:
            self._loading = False

    def _append_editor(self, entry: dict | None = None):
        ed_holder: list = []

        def _remove():
            self._remove_editor(ed_holder[0])

        ed = ActionEditor(
            self._actions_inner,
            index=len(self._editors) + 1,
            light_names=self.light_names,
            on_change=self._commit_from_form,
            on_remove=_remove,
        )
        ed_holder.append(ed)
        ed.pack(fill="x", pady=(0, 10))
        self._editors.append(ed)
        if entry is not None:
            ed.from_dict(entry)
        else:
            ed.from_dict({"mode": "LIGHTS", "action": "turn_on"})
        self._renumber_editors()

        self.after_idle(lambda: self._actions_canvas.yview_moveto(1.0))

    def _add_action(self):
        self._append_editor(None)
        self._commit_from_form()

    def _remove_editor(self, editor: ActionEditor):
        if editor in self._editors:
            self._editors.remove(editor)
        editor.destroy()
        self._renumber_editors()
        self._commit_from_form()

    def _renumber_editors(self):
        for i, ed in enumerate(self._editors, start=1):
            ed.set_index(i)

    def _clear_mapping(self):
        if self.selected_note is None:
            return
        self.current_mappings.pop(str(self.selected_note), None)
        self._load_editors_from_mapping(None)
        self.piano.refresh_mapping(self.selected_note)
        self._set_status(f"Cleared {note_name(self.selected_note)}", SUBTEXT)

    # ---- Writing back into the active profile ---------------------------

    def _commit_from_form(self):
        if self.selected_note is None or self._loading:
            return
        entries: list[dict] = []
        for ed in list(self._editors):
            if not ed.winfo_exists():
                continue
            d = ed.to_dict()
            if d:
                entries.append(d)

        key = str(self.selected_note)
        mappings = self.current_mappings
        if not entries:
            mappings.pop(key, None)
        elif len(entries) == 1:
            mappings[key] = entries[0]
        else:
            mappings[key] = {"actions": entries}
        self.piano.refresh_mapping(self.selected_note)

        scope = profile_store.profile_scope(self.active_profile)
        if scope is not None:
            bad = [e.get("mode", "?") for e in entries
                   if not profile_store.is_in_scope(e, scope)]
            if bad:
                self._set_status(
                    f"{', '.join(bad)} action won't fire in "
                    f"'{self.active_profile}' — out of scope",
                    DANGER)

    # ---- Subprocess + status ---------------------------------------------

    def _toggle_controller(self):
        if self._controller_proc and self._controller_proc.poll() is None:
            self._stop_controller()
        else:
            self._start_controller()

    def _start_controller(self):
        # Save before launching so main.py reads current mappings.
        try:
            profile_store.save(self.profiles_data)
        except Exception as e:
            messagebox.showerror("Save error", str(e))
            return

        script = os.path.join(ROOT, "main.py")
        if not os.path.exists(script):
            self._set_status(f"main.py missing at {script}", DANGER)
            return

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        try:
            self._controller_proc = subprocess.Popen(
                [sys.executable, "-u", script],
                cwd=ROOT, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except Exception as e:
            self._set_status(f"Launch failed: {e}", DANGER)
            self._controller_proc = None
            return

        self._log_queue: queue.Queue[str] = queue.Queue()
        self._controller_reader_thread = threading.Thread(
            target=self._pump_output, args=(self._controller_proc,),
            daemon=True)
        self._controller_reader_thread.start()

        self._append_log(f"$ {sys.executable} main.py\n")
        self._update_run_state()
        self._set_status(
            f"Started controller (pid {self._controller_proc.pid})", SUCCESS)
        self.after(200, self._drain_log_queue)
        self.after(500, self._poll_controller)

    def _stop_controller(self):
        proc = self._controller_proc
        if not proc or proc.poll() is not None:
            self._update_run_state()
            return
        try:
            proc.send_signal(signal.SIGINT)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
        self._set_status("Stopping controller…", SUBTEXT)
        # If SIGINT doesn't take within 2s, hard-kill.
        self.after(2000, lambda: self._force_kill(proc))

    def _force_kill(self, proc):
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass

    def _pump_output(self, proc: subprocess.Popen):
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                self._log_queue.put(line)
        except Exception as e:
            self._log_queue.put(f"[reader error] {e}\n")
        finally:
            self._log_queue.put(
                f"\n[controller exited with code {proc.poll()}]\n")

    def _drain_log_queue(self):
        if not hasattr(self, "_log_queue"):
            return
        drained = 0
        try:
            while True:
                line = self._log_queue.get_nowait()
                self._append_log(line)
                drained += 1
                if drained > 200:
                    break
        except queue.Empty:
            pass
        # Keep draining as long as the process is alive or there may be
        # trailing output to flush.
        if (self._controller_proc and
                self._controller_proc.poll() is None) or drained:
            self.after(150, self._drain_log_queue)

    def _poll_controller(self):
        proc = self._controller_proc
        if proc is None:
            return
        code = proc.poll()
        if code is None:
            self.after(500, self._poll_controller)
            return
        self._update_run_state()
        if code == 0:
            self._set_status("Controller stopped", SUBTEXT)
        else:
            self._set_status(
                f"Controller exited with code {code} — see log below",
                DANGER)

    def _update_run_state(self):
        running = (self._controller_proc is not None and
                   self._controller_proc.poll() is None)
        if running:
            self.run_state_var.set(
                f"● running (pid {self._controller_proc.pid})")
            self.run_state_lbl.configure(foreground=SUCCESS)
            self.launch_btn.configure(text="■  Stop controller")
        else:
            self.run_state_var.set("● stopped")
            self.run_state_lbl.configure(foreground=MUTED)
            self.launch_btn.configure(text="▶  Start controller")

    def _clear_log(self):
        if not hasattr(self, "log_text"):
            return
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _append_log(self, text: str):
        if not hasattr(self, "log_text"):
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        # Cap buffer so it doesn't grow unbounded.
        max_lines = 2000
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > max_lines:
            self.log_text.delete("1.0", f"{line_count - max_lines}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _on_close(self):
        proc = self._controller_proc
        if proc and proc.poll() is None:
            try:
                proc.send_signal(signal.SIGINT)
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self.destroy()

    def _set_status(self, text: str, color: str = SUBTEXT):
        self.status_var.set(text)
        self.status_lbl.configure(foreground=color)


if __name__ == "__main__":
    App().mainloop()
