"""
Central configuration for the AI Proctoring System.
Tune these values based on lighting conditions, camera quality, and
how strict you want the monitoring to be.
"""

# ---------------- Camera ----------------
CAMERA_INDEX = 0            # 0 = default webcam. Change if you have multiple cameras.
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# ---------------- Face Monitoring ----------------
MIN_FACE_DETECTION_CONFIDENCE = 0.6
EXPECTED_FACE_COUNT = 1          # exactly one candidate should be visible
NO_FACE_ALERT_SECONDS = 3        # face missing for this long -> alert
MULTI_FACE_ALERT_SECONDS = 1     # extra face(s) visible for this long -> alert

# ---------------- Head Pose ----------------
YAW_THRESHOLD_DEG = 30           # looking left/right beyond this -> suspicious
PITCH_THRESHOLD_DEG = 20         # looking up/down beyond this -> suspicious
HEAD_POSE_ALERT_SECONDS = 2      # sustained bad pose duration before alert

# ---------------- Gaze / Eye Tracking ----------------
GAZE_HORIZONTAL_THRESHOLD = 0.35 # normalized iris offset from eye center
GAZE_ALERT_SECONDS = 2

# ---------------- Object Detection ----------------
OBJECT_MODEL_PATH = "yolov8n.pt"     # auto-downloaded by ultralytics on first run
OBJECT_CONFIDENCE_THRESHOLD = 0.45
SUSPICIOUS_OBJECT_CLASSES = {
    "cell phone", "book", "laptop", "tablet", "remote"
}
OBJECT_DETECTION_EVERY_N_FRAMES = 5   # run YOLO every Nth frame (perf optimization)

# ---------------- Alerts / Logging ----------------
ALERT_COOLDOWN_SECONDS = 5       # min gap between repeated alerts of the same type
LOG_DIR = "logs"
SCREENSHOT_DIR = "screenshots"
SESSION_REPORT_NAME = "session_report.csv"

# ---------------- Exam Auto-Submit ----------------
AUTO_SUBMIT_VIOLATION_THRESHOLD = 6   # exam auto-submits if total violations reach this

# ---------------- Display ----------------
SHOW_LANDMARKS = True
WINDOW_NAME = "AI Exam Proctoring System"
