# monitors.py — Process, File, and Network monitors + AuditEngine

import threading
from pathlib import Path

try:
    import psutil
except ImportError:
    print("ERROR: Run 'pip install psutil' first.")
    raise SystemExit(1)

from config import SENSITIVE_PATHS, SENSITIVE_PORTS
from event_log import log_event, make_event


#Process monitor
class ProcessMonitor(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="ProcMon")
        self._stop  = threading.Event()
        self._known = {}

    def stop(self): self._stop.set()

    def run(self):
        self._known = {p.pid: p.info["name"]
                       for p in psutil.process_iter(["pid", "name"])}
        while not self._stop.wait(3):
            current = {}
            for p in psutil.process_iter(["pid", "name", "username"]):
                try:
                    current[p.pid] = (p.info["name"] or "", p.info.get("username") or "")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            for pid, (name, user) in current.items():
                if pid not in self._known:
                    log_event(make_event("PROCESS_START",
                        f"Process started: {name} (pid {pid})",
                        user=user, pid=pid, process=name))

            for pid, name in self._known.items():
                if pid not in current:
                    log_event(make_event("PROCESS_END",
                        f"Process ended: {name} (pid {pid})",
                        pid=pid, process=name))

            self._known = {pid: name for pid, (name, _) in current.items()}


#File monitor
class FileMonitor(threading.Thread):
    def __init__(self, paths):
        super().__init__(daemon=True, name="FileMon")
        self._stop   = threading.Event()
        self._paths  = [Path(p) for p in paths if Path(p).exists()]
        self._mtimes = {}

    def stop(self): self._stop.set()

    def run(self):
        self._scan(initial=True)
        while not self._stop.wait(5):
            self._scan()

    def _scan(self, initial=False):
        for base in self._paths:
            try:
                items = base.rglob("*") if base.is_dir() else [base]
                for fp in items:
                    if not fp.is_file():
                        continue
                    key = str(fp)
                    try:
                        mtime = fp.stat().st_mtime
                    except OSError:
                        continue
                    if not initial and key in self._mtimes and mtime != self._mtimes[key]:
                        sev = ("CRITICAL" if any(key.startswith(s) for s in SENSITIVE_PATHS)
                               else "WARNING" if "/etc" in key else "INFO")
                        log_event(make_event("FILE_MODIFY",
                            f"File modified: {key}", severity=sev, path=key))
                    self._mtimes[key] = mtime
            except PermissionError:
                pass


#Network monitor
class NetworkMonitor(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="NetMon")
        self._stop  = threading.Event()
        self._known = set()

    def stop(self): self._stop.set()

    def run(self):
        self._known = self._snap()
        while not self._stop.wait(4):
            current = self._snap()
            for key in current - self._known:
                laddr, raddr, status, pid = key
                sev = ("WARNING" if any(f":{p}" in str(raddr)
                                        for p in SENSITIVE_PORTS) else "INFO")
                pname = ""
                try:
                    pname = psutil.Process(pid).name()
                except Exception:
                    pass
                log_event(make_event("NETWORK",
                    f"Connection: {laddr} → {raddr} [{status}]",
                    severity=sev, pid=pid, process=pname))
            self._known = current

    def _snap(self):
        result = set()
        try:
            for c in psutil.net_connections(kind="inet"):
                if c.laddr:
                    la = f"{c.laddr.ip}:{c.laddr.port}"
                    ra = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else ""
                    result.add((la, ra, c.status, c.pid or 0))
        except psutil.AccessDenied:
            pass
        return result


#Engine (starts/stops all monitors)
class AuditEngine:
    def __init__(self, watch_paths=None):
        self.watch_paths = watch_paths or ["/etc", str(Path.home())]
        self._threads    = []
        self.running     = False

    def start(self):
        if self.running:
            return
        self.running  = True
        self._threads = [
            ProcessMonitor(),
            FileMonitor(self.watch_paths),
            NetworkMonitor(),
        ]
        for t in self._threads:
            t.start()
        log_event(make_event("SYSTEM", "Audit engine started"))

    def stop(self):
        if not self.running:
            return
        self.running = False
        for t in self._threads:
            t.stop()
        log_event(make_event("SYSTEM", "Audit engine stopped"))