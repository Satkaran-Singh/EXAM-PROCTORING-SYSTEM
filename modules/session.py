"""
ProctoringSession
------------------
Core detection pipeline, shared by both the CLI (main.py) and the desktop
GUI (gui_app.py). Keeping this separate means the GUI is purely a
presentation layer -- it doesn't duplicate any detection logic.
"""

import time

import cv2

import config
from modules.face_monitor import FaceMonitor
from modules.pose_gaze_monitor import PoseGazeMonitor
from modules.object_monitor import ObjectMonitor
from modules.logger import EventLogger


class ProctoringSession:
    def __init__(self, candidate_id: str, on_event=None):
        """
        on_event: optional callback(event_type, severity, details, timestamp)
                  fired every time a violation is logged -- lets a GUI show
                  live alerts without polling the CSV file.
        """
        self.face_monitor = FaceMonitor(config.MIN_FACE_DETECTION_CONFIDENCE)
        self.pose_gaze_monitor = PoseGazeMonitor()
        self.object_monitor = ObjectMonitor(
            config.OBJECT_MODEL_PATH,
            config.OBJECT_CONFIDENCE_THRESHOLD,
            config.SUSPICIOUS_OBJECT_CLASSES
        )
        self.logger = EventLogger(
            config.LOG_DIR, config.SCREENSHOT_DIR,
            config.SESSION_REPORT_NAME, candidate_id,
            on_event=on_event
        )

        # Sustained-condition trackers: {condition_name: first_seen_timestamp or None}
        self._condition_start = {
            "no_face": None,
            "multi_face": None,
            "bad_pose": None,
            "bad_gaze": None,
        }

        self.frame_count = 0
        self.last_object_detections = []

    def _sustained(self, key: str, is_active: bool, threshold_seconds: float) -> bool:
        """Returns True the moment a condition has been continuously active
        for >= threshold_seconds. Resets tracker when condition clears."""
        now = time.time()
        if not is_active:
            self._condition_start[key] = None
            return False

        if self._condition_start[key] is None:
            self._condition_start[key] = now
            return False

        return (now - self._condition_start[key]) >= threshold_seconds

    def process_frame(self, frame):
        """
        Runs the full detection pipeline on one frame.
        Returns (annotated_frame, status) where status is a dict describing
        the current state -- used by main.py for the overlay bar and by
        gui_app.py to populate its sidebar widgets.
        """
        status = {
            "face_count": 0, "yaw": None, "pitch": None,
            "gaze_ratio": None, "objects": []
        }

        # ---- 1. Face count ----
        face_count, boxes, frame = self.face_monitor.analyze(frame)
        status["face_count"] = face_count

        if self._sustained("no_face", face_count == 0, config.NO_FACE_ALERT_SECONDS):
            if self.logger.can_alert("NO_FACE", config.ALERT_COOLDOWN_SECONDS):
                self.logger.log_event("NO_FACE", "HIGH",
                                       "No face detected in frame", frame)
        if self._sustained("multi_face", face_count > config.EXPECTED_FACE_COUNT,
                            config.MULTI_FACE_ALERT_SECONDS):
            if self.logger.can_alert("MULTIPLE_FACES", config.ALERT_COOLDOWN_SECONDS):
                self.logger.log_event("MULTIPLE_FACES", "HIGH",
                                       f"{face_count} faces detected", frame)

        # ---- 2. Head pose + gaze (only meaningful if exactly one face) ----
        if face_count == 1:
            pose_result = self.pose_gaze_monitor.analyze(frame)
            frame = pose_result["frame"]
            status["yaw"] = pose_result["yaw"]
            status["pitch"] = pose_result["pitch"]
            status["gaze_ratio"] = pose_result["gaze_ratio"]

            bad_pose = False
            if pose_result["yaw"] is not None:
                bad_pose = (abs(pose_result["yaw"]) > config.YAW_THRESHOLD_DEG or
                            abs(pose_result["pitch"]) > config.PITCH_THRESHOLD_DEG)

            if self._sustained("bad_pose", bad_pose, config.HEAD_POSE_ALERT_SECONDS):
                if self.logger.can_alert("LOOKING_AWAY", config.ALERT_COOLDOWN_SECONDS):
                    self.logger.log_event(
                        "LOOKING_AWAY", "MEDIUM",
                        f"Yaw={pose_result['yaw']:.1f} Pitch={pose_result['pitch']:.1f}",
                        frame)

            bad_gaze = False
            if pose_result["gaze_ratio"] is not None:
                offset = abs(pose_result["gaze_ratio"] - 0.5)
                bad_gaze = offset > config.GAZE_HORIZONTAL_THRESHOLD

            if self._sustained("bad_gaze", bad_gaze, config.GAZE_ALERT_SECONDS):
                if self.logger.can_alert("GAZE_OFF_SCREEN", config.ALERT_COOLDOWN_SECONDS):
                    self.logger.log_event(
                        "GAZE_OFF_SCREEN", "MEDIUM",
                        f"Gaze ratio={pose_result['gaze_ratio']:.2f}", frame)

        # ---- 3. Object detection (throttled for performance) ----
        if self.frame_count % config.OBJECT_DETECTION_EVERY_N_FRAMES == 0:
            detections, frame = self.object_monitor.analyze(frame)
            self.last_object_detections = detections
            for det in detections:
                if self.logger.can_alert(f"OBJ_{det['label']}", config.ALERT_COOLDOWN_SECONDS):
                    self.logger.log_event(
                        "SUSPICIOUS_OBJECT", "HIGH",
                        f"{det['label']} detected (conf={det['confidence']:.2f})", frame)
        else:
            for det in self.last_object_detections:
                x1, y1, x2, y2 = det["box"]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)

        status["objects"] = [d["label"] for d in self.last_object_detections]
        self.frame_count += 1

        return frame, status

    def close(self):
        self.face_monitor.close()
        self.pose_gaze_monitor.close()
        return self.logger.generate_report()
