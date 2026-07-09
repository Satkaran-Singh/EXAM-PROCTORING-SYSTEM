"""
EventLogger
-----------
Handles all record-keeping for a proctoring session:
  - Timestamped event log (CSV)
  - Screenshot capture on violation
  - End-of-session summary report

This is what turns raw detections into evidence an examiner can review.
"""

import os
import csv
import time
from datetime import datetime

import cv2


class EventLogger:
    def __init__(self, log_dir: str, screenshot_dir: str, report_name: str,
                 candidate_id: str = "candidate_01", on_event=None):
        self.log_dir = log_dir
        self.screenshot_dir = screenshot_dir
        self.candidate_id = candidate_id
        self.on_event = on_event  # optional callback(event_type, severity, details, timestamp)

        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.screenshot_dir, exist_ok=True)

        session_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_id = f"{candidate_id}_{session_stamp}"
        self.log_path = os.path.join(self.log_dir, f"{self.session_id}_events.csv")
        self.report_path = os.path.join(self.log_dir, f"{self.session_id}_{report_name}")

        self._last_alert_time = {}   # event_type -> last timestamp, for cooldown
        self._event_counts = {}      # event_type -> count
        self.session_start = time.time()

        # Initialize CSV with header
        with open(self.log_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "elapsed_seconds", "event_type",
                              "severity", "details", "screenshot"])

    def can_alert(self, event_type: str, cooldown_seconds: float) -> bool:
        """Rate-limit repeated alerts of the same type so the log stays readable."""
        now = time.time()
        last = self._last_alert_time.get(event_type, 0)
        if now - last >= cooldown_seconds:
            self._last_alert_time[event_type] = now
            return True
        return False

    def log_event(self, event_type: str, severity: str, details: str,
                  frame=None, save_screenshot: bool = True):
        """
        Record a violation/event.
        severity: "LOW" | "MEDIUM" | "HIGH"
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elapsed = round(time.time() - self.session_start, 1)

        screenshot_name = ""
        if save_screenshot and frame is not None:
            screenshot_name = f"{self.session_id}_{event_type}_{int(time.time()*1000)}.jpg"
            screenshot_path = os.path.join(self.screenshot_dir, screenshot_name)
            cv2.imwrite(screenshot_path, frame)

        with open(self.log_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, elapsed, event_type, severity, details, screenshot_name])

        self._event_counts[event_type] = self._event_counts.get(event_type, 0) + 1
        print(f"[{severity}] {timestamp} | {event_type}: {details}")

        if self.on_event:
            try:
                self.on_event(event_type, severity, details, timestamp)
            except Exception as e:
                print(f"on_event callback error: {e}")

    def get_summary_data(self):
        """Structured session stats -- used by generate_report() and by the
        GUI to build a detailed report view (table, etc.) without re-parsing text."""
        duration = round(time.time() - self.session_start, 1)
        total_events = sum(self._event_counts.values())

        score = 100
        weights = {
            "NO_FACE": 5, "MULTIPLE_FACES": 10, "LOOKING_AWAY": 3,
            "GAZE_OFF_SCREEN": 3, "SUSPICIOUS_OBJECT": 15
        }
        for event_type, count in self._event_counts.items():
            score -= weights.get(event_type, 5) * count
        score = max(score, 0)

        return {
            "candidate_id": self.candidate_id,
            "session_id": self.session_id,
            "duration_seconds": duration,
            "total_events": total_events,
            "event_counts": dict(sorted(self._event_counts.items())),
            "score": score,
            "log_path": self.log_path,
            "screenshot_dir": self.screenshot_dir,
        }

    def generate_report(self):
        """Write a human-readable summary at the end of the session.
        Returns (report_text, score, summary_data)."""
        data = self.get_summary_data()

        lines = [
            "=" * 55,
            "AI PROCTORING SESSION REPORT",
            "=" * 55,
            f"Candidate ID     : {data['candidate_id']}",
            f"Session ID       : {data['session_id']}",
            f"Duration         : {data['duration_seconds']} seconds",
            f"Total Violations : {data['total_events']}",
            "-" * 55,
            "Breakdown by type:",
        ]
        if data["event_counts"]:
            for event_type, count in data["event_counts"].items():
                lines.append(f"  - {event_type:<20}: {count}")
        else:
            lines.append("  (none -- clean session)")
        lines += [
            "-" * 55,
            f"Integrity Score  : {data['score']}/100",
            "  (100 = clean session, lower = more/severe flags)",
            "=" * 55,
            f"Detailed event log : {data['log_path']}",
            f"Screenshots folder : {data['screenshot_dir']}",
        ]

        report_text = "\n".join(lines)
        with open(self.report_path.replace(".csv", ".txt"), "w") as f:
            f.write(report_text)

        print("\n" + report_text)
        return report_text, data["score"], data
