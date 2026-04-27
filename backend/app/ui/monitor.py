"""Tkinter live debug monitor.

Shows the latest key event and per-key session counts. Used to verify
that every Q6 HE key (modifiers, F1-F24, numpad, media, volume knob,
OEM keys on the IT layout) actually reaches the LL hook.

Privacy: this UI deliberately does NOT keep an ordered history of
events with timestamps — that would be a reconstructable sequence of
keystrokes. We only render the most recent event (no timing) plus the
aggregated per-key counts.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from app.core.config import get_settings
from app.hook.events import EventKind, KeyEvent
from app.hook.vk_codes import name as vk_name
from app.service.daemon import KeyLifeDaemon, UiEventBridge


def _fmt_event(ev: KeyEvent) -> str:
    flags = []
    if ev.extended:
        flags.append("E")
    if ev.injected:
        flags.append("I")
    flag_str = f" [{''.join(flags)}]" if flags else ""
    # No timestamp_ms in the rendered string: keeping ordered, timed events
    # would let an observer reconstruct typed sequences.
    return (
        f"{ev.kind.value:>4}  "
        f"vk=0x{ev.vk:02X}  sc=0x{ev.scancode:03X}  "
        f"{vk_name(ev.vk)}{flag_str}"
    )


class MonitorApp:
    POLL_MS = 50

    def __init__(self) -> None:
        self.settings = get_settings()
        self.bridge = UiEventBridge(maxsize=self.settings.ui_queue_max)
        self.daemon = KeyLifeDaemon(ui_listener=self.bridge.push)

        self.root = tk.Tk()
        self.root.title("KeyLife — Hook Monitor")
        self.root.geometry("780x560")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}

        # Top: last event + session totals
        top = ttk.Frame(self.root)
        top.pack(fill=tk.X, **pad)

        self.var_last = tk.StringVar(value="(no events yet — press a key)")
        ttk.Label(top, text="Last event:").pack(anchor=tk.W)
        ttk.Label(top, textvariable=self.var_last, font=("Consolas", 12, "bold")).pack(
            anchor=tk.W
        )

        self.var_total = tk.StringVar(value="Session presses: 0")
        ttk.Label(top, textvariable=self.var_total, font=("Segoe UI", 10)).pack(
            anchor=tk.W, pady=(6, 0)
        )

        # Show only the filename — the full path includes the OS username.
        self.var_db = tk.StringVar(value=f"DB: {self.settings.db_filename}")
        ttk.Label(top, textvariable=self.var_db, foreground="#666").pack(anchor=tk.W)

        # Middle: aggregated session counts (no chronological list, by design —
        # see module docstring on privacy).
        mid = ttk.Frame(self.root)
        mid.pack(fill=tk.BOTH, expand=True, **pad)
        mid.columnconfigure(0, weight=1)
        mid.rowconfigure(0, weight=1)

        right = ttk.LabelFrame(mid, text="Session counts (per vk+scancode)")
        right.grid(row=0, column=0, sticky="nsew")
        cols = ("vk", "sc", "name", "count")
        self.tbl = ttk.Treeview(right, columns=cols, show="headings", height=14)
        for c, w, anchor in (
            ("vk", 60, tk.E), ("sc", 60, tk.E),
            ("name", 180, tk.W), ("count", 70, tk.E),
        ):
            self.tbl.heading(c, text=c.upper(), command=lambda cc=c: self._sort_by(cc))
            self.tbl.column(c, width=w, anchor=anchor)
        sb_r = ttk.Scrollbar(right, orient=tk.VERTICAL, command=self.tbl.yview)
        self.tbl.configure(yscrollcommand=sb_r.set)
        self.tbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_r.pack(side=tk.RIGHT, fill=tk.Y)

        # Bottom: status + controls
        bot = ttk.Frame(self.root)
        bot.pack(fill=tk.X, **pad)
        self.var_status = tk.StringVar(value="starting…")
        ttk.Label(bot, textvariable=self.var_status, foreground="#0a0").pack(side=tk.LEFT)
        ttk.Button(bot, text="Flush now", command=self._flush_now).pack(side=tk.RIGHT)

        self._sort_state: tuple[str, bool] = ("count", True)

    # ----- lifecycle -----
    def run(self) -> None:
        self.daemon.start()
        self.var_status.set("hook active — listening")
        self.root.after(self.POLL_MS, self._tick)
        self.root.mainloop()

    def _on_close(self) -> None:
        self.var_status.set("stopping…")
        try:
            self.daemon.stop()
        finally:
            self.root.destroy()

    def _flush_now(self) -> None:
        self.daemon._flush_once()  # noqa: SLF001 — debug action

    # ----- UI tick -----
    def _tick(self) -> None:
        events = self.bridge.drain(limit=128)
        if events:
            # Only keep the *latest* DOWN for display — never a sequence.
            for ev in events:
                if ev.kind is EventKind.DOWN:
                    self.var_last.set(_fmt_event(ev))
            self._refresh_table()
        self.root.after(self.POLL_MS, self._tick)

    def _refresh_table(self) -> None:
        total, per_key = self.daemon.aggregator.session_view()
        self.var_total.set(f"Session presses: {total}")

        col, reverse = self._sort_state
        rows = [
            (vk, sc, vk_name(vk), cnt)
            for (vk, sc), cnt in per_key.items()
        ]
        idx = {"vk": 0, "sc": 1, "name": 2, "count": 3}[col]
        rows.sort(key=lambda r: r[idx], reverse=reverse)

        self.tbl.delete(*self.tbl.get_children())
        for vk, sc, nm, cnt in rows:
            self.tbl.insert(
                "", tk.END,
                values=(f"0x{vk:02X}", f"0x{sc:03X}", nm, cnt),
            )

    def _sort_by(self, col: str) -> None:
        cur_col, cur_rev = self._sort_state
        self._sort_state = (col, not cur_rev if cur_col == col else (col == "count"))
        self._refresh_table()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    )
    MonitorApp().run()


if __name__ == "__main__":
    main()
