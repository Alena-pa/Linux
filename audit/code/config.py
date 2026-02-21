# config.py — Shared constants and settings

from pathlib import Path

LOG_FILE = Path.home() / ".sysaudit_events.jsonl"

SENSITIVE_PORTS = {22, 23, 3389, 5900, 4444}
SENSITIVE_PATHS = ["/etc/passwd", "/etc/shadow", "/etc/sudoers"]

# ── UI colours ────────────────────────────────
BG, SURFACE, TEXT = "#0d1117", "#161b22", "#e6edf3"
MUTED, BORDER     = "#8b949e", "#30363d"
GREEN, BLUE, ORANGE, RED = "#3fb950", "#58a6ff", "#ffa657", "#ff7b72"
SEV_COLOR = {"INFO": BLUE, "WARNING": ORANGE, "CRITICAL": RED}