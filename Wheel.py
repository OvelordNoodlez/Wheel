"""
Random Spin Wheel
=================
A small Tkinter spin-the-wheel picker (standard library only).

Shortcuts
---------
Setup screen : Enter = next / new row   Up/Down = move   Ctrl+Enter = create wheel
               Backspace on an empty row = delete it    Paste a multi-line list = one row per line
Wheel screen : Space / Enter / click the wheel = spin
Anywhere     : Ctrl+S = save wheel          Ctrl+O = load wheel
"""

import json
import math
import random
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

# -------------------------------------------------
# SETTINGS
# -------------------------------------------------

MIN_OPTIONS = 2
MAX_OPTIONS = 30
MAX_NAME_LEN = 60
MAX_HISTORY = 100
FRAME_MS = 15

SPIN_TURNS = (4, 6)          # full rotations (min, max)
SPIN_SECONDS = (4.5, 6.0)    # spin duration (min, max)

# Dark theme
BG = "#14161f"
PANEL = "#1d2030"
ENTRY_BG = "#2a2e45"
FG = "#e8eaf2"
MUTED = "#8b90a7"
ACCENT = "#7c6cf0"
ACCENT_HOVER = "#9486ff"
BTN_BG = "#2f3450"
BTN_HOVER = "#3d4466"
GOLD = "#ffd166"

SLICE_COLORS = [
    "#FF6B6B", "#4ECDC4", "#FFD93D", "#6C5CE7", "#FF9F43",
    "#54A0FF", "#A55EEA", "#10AC84", "#EE5253", "#00D2D3",
]


# -------------------------------------------------
# HELPERS
# -------------------------------------------------

def clean_name(text):
    """Collapse whitespace and enforce the maximum name length."""
    return " ".join(str(text).split())[:MAX_NAME_LEN]


def build_palette(count):
    """One colour per slice, making sure neighbours never match (incl. last/first)."""
    colors = [SLICE_COLORS[i % len(SLICE_COLORS)] for i in range(count)]

    if count > 2 and (colors[-1] == colors[0] or colors[-1] == colors[-2]):
        for candidate in SLICE_COLORS:
            if candidate != colors[0] and candidate != colors[-2]:
                colors[-1] = candidate
                break

    return colors


def readable_text_color(hex_color):
    """Dark text on light slices, white text on dark slices."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return "#1b1d2a" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#ffffff"


def fit_text(font, text, max_px):
    """Shorten text with an ellipsis so it fits in max_px."""
    if font.measure(text) <= max_px:
        return text

    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.measure(text[:mid].rstrip() + "…") <= max_px:
            lo = mid
        else:
            hi = mid - 1

    return (text[:lo].rstrip() + "…") if lo else "…"


def read_options_file(path):
    """Load options from a .json wheel file (or a plain text file, one per line)."""
    with open(path, "r", encoding="utf-8") as file:
        raw = file.read()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = raw.splitlines()

    if isinstance(data, dict):
        data = data.get("options")

    if not isinstance(data, list):
        raise ValueError("This is not a valid wheel file.")

    options = [clean_name(item) for item in data]
    options = [item for item in options if item]

    if len(options) < MIN_OPTIONS:
        raise ValueError(f"A wheel must contain at least {MIN_OPTIONS} options.")

    if len(options) > MAX_OPTIONS:
        raise ValueError(f"This wheel contains more than {MAX_OPTIONS} options.")

    return options


class Row:
    """One editable option row on the setup screen."""
    __slots__ = ("frame", "label", "var", "entry", "button")


# -------------------------------------------------
# APP
# -------------------------------------------------

class SpinWheelApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Random Spin Wheel")
        self.root.geometry("1040x740")
        self.root.minsize(860, 620)
        self.root.configure(bg=BG)

        families = set(tkfont.families())
        self.font = next(
            (f for f in ("Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans") if f in families),
            tkfont.nametofont("TkDefaultFont").actual("family"),
        )

        # Data
        self.options = []
        self.rows = []
        self.screen = None

        # Wheel / animation state
        self.rotation = 0.0
        self.spinning = False
        self.spin_after_id = None
        self.pulse_after_id = None
        self.resize_after_id = None
        self.status_after_id = None
        self.spin_start = 0.0
        self.spin_delta = 0.0
        self.spin_duration = 1.0
        self.spin_origin = 0.0
        self.winning_index = None
        self.highlight_index = None
        self.pending_removal = None
        self.spin_count = 0
        self.kick = 0.0
        self.last_tick_index = None

        # Canvas items (rebuilt on resize / option change)
        self.arcs, self.texts, self.pegs = [], [], []
        self.highlight_item = None
        self.pointer = None
        self.slice_colors = []
        self.wheel_font = None
        self.geometry = (0, 0, 0)
        self.last_canvas_size = (0, 0)

        self._build_style()
        self._build_setup_ui()
        self._build_wheel_ui()
        self._bind_global_keys()

        for _ in range(4):
            self._insert_row(len(self.rows), "")
        self._repack_rows()

        self.show_screen("setup")
        self.rows[0].entry.focus_set()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # -------------------------------------------------
    # STYLE
    # -------------------------------------------------

    def _build_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        f = self.font

        style.configure(
            "TButton", font=(f, 11), padding=(14, 8), background=BTN_BG,
            foreground=FG, borderwidth=0, focuscolor=BTN_BG, relief="flat",
        )
        style.map(
            "TButton",
            background=[("disabled", "#23263a"), ("active", BTN_HOVER)],
            foreground=[("disabled", MUTED)],
        )

        style.configure("Accent.TButton", font=(f, 12, "bold"), background=ACCENT,
                        foreground="#ffffff", focuscolor=ACCENT, padding=(18, 10))
        style.map(
            "Accent.TButton",
            background=[("disabled", "#3a3566"), ("active", ACCENT_HOVER)],
            foreground=[("disabled", "#8f8ab5")],
        )

        style.configure("Spin.Accent.TButton", font=(f, 20, "bold"), padding=(20, 14))
        style.configure("Icon.TButton", font=(f, 11, "bold"), padding=(8, 4))

        style.configure("TCheckbutton", background=PANEL, foreground=FG, font=(f, 11))
        style.map(
            "TCheckbutton",
            background=[("active", PANEL)],
            indicatorcolor=[("selected", ACCENT), ("!selected", ENTRY_BG)],
        )

        style.configure(
            "Vertical.TScrollbar", background=BTN_BG, troughcolor=PANEL,
            bordercolor=PANEL, arrowcolor=FG, lightcolor=BTN_BG, darkcolor=BTN_BG,
        )

    def _button(self, parent, text, command, style="TButton", cursor="hand2"):
        return ttk.Button(parent, text=text, command=command, style=style, cursor=cursor)

    # -------------------------------------------------
    # GENERAL
    # -------------------------------------------------

    def show_screen(self, name):
        self.stop_animation()
        self.screen = name

        self.setup_frame.pack_forget()
        self.wheel_frame.pack_forget()

        frame = self.setup_frame if name == "setup" else self.wheel_frame
        frame.pack(fill="both", expand=True)

    def stop_animation(self):
        """Cancel any pending animation callbacks."""
        for attr in ("spin_after_id", "pulse_after_id", "resize_after_id"):
            after_id = getattr(self, attr)
            if after_id is not None:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
                setattr(self, attr, None)

        self.spinning = False

        if hasattr(self, "spin_button"):
            self._refresh_spin_button()

    def _on_close(self):
        self.stop_animation()
        self.root.destroy()

    def _bind_global_keys(self):
        self.root.bind_all("<Control-s>", lambda e: self.save_current())
        self.root.bind_all("<Control-o>", lambda e: self.load_wheel())
        self.root.bind_all("<Control-Return>", lambda e: self.create_wheel() if self.screen == "setup" else None)
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)
        self.root.bind_all("<Button-4>", self._on_mousewheel)
        self.root.bind_all("<Button-5>", self._on_mousewheel)

        self.root.bind("<space>", self._on_space)
        self.root.bind("<Return>", self._on_space)

    def _on_space(self, _event):
        if self.screen == "wheel":
            self.spin()
            return "break"

    def _on_mousewheel(self, event):
        if self.screen != "setup":
            return

        if getattr(event, "num", 0) == 4:
            step = -1
        elif getattr(event, "num", 0) == 5:
            step = 1
        else:
            step = -1 if event.delta > 0 else 1

        self.rows_canvas.yview_scroll(step, "units")

    def _flash_status(self, message, color=MUTED):
        self.setup_status.config(text=message, fg=color)

        if self.status_after_id is not None:
            self.root.after_cancel(self.status_after_id)

        self.status_after_id = self.root.after(
            3500, lambda: self.setup_status.config(text="")
        )

    # -------------------------------------------------
    # SETUP SCREEN
    # -------------------------------------------------

    def _build_setup_ui(self):
        self.setup_frame = tk.Frame(self.root, bg=BG)

        inner = tk.Frame(self.setup_frame, bg=BG)
        inner.pack(fill="y", expand=True, pady=18)

        tk.Label(inner, text="Spin Wheel", font=(self.font, 30, "bold"),
                 bg=BG, fg=FG).pack()
        tk.Label(
            inner,
            text="Type your options, or paste a list. Enter adds the next row.",
            font=(self.font, 11), bg=BG, fg=MUTED,
        ).pack(pady=(2, 14))

        # Toolbar
        toolbar = tk.Frame(inner, bg=BG)
        toolbar.pack(fill="x", pady=(0, 8))

        self._button(toolbar, "+ Add Option", self.add_option).pack(side="left")
        self._button(toolbar, "Bulk Add", self.bulk_add).pack(side="left", padx=6)
        self._button(toolbar, "Clear All", self.clear_all).pack(side="left")

        self.counter_label = tk.Label(toolbar, font=(self.font, 11), bg=BG, fg=MUTED)
        self.counter_label.pack(side="right")

        # Scrollable list of option rows
        card = tk.Frame(inner, bg=PANEL)
        card.pack(fill="both", expand=True)

        self.rows_canvas = tk.Canvas(card, bg=PANEL, highlightthickness=0, width=520)
        scrollbar = ttk.Scrollbar(card, orient="vertical", command=self.rows_canvas.yview)
        self.rows_canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.rows_canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)

        self.rows_frame = tk.Frame(self.rows_canvas, bg=PANEL)
        self.rows_window = self.rows_canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")

        self.rows_frame.bind(
            "<Configure>",
            lambda e: self.rows_canvas.configure(scrollregion=self.rows_canvas.bbox("all")),
        )
        self.rows_canvas.bind(
            "<Configure>",
            lambda e: self.rows_canvas.itemconfigure(self.rows_window, width=e.width),
        )

        self.setup_status = tk.Label(inner, text="", font=(self.font, 10), bg=BG, fg=MUTED)
        self.setup_status.pack(pady=(6, 0), anchor="w")

        # Footer
        footer = tk.Frame(inner, bg=BG)
        footer.pack(fill="x", pady=(8, 0))

        self._button(footer, "Load Wheel", self.load_wheel).pack(side="left")
        self._button(footer, "Save Wheel", self.save_current).pack(side="left", padx=6)
        self._button(footer, "Create Wheel  ▶", self.create_wheel, "Accent.TButton").pack(side="right")

    # ----- rows -----

    def _insert_row(self, index, text=""):
        row = Row()
        row.frame = tk.Frame(self.rows_frame, bg=PANEL)
        row.label = tk.Label(row.frame, width=3, anchor="e", font=(self.font, 12),
                             bg=PANEL, fg=MUTED)
        row.var = tk.StringVar(value=text)

        vcmd = (self.root.register(lambda value: len(value) <= MAX_NAME_LEN), "%P")
        row.entry = tk.Entry(
            row.frame, textvariable=row.var, font=(self.font, 13), relief="flat",
            bg=ENTRY_BG, fg=FG, insertbackground=FG, selectbackground=ACCENT,
            highlightthickness=2, highlightbackground=ENTRY_BG, highlightcolor=ACCENT,
            validate="key", validatecommand=vcmd,
        )
        row.button = ttk.Button(row.frame, text="✕", style="Icon.TButton", width=2,
                                cursor="hand2", command=lambda r=row: self.remove_row(r))

        row.label.pack(side="left")
        row.entry.pack(side="left", fill="x", expand=True, ipady=4, padx=(6, 6))
        row.button.pack(side="left", padx=(0, 4))

        row.entry.bind("<Return>", lambda e, r=row: self._on_entry_return(r))
        row.entry.bind("<Down>", lambda e, r=row: self._focus_neighbor(r, 1))
        row.entry.bind("<Up>", lambda e, r=row: self._focus_neighbor(r, -1))
        row.entry.bind("<BackSpace>", lambda e, r=row: self._on_entry_backspace(r))
        row.entry.bind("<<Paste>>", lambda e, r=row: self._on_paste(r))

        self.rows.insert(index, row)
        return row

    def _repack_rows(self):
        for i, row in enumerate(self.rows):
            row.frame.pack_forget()
            row.frame.pack(fill="x", pady=3, padx=(0, 6))
            row.label.config(text=f"{i + 1}.")

        self.counter_label.config(text=f"{len(self.rows)} / {MAX_OPTIONS} options")

    def add_option(self, index=None, focus=True):
        if len(self.rows) >= MAX_OPTIONS:
            self._flash_status(f"Maximum of {MAX_OPTIONS} options reached.", "#ff8b8b")
            return None

        row = self._insert_row(len(self.rows) if index is None else index, "")
        self._repack_rows()

        if focus:
            self._focus_row(self.rows.index(row))

        return row

    def remove_row(self, row):
        if row not in self.rows:
            return

        if len(self.rows) <= MIN_OPTIONS:
            row.var.set("")
            self._flash_status(f"A wheel needs at least {MIN_OPTIONS} options.")
            return

        index = self.rows.index(row)
        row.frame.destroy()
        self.rows.remove(row)
        self._repack_rows()
        self._focus_row(min(index, len(self.rows) - 1))

    def clear_all(self):
        self.set_rows([])

    def set_rows(self, names):
        """Replace every row with the given names (padded to the minimum row count)."""
        for row in self.rows:
            row.frame.destroy()
        self.rows = []

        for name in names:
            self._insert_row(len(self.rows), name)

        while len(self.rows) < max(MIN_OPTIONS, 4 if not names else 0):
            self._insert_row(len(self.rows), "")

        self._repack_rows()
        self.rows_canvas.yview_moveto(0)

    def _focus_row(self, index):
        if not 0 <= index < len(self.rows):
            return

        row = self.rows[index]
        row.entry.focus_set()
        row.entry.icursor(tk.END)

        # Keep the focused row visible
        self.rows_frame.update_idletasks()
        total = max(1, self.rows_frame.winfo_height())
        view_h = self.rows_canvas.winfo_height()
        top = self.rows_canvas.canvasy(0)
        y, h = row.frame.winfo_y(), row.frame.winfo_height()

        if y < top:
            self.rows_canvas.yview_moveto(y / total)
        elif y + h > top + view_h:
            self.rows_canvas.yview_moveto((y + h - view_h) / total)

    def _focus_neighbor(self, row, step):
        self._focus_row(self.rows.index(row) + step)
        return "break"

    def _on_entry_return(self, row):
        index = self.rows.index(row)

        if index + 1 < len(self.rows):
            self._focus_row(index + 1)
        else:
            self.add_option()

        return "break"

    def _on_entry_backspace(self, row):
        if row.var.get() == "" and len(self.rows) > MIN_OPTIONS:
            self.remove_row(row)
            return "break"

    def _on_paste(self, row):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return None

        lines = [clean_name(line) for line in text.splitlines()]
        lines = [line for line in lines if line]

        if len(lines) < 2:
            return None  # ordinary single-line paste: let Tk handle it

        index = self.rows.index(row)
        self._place_lines(lines, index if not row.var.get().strip() else index + 1)
        return "break"

    def _place_lines(self, lines, at):
        """Put lines into rows from index `at`, reusing blank rows and adding rows as needed."""
        placed = 0

        for line in lines:
            if at < len(self.rows) and not self.rows[at].var.get().strip():
                self.rows[at].var.set(line)
            elif len(self.rows) < MAX_OPTIONS:
                self._insert_row(at, line)
            else:
                break

            placed += 1
            at += 1

        self._repack_rows()

        if placed < len(lines):
            self._flash_status(
                f"Added {placed} of {len(lines)} - limit is {MAX_OPTIONS} options.", "#ff8b8b"
            )
        else:
            self._flash_status(f"Added {placed} options.")

        self._focus_row(min(at, len(self.rows) - 1))

    def bulk_add(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Bulk Add")
        dialog.configure(bg=PANEL)
        dialog.transient(self.root)
        dialog.resizable(False, False)

        tk.Label(dialog, text="One option per line:", font=(self.font, 12, "bold"),
                 bg=PANEL, fg=FG).pack(padx=16, pady=(14, 6), anchor="w")

        text = tk.Text(dialog, width=44, height=14, font=(self.font, 12), relief="flat",
                       bg=ENTRY_BG, fg=FG, insertbackground=FG, selectbackground=ACCENT,
                       padx=8, pady=8)
        text.pack(padx=16)
        text.focus_set()

        def submit():
            lines = [clean_name(line) for line in text.get("1.0", tk.END).splitlines()]
            lines = [line for line in lines if line]
            dialog.destroy()

            if lines:
                last_filled = max(
                    (i + 1 for i, r in enumerate(self.rows) if r.var.get().strip()), default=0
                )
                self._place_lines(lines, last_filled)

        buttons = tk.Frame(dialog, bg=PANEL)
        buttons.pack(fill="x", padx=16, pady=14)
        self._button(buttons, "Add", submit, "Accent.TButton").pack(side="right")
        self._button(buttons, "Cancel", dialog.destroy).pack(side="right", padx=6)

        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.update_idletasks()
        dialog.geometry(
            f"+{self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2}"
            f"+{self.root.winfo_rooty() + 80}"
        )
        dialog.grab_set()

    def collect_options(self):
        """Read the rows. Blank rows get a default name so the wheel never has empty slices."""
        options = []

        for i, row in enumerate(self.rows):
            name = clean_name(row.var.get())

            if not name:
                name = f"Option {i + 1}"
                row.var.set(name)

            options.append(name)

        return options

    # -------------------------------------------------
    # SAVE / LOAD
    # -------------------------------------------------

    def save_current(self):
        options = self.collect_options() if self.screen == "setup" else list(self.options)

        if len(options) < MIN_OPTIONS:
            messagebox.showerror("No Wheel", "Create your options before saving.")
            return

        path = filedialog.asksaveasfilename(
            title="Save Wheel",
            defaultextension=".json",
            initialfile="my_wheel.json",
            filetypes=[("Wheel Files", "*.json"), ("All Files", "*.*")],
        )

        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump({"options": options}, file, indent=4, ensure_ascii=False)
        except OSError as error:
            messagebox.showerror("Save Error", f"Could not save the wheel.\n\n{error}")
            return

        if self.screen == "setup":
            self._flash_status("Wheel saved.")
        else:
            self.result_hint.config(text="Wheel saved.")

    def load_wheel(self):
        path = filedialog.askopenfilename(
            title="Load Wheel",
            filetypes=[("Wheel Files", "*.json"), ("Text Files", "*.txt"), ("All Files", "*.*")],
        )

        if not path:
            return

        try:
            options = read_options_file(path)
        except (OSError, ValueError) as error:
            messagebox.showerror("Load Error", f"Could not load the wheel.\n\n{error}")
            return

        if self.screen == "wheel":
            self._start_wheel(options)
        else:
            self.set_rows(options)
            self._flash_status(f"Loaded {len(options)} options.")

    # -------------------------------------------------
    # WHEEL SCREEN
    # -------------------------------------------------

    def _build_wheel_ui(self):
        self.wheel_frame = tk.Frame(self.root, bg=BG)

        # Top bar
        bar = tk.Frame(self.wheel_frame, bg=BG)
        bar.pack(fill="x", padx=16, pady=(12, 0))
        self._button(bar, "◀  Edit Options", self.edit_options).pack(side="left")
        self._button(bar, "Load", self.load_wheel).pack(side="right")
        self._button(bar, "Save", self.save_current).pack(side="right", padx=6)

        body = tk.Frame(self.wheel_frame, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=12)

        # Wheel canvas
        self.canvas = tk.Canvas(body, bg=BG, highlightthickness=0, cursor="hand2")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Button-1>", lambda e: self.spin())

        # Side panel
        panel = tk.Frame(body, bg=PANEL, width=270)
        panel.pack(side="right", fill="y", padx=(14, 0))
        panel.pack_propagate(False)

        tk.Label(panel, text="RESULT", font=(self.font, 10, "bold"),
                 bg=PANEL, fg=MUTED).pack(pady=(18, 4))

        self.result_label = tk.Label(
            panel, text="—", font=(self.font, 22, "bold"), bg=PANEL, fg=FG,
            wraplength=240, justify="center", height=2,
        )
        self.result_label.pack(padx=14)

        self.result_hint = tk.Label(panel, text="", font=(self.font, 10),
                                    bg=PANEL, fg=MUTED, wraplength=240)
        self.result_hint.pack()

        self.spin_button = self._button(panel, "SPIN", self.spin, "Spin.Accent.TButton")
        self.spin_button.pack(fill="x", padx=18, pady=(16, 4))

        tk.Label(panel, text="Space, Enter or click the wheel", font=(self.font, 9),
                 bg=PANEL, fg=MUTED).pack()

        self.remove_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            panel, text="Remove winner after spin", variable=self.remove_var,
            command=self._on_remove_toggle,
        ).pack(padx=18, pady=(16, 8), anchor="w")

        # History
        header = tk.Frame(panel, bg=PANEL)
        header.pack(fill="x", padx=18)
        tk.Label(header, text="HISTORY", font=(self.font, 10, "bold"),
                 bg=PANEL, fg=MUTED).pack(side="left")
        clear = tk.Label(header, text="clear", font=(self.font, 10, "underline"),
                         bg=PANEL, fg=MUTED, cursor="hand2")
        clear.pack(side="right")
        clear.bind("<Button-1>", lambda e: self.history.delete(0, tk.END))

        history_box = tk.Frame(panel, bg=PANEL)
        history_box.pack(fill="both", expand=True, padx=(18, 12), pady=(4, 16))

        scrollbar = ttk.Scrollbar(history_box, orient="vertical")
        self.history = tk.Listbox(
            history_box, font=(self.font, 11), bg=ENTRY_BG, fg=FG, relief="flat",
            highlightthickness=0, activestyle="none", selectbackground=ACCENT,
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=self.history.yview)
        scrollbar.pack(side="right", fill="y")
        self.history.pack(side="left", fill="both", expand=True)

    def create_wheel(self):
        options = self.collect_options()

        if len(options) < MIN_OPTIONS:
            messagebox.showerror("No Options", f"Please enter at least {MIN_OPTIONS} options.")
            return

        self._start_wheel(options)

    def _start_wheel(self, options):
        self.options = list(options)
        self.rotation = 0.0
        self.highlight_index = None
        self.pending_removal = None
        self.spin_count = 0

        self.history.delete(0, tk.END)
        self.result_label.config(text="—", fg=FG)
        self.result_hint.config(text="")

        self.show_screen("wheel")
        self.root.update_idletasks()
        self._rebuild_wheel()
        self._refresh_spin_button()

    def edit_options(self):
        self.stop_animation()
        self.set_rows(self.options)
        self.show_screen("setup")
        self._focus_row(len(self.rows) - 1)

    def _refresh_spin_button(self):
        enabled = (not self.spinning) and len(self.options) >= MIN_OPTIONS
        self.spin_button.config(state="normal" if enabled else "disabled")

    def _on_remove_toggle(self):
        if not self.remove_var.get():
            self.pending_removal = None
            self.result_hint.config(text="")

    # -------------------------------------------------
    # DRAWING
    # -------------------------------------------------

    def _on_canvas_configure(self, event):
        size = (event.width, event.height)
        if size == self.last_canvas_size:
            return

        self.last_canvas_size = size

        if self.resize_after_id is not None:
            self.root.after_cancel(self.resize_after_id)

        self.resize_after_id = self.root.after(25, self._rebuild_wheel)

    def _rebuild_wheel(self):
        """Create all canvas items. Called on resize or when the options change.
        While spinning, only the existing items are moved (see _apply_rotation)."""
        self.resize_after_id = None
        canvas = self.canvas
        canvas.delete("all")
        self.arcs, self.texts, self.pegs = [], [], []

        width, height = canvas.winfo_width(), canvas.winfo_height()
        count = len(self.options)

        if width < 120 or height < 120 or count == 0:
            return

        radius = max(60, min((width - 24) / 2, (height - 44) / 2))
        cx = width / 2
        cy = (height + 26) / 2
        self.geometry = (cx, cy, radius)

        slice_angle = 360 / count
        self.slice_colors = build_palette(count)

        # Font sized to the slice width, text shortened to the available length
        mid_arc = 0.62 * radius * math.radians(slice_angle)
        font_px = int(max(10, min(22, mid_arc * 0.42, radius * 0.075)))
        self.wheel_font = tkfont.Font(family=self.font, size=-font_px, weight="bold")
        max_text = radius * 0.93 - radius * 0.19

        # Shadow
        canvas.create_oval(cx - radius + 5, cy - radius + 9, cx + radius + 5, cy + radius + 9,
                           fill="#0b0c12", outline="")

        box = (cx - radius, cy - radius, cx + radius, cy + radius)

        for i in range(count):
            self.arcs.append(canvas.create_arc(
                *box, start=0, extent=slice_angle, fill=self.slice_colors[i],
                outline="#ffffff", width=2,
            ))

        # Winner highlight (hidden until a spin ends)
        self.highlight_item = canvas.create_arc(
            *box, start=0, extent=slice_angle, fill="", outline=GOLD, width=6, state="hidden",
        )

        for i, name in enumerate(self.options):
            self.texts.append(canvas.create_text(
                cx, cy, text=fit_text(self.wheel_font, name, max_text),
                font=self.wheel_font, fill=readable_text_color(self.slice_colors[i]),
                anchor="e",
            ))

        # Rim and pegs
        canvas.create_oval(*box, outline="#f1e3b5", width=7)
        for _ in range(count):
            self.pegs.append(canvas.create_oval(0, 0, 0, 0, fill="#ffffff", outline="#8d7b45", width=2))

        # Hub
        hub = max(14, radius * 0.085)
        canvas.create_oval(cx - hub, cy - hub, cx + hub, cy + hub,
                           fill=PANEL, outline=GOLD, width=4)
        canvas.create_oval(cx - hub * 0.35, cy - hub * 0.35, cx + hub * 0.35, cy + hub * 0.35,
                           fill=GOLD, outline="")

        # Pointer
        self.pointer = canvas.create_polygon(
            *self._pointer_points(0), fill=GOLD, outline="#7a5c00", width=2, joinstyle="round",
        )

        self._apply_rotation()

        if self.highlight_index is not None:
            canvas.itemconfigure(self.highlight_item, state="normal")

    def _pointer_points(self, tilt_degrees):
        cx, cy, radius = self.geometry
        pivot_y = cy - radius - 26
        angle = math.radians(tilt_degrees)
        cos_a, sin_a = math.cos(angle), math.sin(angle)

        points = []
        for x, y in ((-17, 0), (17, 0), (0, 52)):
            points.extend((cx + x * cos_a - y * sin_a, pivot_y + x * sin_a + y * cos_a))

        return points

    def _apply_rotation(self):
        """Move existing items to match self.rotation (no deleting / recreating)."""
        count = len(self.arcs)
        if not count:
            return

        canvas = self.canvas
        cx, cy, radius = self.geometry
        slice_angle = 360 / count
        text_radius = radius * 0.93
        peg_r = max(3.5, radius * 0.016)

        for i in range(count):
            start = (self.rotation + i * slice_angle) % 360
            mid = math.radians(start + slice_angle / 2)

            canvas.itemconfigure(self.arcs[i], start=start)

            canvas.coords(self.texts[i],
                          cx + text_radius * math.cos(mid), cy - text_radius * math.sin(mid))
            # Keep labels upright: on the left half, flip them so they never read upside down
            flipped = math.cos(mid) < 0
            canvas.itemconfigure(
                self.texts[i],
                angle=(start + slice_angle / 2 + (180 if flipped else 0)) % 360,
                anchor="w" if flipped else "e",
            )

            edge = math.radians(start)
            px, py = cx + radius * math.cos(edge), cy - radius * math.sin(edge)
            canvas.coords(self.pegs[i], px - peg_r, py - peg_r, px + peg_r, py + peg_r)

        if self.highlight_index is not None and self.highlight_index < count:
            canvas.itemconfigure(
                self.highlight_item,
                start=(self.rotation + self.highlight_index * slice_angle) % 360,
            )

    def _index_under_pointer(self):
        count = len(self.options)
        angle = (90 - self.rotation) % 360
        return min(count - 1, int(angle // (360 / count)))

    # -------------------------------------------------
    # SPINNING
    # -------------------------------------------------

    def spin(self):
        if self.spinning or self.screen != "wheel":
            return

        # Apply "remove winner" from the previous spin
        if self.pending_removal is not None:
            if self.remove_var.get() and self.pending_removal < len(self.options):
                del self.options[self.pending_removal]
                self.highlight_index = None
                self._rebuild_wheel()
            self.pending_removal = None

        if len(self.options) < MIN_OPTIONS:
            self._refresh_spin_button()
            self.result_hint.config(text="Only one option left. Use Edit Options to start over.")
            return

        self._clear_highlight()
        self.result_hint.config(text="")
        self.spinning = True
        self._refresh_spin_button()

        count = len(self.options)
        slice_angle = 360 / count

        # Equal chance for every option; land anywhere inside the winning slice (not dead-centre)
        self.winning_index = random.randrange(count)
        landing = self.winning_index * slice_angle + slice_angle / 2
        landing += random.uniform(-0.38, 0.38) * slice_angle
        target = 90 - landing

        # Clockwise spin (rotation decreases)
        extra = (self.rotation - target) % 360
        self.spin_origin = self.rotation
        self.spin_delta = -(random.randint(*SPIN_TURNS) * 360 + extra)
        self.spin_duration = random.uniform(*SPIN_SECONDS)
        self.spin_start = time.perf_counter()
        self.last_tick_index = self._index_under_pointer()
        self.kick = 0.0

        self._tick()

    def _tick(self):
        if not self.spinning:
            return

        progress = (time.perf_counter() - self.spin_start) / self.spin_duration

        if progress >= 1:
            self.spin_after_id = None
            self._finish_spin()
            return

        eased = 1 - (1 - progress) ** 4  # fast start, long smooth slowdown
        self.rotation = self.spin_origin + self.spin_delta * eased
        self._apply_rotation()
        self._update_pointer()

        self.spin_after_id = self.root.after(FRAME_MS, self._tick)

    def _update_pointer(self):
        """Flick the pointer each time a slice boundary passes it."""
        index = self._index_under_pointer()

        if index != self.last_tick_index:
            self.last_tick_index = index
            self.kick = 1.0
        else:
            self.kick *= 0.8

        self.canvas.coords(self.pointer, *self._pointer_points(-24 * self.kick))

    def _finish_spin(self):
        self.rotation = (self.spin_origin + self.spin_delta) % 360
        self.kick = 0.0
        self.spinning = False

        self._apply_rotation()
        self.canvas.coords(self.pointer, *self._pointer_points(0))

        index = self.winning_index
        winner = self.options[index]

        self.spin_count += 1
        self.result_label.config(text=winner, fg=self.slice_colors[index])
        self.history.insert(0, f"{self.spin_count}.  {winner}")
        if self.history.size() > MAX_HISTORY:
            self.history.delete(MAX_HISTORY, tk.END)

        if self.remove_var.get():
            self.pending_removal = index
            self.result_hint.config(text="Will be removed on the next spin.")

        self._show_highlight(index)
        self._refresh_spin_button()

    def _show_highlight(self, index):
        self.highlight_index = index
        self._apply_rotation()
        self._pulse(6)

    def _pulse(self, toggles):
        """Blink the winning slice's outline a few times, ending visible."""
        if self.highlight_index is None:
            return

        visible = toggles % 2 == 0
        self.canvas.itemconfigure(self.highlight_item, state="normal" if visible else "hidden")

        if toggles > 0:
            self.pulse_after_id = self.root.after(170, lambda: self._pulse(toggles - 1))
        else:
            self.pulse_after_id = None

    def _clear_highlight(self):
        if self.pulse_after_id is not None:
            self.root.after_cancel(self.pulse_after_id)
            self.pulse_after_id = None

        self.highlight_index = None
        if self.highlight_item is not None:
            self.canvas.itemconfigure(self.highlight_item, state="hidden")


# -------------------------------------------------
# START PROGRAM
# -------------------------------------------------

def main():
    # Crisp text on high-DPI Windows displays
    if sys.platform == "win32":
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    root = tk.Tk()
    SpinWheelApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
