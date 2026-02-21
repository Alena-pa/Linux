# gui.py — SysAudit GUI with Telegram notifications

import json
import re
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from datetime import datetime, timedelta

from config import EMAIL_CFG_FILE
from event_log import add_listener, make_event, read_events, remove_listener
from monitors import AuditEngine
from notifier import TelegramNotifier
from report import Reporter


def _load_chat_id() -> str:
    try:
        if EMAIL_CFG_FILE.exists():
            return json.loads(EMAIL_CFG_FILE.read_text(encoding="utf-8")).get("chat_id", "")
    except Exception:
        pass
    return ""

def _save_chat_id(chat_id: str):
    EMAIL_CFG_FILE.write_text(
        json.dumps({"chat_id": chat_id}, indent=2), encoding="utf-8"
    )


class _LoggerAdapter:
    def query(self, sql, params):       return read_events()
    def query_period(self, start, end): return [e for e in read_events() if start <= e.get("ts","") <= end]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SysAudit")
        self.geometry("860x540")

        self.engine   = AuditEngine()
        self.reporter = Reporter(_LoggerAdapter())
        self.notifier = None
        self._buf     = []
        self._lock    = threading.Lock()

        self._build()
        add_listener(self._on_event)

        # Auto-restore saved chat_id
        saved = _load_chat_id()
        if saved:
            self._chat_var.set(saved)
            self._apply_notifier(saved, silent=True)

        self._tick()

    #Layout

    def _build(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        log_frame = tk.Frame(nb)
        nb.add(log_frame, text="  Events  ")
        self._build_log_tab(log_frame)

        cfg_frame = tk.Frame(nb)
        nb.add(cfg_frame, text="  Notifications  ")
        self._build_cfg_tab(cfg_frame)

    #Tab 1: Events

    def _build_log_tab(self, parent):
        btn = tk.Frame(parent)
        btn.pack(fill="x", padx=8, pady=6)

        self._status = tk.Label(btn, text="[STOPPED]", width=10)
        self._status.pack(side="left", padx=(0, 8))

        for text, cmd, w in [("Start", self._start, 8), ("Stop", self._stop, 8),
                              ("Clear", self._clear, 8), ("Report", self._report, 8)]:
            tk.Button(btn, text=text, command=cmd, width=w).pack(side="left", padx=2)

        self._notifier_lbl = tk.Label(btn, text="🔔 off", fg="gray")
        self._notifier_lbl.pack(side="right", padx=8)

        f = tk.Frame(parent)
        f.pack(fill="x", padx=8, pady=(0, 4))
        tk.Label(f, text="Filter:").pack(side="left")
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", lambda *_: self._apply_filter())
        tk.Entry(f, textvariable=self._filter_var, width=40).pack(side="left", padx=4)

        self._log = scrolledtext.ScrolledText(parent, font=("Courier", 12), state="disabled")
        self._log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._all_events = list(reversed(read_events(1000)))
        self._apply_filter()

    #Tab 2: Notifications

    def _build_cfg_tab(self, parent):
        wrap = tk.Frame(parent)
        wrap.pack(anchor="nw", padx=30, pady=30)

        # Instruction
        tk.Label(wrap, text="Telegram notifications", font=("", 13, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        help_text = (
            "How to get your Chat ID:\n"
            "  1. Open Telegram → search @userinfobot\n"
            "  2. Press Start — it replies with your ID\n"
            "  3. Paste it below and click Save"
        )
        tk.Label(wrap, text=help_text, justify="left", fg="#555").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 16))

        # Single input
        tk.Label(wrap, text="Your Chat ID:", width=16, anchor="e").grid(
            row=2, column=0, sticky="e", padx=(0, 8))
        self._chat_var = tk.StringVar()
        tk.Entry(wrap, textvariable=self._chat_var, width=24,
                 font=("Courier", 12)).grid(row=2, column=1, sticky="w")

        # Buttons
        btn_row = tk.Frame(wrap)
        btn_row.grid(row=3, column=0, columnspan=2, sticky="w", pady=12)
        tk.Button(btn_row, text="Save", width=10,
                  command=self._save_cfg).pack(side="left", padx=(0, 8))
        tk.Button(btn_row, text="Test", width=10,
                  command=self._test_notify).pack(side="left")

        self._cfg_status = tk.Label(wrap, text="", fg="gray")
        self._cfg_status.grid(row=4, column=0, columnspan=2, sticky="w")

    #Notifier helpers

    def _save_cfg(self):
        chat_id = self._chat_var.get().strip()
        if not chat_id:
            messagebox.showerror("Error", "Please enter your Chat ID.")
            return
        _save_chat_id(chat_id)
        self._apply_notifier(chat_id)

    def _apply_notifier(self, chat_id: str, silent=False):
        if self.notifier:
            self.notifier.stop()
        self.notifier = TelegramNotifier(chat_id)
        self.notifier.start()
        self._notifier_lbl.config(text="🔔 on", fg="green")
        if not silent:
            self._cfg_status.config(text="✓ Saved. Notifications active.", fg="green")

    def _test_notify(self):
        chat_id = self._chat_var.get().strip()
        if not chat_id:
            messagebox.showerror("Error", "Please enter your Chat ID.")
            return
        self._cfg_status.config(text="Sending…", fg="gray")
        self.update_idletasks()

        ev = make_event("TEST", "Test notification from SysAudit 🎉", severity="CRITICAL")

        def _send():
            try:
                n = TelegramNotifier(chat_id)
                n._send(n._format(ev))
                self.after(0, lambda: self._cfg_status.config(
                    text="✓ Message sent! Check Telegram.", fg="green"))
            except Exception as exc:
                self.after(0, lambda e=exc: self._cfg_status.config(
                    text=f"✗ Error: {e}", fg="red"))

        threading.Thread(target=_send, daemon=True).start()

    #Event log helpers

    def _apply_filter(self):
        kw = self._filter_var.get().strip().lower()
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        for ev in self._all_events:
            line = (f"[{ev['ts']}] {ev.get('severity',''):<8} "
                    f"{ev.get('type',''):<20} {ev.get('message','')}\n")
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
        win   = tk.Toplevel(self)
        win.title("Report")
        win.geometry("480x360")
        box = scrolledtext.ScrolledText(win, font=("Courier", 12))
        box.pack(fill="both", expand=True, padx=8, pady=8)
        box.insert("end", text)
        box.config(state="disabled")

    def destroy(self):
        self.engine.stop()
        if self.notifier:
            self.notifier.stop()
        remove_listener(self._on_event)
        super().destroy()