# gui.py — Minimal GUI for SysAudit

import re
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime, timedelta

from event_log import add_listener, read_events, remove_listener
from monitors import AuditEngine
from report import Reporter


class _LoggerAdapter:
    def query(self, sql, params):
        return read_events()
    def query_period(self, start, end):
        return [e for e in read_events() if start <= e.get("ts", "") <= end]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SysAudit")
        self.geometry("800x500")

        self.engine   = AuditEngine()
        self.reporter = Reporter(_LoggerAdapter())
        self._buf     = []
        self._lock    = threading.Lock()

        self._build()
        add_listener(self._on_event)
        self._tick()

    def _build(self):
        # Buttons
        btn_frame = tk.Frame(self)
        btn_frame.pack(fill="x", padx=8, pady=6)

        self._status = tk.Label(btn_frame, text="[STOPPED]", width=10)
        self._status.pack(side="left", padx=(0, 8))

        tk.Button(btn_frame, text="Start",  command=self._start,  width=8).pack(side="left", padx=2)
        tk.Button(btn_frame, text="Stop",   command=self._stop,   width=8).pack(side="left", padx=2)
        tk.Button(btn_frame, text="Clear",  command=self._clear,  width=8).pack(side="left", padx=2)
        tk.Button(btn_frame, text="Report", command=self._report, width=8).pack(side="left", padx=2)

        # Filter
        filter_frame = tk.Frame(self)
        filter_frame.pack(fill="x", padx=8, pady=(0, 4))

        tk.Label(filter_frame, text="Filter:").pack(side="left")
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", lambda *_: self._apply_filter())
        tk.Entry(filter_frame, textvariable=self._filter_var, width=40).pack(side="left", padx=4)

        # Event log (plain text box)
        self._log = scrolledtext.ScrolledText(self, font=("Courier", 12), state="disabled")
        self._log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._load_events()

    def _load_events(self):
        self._all_events = list(reversed(read_events(1000)))
        self._apply_filter()

    def _apply_filter(self):
        kw = self._filter_var.get().strip().lower()
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        for ev in self._all_events:
            line = f"[{ev['ts']}] {ev.get('severity',''):<8} {ev.get('type',''):<20} {ev.get('message','')}\n"
            if kw and kw not in line.lower():
                continue
            self._log.insert("end", line)
        self._log.config(state="disabled")
        self._log.see("end")

    def _on_event(self, ev):
        with self._lock:
            self._buf.append(ev)

    def _tick(self):
        with self._lock:
            buf, self._buf = self._buf[:], []
        if buf:
            for ev in buf:
                self._all_events.insert(0, ev)
            self._all_events = self._all_events[:1000]
            self._apply_filter()
        self.after(1000, self._tick)

    def _start(self):
        self.engine.start()
        self._status.config(text="[RUNNING]")

    def _stop(self):
        self.engine.stop()
        self._status.config(text="[STOPPED]")

    def _clear(self):
        self._all_events = []
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")

    def _report(self):
        start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")
        end   = datetime.now().strftime("%Y-%m-%d 23:59:59")
        text  = self.reporter.build_text_report(start, end)
        text  = re.sub(r"</?b>", "", text)

        win = tk.Toplevel(self)
        win.title("Report")
        win.geometry("480x360")
        box = scrolledtext.ScrolledText(win, font=("Courier", 12))
        box.pack(fill="both", expand=True, padx=8, pady=8)
        box.insert("end", text)
        box.config(state="disabled")

    def destroy(self):
        self.engine.stop()
        remove_listener(self._on_event)
        super().destroy()