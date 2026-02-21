# report.py — Reporter class using matplotlib and pandas

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from io import BytesIO
from datetime import datetime

CRITICAL_TYPES = {
    "proc:EXEC",
    "file_deleted",
    "priv_escalation",
    "audit_violation",
    "critical",
}


class Reporter:
    def __init__(self, logger):
        self.logger = logger

    def basic_stats(self):
        rows = self.logger.query('', ())
        df = pd.DataFrame(rows)
        if df.empty:
            return None
        return df['type'].value_counts()

    def plot_event_counts(self):
        counts = self.basic_stats()
        if counts is None:
            return None
        fig = plt.figure()
        counts.plot(kind='bar')
        buf = BytesIO()
        fig.savefig(buf, format='png')
        buf.seek(0)
        plt.close(fig)
        return buf

    def get_period_stats(self, start, end):
        rows = self.logger.query_period(start, end)
        df = pd.DataFrame(rows)
        if df.empty:
            return None, None
        # Statistics by event type
        type_stats = df['type'].value_counts()
        # Filter critical/important events
        if "type" in df.columns:
            important = df[df["type"].isin(CRITICAL_TYPES)]
        else:
            important = pd.DataFrame()
        return type_stats, important

    def build_text_report(self, start, end):
        # Normalize start/end to ISO strings
        if hasattr(start, "isoformat"):
            start_str = start.isoformat() + "Z"
        else:
            start_str = str(start)
        if hasattr(end, "isoformat"):
            end_str = end.isoformat() + "Z"
        else:
            end_str = str(end)

        # Fetch events for the period
        events = self.logger.query_period(start_str, end_str)
        total = len(events)
        important = [e for e in events if e["type"] in ("critical", "error")]
        imp_count = len(important)

        # Count by type
        counts = {}
        for e in events:
            t = e["type"]
            counts[t] = counts.get(t, 0) + 1

        # Build report text
        lines = []
        lines.append(f"<b>Report for period:</b>\n{start_str} → {end_str}\n\n")
        lines.append(f"<b>Total events:</b> {total}\n")
        lines.append(f"<b>Important events:</b> {imp_count}\n\n")
        lines.append("<b>STATISTICS BY TYPE:</b>\n")
        for k, v in sorted(counts.items(), key=lambda x: -x[1]):
            lines.append(f" * {k} — {v}\n")
        lines.append("\n")
        if imp_count == 0:
            lines.append("<b>No critical events detected in this period.</b>\n")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"\n<b>Report generated:</b> {now}")
        return "".join(lines)

    def plot_period(self, start, end):
        rows = self.logger.query_period(start, end)
        df = pd.DataFrame(rows)
        if df.empty:
            return None
        fig = plt.figure()
        df['type'].value_counts().plot(kind="bar")
        buf = BytesIO()
        fig.savefig(buf, format='png')
        buf.seek(0)
        plt.close(fig)
        return buf