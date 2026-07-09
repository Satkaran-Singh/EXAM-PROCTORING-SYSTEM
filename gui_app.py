"""
AI-Powered Exam Proctoring System -- Desktop GUI
==================================================
A Tkinter frontend around the same detection pipeline used by main.py
(shared via modules/session.py). Replaces the raw OpenCV preview window
with a full dashboard:
  - Live annotated video feed
  - Real-time status cards (faces, head pose, gaze, objects)
  - A tabbed panel: "Alerts" (violations only) and "Activity Log"
    (a continuous feed of everything the system observes, not just flags)
  - A detailed end-of-session report with a per-category breakdown table

Run:
    python gui_app.py
"""

import time
import tkinter as tk
from tkinter import ttk, messagebox

import cv2
from PIL import Image, ImageTk

import config
from modules.session import ProctoringSession

# ---- Color palette (dark theme) ----
BG_DARK = "#1e1e2e"
BG_PANEL = "#282838"
BG_CARD = "#323244"
FG_TEXT = "#e4e4ef"
FG_MUTED = "#9a9ab0"
ACCENT = "#7c8cff"
COLOR_OK = "#3ecf8e"
COLOR_ALERT = "#ff5c7c"
COLOR_WARN = "#ffb454"
COLOR_NEUTRAL = "#8a8aa0"

SEVERITY_COLORS = {"HIGH": "#ff5c7c", "MEDIUM": "#ffb454", "LOW": "#e5c07b"}

ACTIVITY_SNAPSHOT_INTERVAL = 2.0  # seconds between routine (non-violation) log entries


class StatusCard(tk.Frame):
    """A small labeled status tile, e.g. 'Faces: 1' with a color that
    shifts between OK/alert states."""

    def __init__(self, parent, title):
        super().__init__(parent, bg=BG_CARD, padx=12, pady=8)
        self.title_label = tk.Label(self, text=title, bg=BG_CARD, fg=FG_MUTED,
                                     font=("Segoe UI", 9))
        self.title_label.pack(anchor="w")
        self.value_label = tk.Label(self, text="--", bg=BG_CARD, fg=FG_TEXT,
                                     font=("Segoe UI", 14, "bold"))
        self.value_label.pack(anchor="w")

    def update_value(self, text, ok=True):
        self.value_label.config(text=text, fg=COLOR_OK if ok else COLOR_ALERT)


class ProctoringGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Exam Proctoring System")
        self.root.geometry("1250x720")
        self.root.configure(bg=BG_DARK)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.cap = None
        self.session = None
        self.running = False
        self.start_time = None
        self.total_violations = 0
        self.last_activity_snapshot = 0.0

        self._build_layout()

    # ---------------------------------------------------------------- UI
    def _build_layout(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Accent.TButton", background=ACCENT, foreground="white",
                         font=("Segoe UI", 10, "bold"), padding=8)
        style.map("Accent.TButton", background=[("active", "#6572e0")])
        style.configure("Dark.TEntry", fieldbackground=BG_CARD, foreground=FG_TEXT)

        style.configure("Dark.TNotebook", background=BG_DARK, borderwidth=0)
        style.configure("Dark.TNotebook.Tab", background=BG_PANEL, foreground=FG_MUTED,
                         padding=(14, 6), font=("Segoe UI", 9, "bold"))
        style.map("Dark.TNotebook.Tab",
                  background=[("selected", BG_CARD)],
                  foreground=[("selected", FG_TEXT)])

        style.configure("Report.Treeview", background=BG_PANEL, fieldbackground=BG_PANEL,
                         foreground=FG_TEXT, rowheight=26, borderwidth=0,
                         font=("Segoe UI", 10))
        style.configure("Report.Treeview.Heading", background=BG_CARD, foreground=FG_TEXT,
                         font=("Segoe UI", 10, "bold"))

        # ---- Top bar ----
        top_bar = tk.Frame(self.root, bg=BG_PANEL, height=64)
        top_bar.pack(side="top", fill="x")
        top_bar.pack_propagate(False)

        tk.Label(top_bar, text="AI Exam Proctoring System", bg=BG_PANEL, fg=FG_TEXT,
                 font=("Segoe UI", 15, "bold")).pack(side="left", padx=20)

        control_frame = tk.Frame(top_bar, bg=BG_PANEL)
        control_frame.pack(side="right", padx=20)

        tk.Label(control_frame, text="Candidate ID:", bg=BG_PANEL, fg=FG_MUTED,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
        self.candidate_entry = ttk.Entry(control_frame, width=16, style="Dark.TEntry")
        self.candidate_entry.insert(0, "candidate_01")
        self.candidate_entry.pack(side="left", padx=(0, 12))

        self.status_dot = tk.Label(control_frame, text="\u25cf", bg=BG_PANEL,
                                    fg=COLOR_NEUTRAL, font=("Segoe UI", 12))
        self.status_dot.pack(side="left", padx=(0, 4))
        self.status_text = tk.Label(control_frame, text="Idle", bg=BG_PANEL,
                                     fg=FG_MUTED, font=("Segoe UI", 9), width=8, anchor="w")
        self.status_text.pack(side="left", padx=(0, 12))

        self.timer_label = tk.Label(control_frame, text="00:00", bg=BG_PANEL,
                                     fg=FG_MUTED, font=("Segoe UI", 10), width=6)
        self.timer_label.pack(side="left", padx=(0, 12))

        self.start_btn = ttk.Button(control_frame, text="Start Session",
                                     style="Accent.TButton", command=self._toggle_session)
        self.start_btn.pack(side="left")

        # ---- Body ----
        body = tk.Frame(self.root, bg=BG_DARK)
        body.pack(fill="both", expand=True, padx=12, pady=12)

        # Left: video
        video_frame = tk.Frame(body, bg="black")
        video_frame.pack(side="left", fill="both", expand=True, padx=(0, 12))
        self.video_label = tk.Label(video_frame, bg="black",
                                     text="Press 'Start Session' to begin",
                                     fg=FG_MUTED, font=("Segoe UI", 12))
        self.video_label.pack(fill="both", expand=True)

        # Right: sidebar
        sidebar = tk.Frame(body, bg=BG_DARK, width=380)
        sidebar.pack(side="right", fill="y")
        sidebar.pack_propagate(False)

        # Status cards grid
        cards_frame = tk.Frame(sidebar, bg=BG_DARK)
        cards_frame.pack(fill="x", pady=(0, 10))
        cards_frame.columnconfigure((0, 1), weight=1)

        self.card_faces = StatusCard(cards_frame, "FACES DETECTED")
        self.card_faces.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=4)
        self.card_pose = StatusCard(cards_frame, "HEAD POSE (Yaw/Pitch)")
        self.card_pose.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=4)
        self.card_gaze = StatusCard(cards_frame, "GAZE RATIO")
        self.card_gaze.grid(row=1, column=0, sticky="nsew", padx=(0, 4), pady=4)
        self.card_objects = StatusCard(cards_frame, "OBJECTS DETECTED")
        self.card_objects.grid(row=1, column=1, sticky="nsew", padx=(4, 0), pady=4)

        # Violation counter
        counter_frame = tk.Frame(sidebar, bg=BG_CARD, pady=10)
        counter_frame.pack(fill="x", pady=(0, 10))
        tk.Label(counter_frame, text="TOTAL VIOLATIONS THIS SESSION", bg=BG_CARD,
                 fg=FG_MUTED, font=("Segoe UI", 9)).pack()
        self.violation_count_label = tk.Label(counter_frame, text="0", bg=BG_CARD,
                                               fg=FG_TEXT, font=("Segoe UI", 22, "bold"))
        self.violation_count_label.pack()

        # ---- Tabbed log panel: Alerts vs full Activity feed ----
        notebook = ttk.Notebook(sidebar, style="Dark.TNotebook")
        notebook.pack(fill="both", expand=True)

        alerts_tab = tk.Frame(notebook, bg=BG_PANEL)
        activity_tab = tk.Frame(notebook, bg=BG_PANEL)
        notebook.add(alerts_tab, text="Alerts")
        notebook.add(activity_tab, text="Full Activity Log")

        self.alert_listbox = self._make_listbox(alerts_tab)
        self.activity_listbox = self._make_listbox(activity_tab)

    def _make_listbox(self, parent):
        scrollbar = tk.Scrollbar(parent)
        scrollbar.pack(side="right", fill="y")
        listbox = tk.Listbox(
            parent, bg=BG_PANEL, fg=FG_TEXT, bd=0, highlightthickness=0,
            font=("Consolas", 9), yscrollcommand=scrollbar.set, selectmode="none"
        )
        listbox.pack(fill="both", expand=True, padx=6, pady=6)
        scrollbar.config(command=listbox.yview)
        return listbox

    # ------------------------------------------------------------ Session
    def _toggle_session(self):
        if self.running:
            self._stop_session()
        else:
            self._start_session()

    def _start_session(self):
        candidate_id = self.candidate_entry.get().strip() or "candidate_01"

        self.cap = cv2.VideoCapture(config.CAMERA_INDEX)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)

        if not self.cap.isOpened():
            messagebox.showerror("Camera Error",
                                  "Could not open webcam. Check CAMERA_INDEX in config.py.")
            self.cap = None
            return

        self.session = ProctoringSession(candidate_id, on_event=self._on_violation)
        self.running = True
        self.start_time = time.time()
        self.last_activity_snapshot = 0.0
        self.total_violations = 0
        self.violation_count_label.config(text="0")
        self.alert_listbox.delete(0, tk.END)
        self.activity_listbox.delete(0, tk.END)

        self.candidate_entry.config(state="disabled")
        self.start_btn.config(text="End Session")
        self.status_dot.config(fg=COLOR_OK)
        self.status_text.config(text="Recording", fg=COLOR_OK)

        self._log_activity(f"Session started for candidate '{candidate_id}'.", COLOR_OK)

        self._update_frame()
        self._update_timer()

    def _stop_session(self):
        self.running = False
        if self.cap:
            self.cap.release()
            self.cap = None

        report_text, score, summary = ("", None, None)
        if self.session:
            report_text, score, summary = self.session.close()
            self.session = None

        self.candidate_entry.config(state="normal")
        self.start_btn.config(text="Start Session")
        self.status_dot.config(fg=COLOR_NEUTRAL)
        self.status_text.config(text="Idle", fg=FG_MUTED)
        self.video_label.config(image="", text="Session ended.", fg=FG_MUTED)
        self.video_label.image = None

        if summary:
            self._log_activity("Session ended. Report generated.", COLOR_WARN)
            self._show_summary(report_text, score, summary)

    def _on_close(self):
        if self.running:
            self._stop_session()
        self.root.destroy()

    # -------------------------------------------------------------- Loop
    def _update_frame(self):
        if not self.running or self.cap is None:
            return

        ret, frame = self.cap.read()
        if not ret:
            self._stop_session()
            return

        frame, status = self.session.process_frame(frame)
        self._update_sidebar(status)
        self._maybe_log_activity_snapshot(status)

        # Convert BGR (OpenCV) -> RGB (PIL/Tkinter) and fit to label size
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)

        label_w = self.video_label.winfo_width() or config.FRAME_WIDTH
        label_h = self.video_label.winfo_height() or config.FRAME_HEIGHT
        img.thumbnail((label_w, label_h))

        imgtk = ImageTk.PhotoImage(image=img)
        self.video_label.imgtk = imgtk  # keep a reference, else it gets GC'd
        self.video_label.config(image=imgtk, text="")

        self.root.after(15, self._update_frame)

    def _update_timer(self):
        if not self.running:
            return
        elapsed = int(time.time() - self.start_time)
        mins, secs = divmod(elapsed, 60)
        self.timer_label.config(text=f"{mins:02d}:{secs:02d}")
        self.root.after(1000, self._update_timer)

    # ------------------------------------------------------------ Widgets
    def _update_sidebar(self, status):
        face_count = status["face_count"]
        self.card_faces.update_value(str(face_count), ok=(face_count == 1))

        if status["yaw"] is not None:
            bad_pose = (abs(status["yaw"]) > config.YAW_THRESHOLD_DEG or
                        abs(status["pitch"]) > config.PITCH_THRESHOLD_DEG)
            self.card_pose.update_value(f"{status['yaw']:.0f}\u00b0 / {status['pitch']:.0f}\u00b0",
                                         ok=not bad_pose)
        else:
            self.card_pose.update_value("--", ok=True)

        if status["gaze_ratio"] is not None:
            bad_gaze = abs(status["gaze_ratio"] - 0.5) > config.GAZE_HORIZONTAL_THRESHOLD
            self.card_gaze.update_value(f"{status['gaze_ratio']:.2f}", ok=not bad_gaze)
        else:
            self.card_gaze.update_value("--", ok=True)

        objects = status["objects"]
        if objects:
            self.card_objects.update_value(", ".join(objects[:2]), ok=False)
        else:
            self.card_objects.update_value("None", ok=True)

    def _maybe_log_activity_snapshot(self, status):
        """Every few seconds, regardless of whether a violation fired, log a
        plain status line -- this is what makes the Activity tab a full record
        of what the system observed, not just the moments it flagged."""
        now = time.time()
        if now - self.last_activity_snapshot < ACTIVITY_SNAPSHOT_INTERVAL:
            return
        self.last_activity_snapshot = now

        parts = [f"Faces={status['face_count']}"]
        if status["yaw"] is not None:
            parts.append(f"Yaw={status['yaw']:.1f}")
            parts.append(f"Pitch={status['pitch']:.1f}")
        if status["gaze_ratio"] is not None:
            parts.append(f"Gaze={status['gaze_ratio']:.2f}")
        parts.append(f"Objects={','.join(status['objects']) if status['objects'] else 'none'}")

        self._log_activity("Status check -- " + ", ".join(parts), FG_MUTED)

    def _log_activity(self, text, color=FG_MUTED):
        clock = time.strftime("%H:%M:%S")
        self.activity_listbox.insert(tk.END, f"[{clock}] {text}")
        self.activity_listbox.itemconfig(tk.END, fg=color)
        self.activity_listbox.see(tk.END)

    def _on_violation(self, event_type, severity, details, timestamp):
        """Called from ProctoringSession/EventLogger whenever a violation fires.
        Logged into BOTH the Alerts tab and the full Activity tab."""
        self.total_violations += 1
        self.violation_count_label.config(text=str(self.total_violations))

        clock = timestamp.split(" ")[-1]  # just the time portion
        entry = f"[{clock}] {event_type}: {details}"
        color = SEVERITY_COLORS.get(severity, FG_TEXT)

        self.alert_listbox.insert(tk.END, entry)
        self.alert_listbox.itemconfig(tk.END, fg=color)
        self.alert_listbox.see(tk.END)

        self.activity_listbox.insert(tk.END, f"{entry}  [{severity}]")
        self.activity_listbox.itemconfig(tk.END, fg=color)
        self.activity_listbox.see(tk.END)

    # ----------------------------------------------------------- Report
    def _show_summary(self, report_text, score, summary):
        dialog = tk.Toplevel(self.root)
        dialog.title("Session Report")
        dialog.configure(bg=BG_DARK)
        dialog.geometry("560x600")

        tk.Label(dialog, text="Session Report", bg=BG_DARK, fg=FG_TEXT,
                 font=("Segoe UI", 16, "bold")).pack(pady=(18, 2))
        tk.Label(dialog,
                 text=f"{summary['candidate_id']}  \u2022  {summary['duration_seconds']}s  \u2022  "
                      f"{summary['total_events']} violation(s)",
                 bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 9)).pack(pady=(0, 12))

        score_color = COLOR_OK if score >= 70 else (COLOR_WARN if score >= 40 else COLOR_ALERT)
        score_frame = tk.Frame(dialog, bg=BG_CARD)
        score_frame.pack(fill="x", padx=20, pady=(0, 14))
        tk.Label(score_frame, text="INTEGRITY SCORE", bg=BG_CARD, fg=FG_MUTED,
                 font=("Segoe UI", 9)).pack(pady=(10, 0))
        tk.Label(score_frame, text=f"{score}/100", bg=BG_CARD, fg=score_color,
                 font=("Segoe UI", 28, "bold")).pack(pady=(0, 10))

        # ---- Breakdown table ----
        tk.Label(dialog, text="VIOLATION BREAKDOWN", bg=BG_DARK, fg=FG_MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=20)

        table_frame = tk.Frame(dialog, bg=BG_DARK)
        table_frame.pack(fill="x", padx=20, pady=(4, 14))

        columns = ("type", "count")
        row_count = max(1, len(summary["event_counts"]))
        tree = ttk.Treeview(table_frame, columns=columns, show="headings",
                             style="Report.Treeview", height=min(6, row_count))
        tree.heading("type", text="Event Type")
        tree.heading("count", text="Count")
        tree.column("type", width=320, anchor="w")
        tree.column("count", width=80, anchor="center")

        if summary["event_counts"]:
            for event_type, count in summary["event_counts"].items():
                tree.insert("", "end", values=(event_type, count))
        else:
            tree.insert("", "end", values=("No violations -- clean session", ""))
        tree.pack(fill="x")

        # ---- File locations ----
        paths_frame = tk.Frame(dialog, bg=BG_DARK)
        paths_frame.pack(fill="x", padx=20, pady=(0, 10))
        tk.Label(paths_frame, text=f"Event log: {summary['log_path']}", bg=BG_DARK,
                 fg=FG_MUTED, font=("Consolas", 8), anchor="w", justify="left",
                 wraplength=520).pack(anchor="w")
        tk.Label(paths_frame, text=f"Screenshots: {summary['screenshot_dir']}", bg=BG_DARK,
                 fg=FG_MUTED, font=("Consolas", 8), anchor="w", justify="left",
                 wraplength=520).pack(anchor="w")

        ttk.Button(dialog, text="Close", style="Accent.TButton",
                   command=dialog.destroy).pack(pady=(4, 16))


def main():
    root = tk.Tk()
    ProctoringGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
