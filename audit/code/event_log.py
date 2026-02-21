# event_log.py — Event model, log writing/reading, listener bus

import json
import threading
from datetime import datetime
from config import LOG_FILE

_log_lock  = threading.Lock()
_listeners = []   # callables notified on every new event


#Event factory
def make_event(etype, message, severity="INFO", user="", pid=0, process="", path=""):
    return {
        "ts":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type":     etype,
        "severity": severity,
        "user":     user,
        "pid":      pid,
        "process":  process,
        "path":     path,
        "message":  message,
    }


#Write
def log_event(ev: dict):
    with _log_lock:
        # Rotate at 5 MB
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 5 * 1024 * 1024:
            LOG_FILE.replace(LOG_FILE.with_suffix(".jsonl.1"))
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev) + "\n")
    for cb in _listeners:
        try:
            cb(ev)
        except Exception:
            pass


#Read
def read_events(limit=10_000):
    events = []
    for path in [LOG_FILE.with_suffix(".jsonl.1"), LOG_FILE]:
        if path.exists():
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                events.append(json.loads(line))
                            except Exception:
                                pass
            except Exception:
                pass
    return events[-limit:]


#Listener bus
def add_listener(cb):    _listeners.append(cb)
def remove_listener(cb):
    if cb in _listeners: _listeners.remove(cb)