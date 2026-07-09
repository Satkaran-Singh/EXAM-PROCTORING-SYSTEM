"""
PoseGazeMonitor
---------------
Estimates:
  1. Head pose (yaw / pitch) via classic solvePnP against a generic 3D
     face model, using 6 stable landmarks from MediaPipe's FaceLandmarker.
  2. Gaze direction via iris landmarks (the FaceLandmarker model always
     outputs 478 landmarks, where indices 468-477 are the iris points --
     no extra flag needed, unlike the old solutions API's refine_landmarks).

Flags:
  - LOOKING_AWAY      -> yaw/pitch beyond threshold (head turned)
  - GAZE_OFF_SCREEN   -> eyes looking far left/right while head is roughly forward

Uses MediaPipe's Tasks API FaceLandmarker, which replaces the older
`mp.solutions.face_mesh` API removed in mediapipe >= 0.10.15.
"""

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision as mp_vision

from modules.model_utils import ensure_model

FACE_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
FACE_LANDMARKER_FILENAME = "face_landmarker.task"

# Landmark indices (478-point FaceLandmarker topology -- same indexing as
# the old 468+iris FaceMesh with refine_landmarks=True)
NOSE_TIP = 1
CHIN = 152
LEFT_EYE_OUTER = 33
RIGHT_EYE_OUTER = 263
LEFT_MOUTH = 61
RIGHT_MOUTH = 291

LEFT_EYE_INNER = 133
RIGHT_EYE_INNER = 362
LEFT_IRIS_CENTER = 468
RIGHT_IRIS_CENTER = 473

# Generic 3D face model points (arbitrary units, right-handed coord system)
MODEL_POINTS_3D = np.array([
    (0.0, 0.0, 0.0),        # Nose tip
    (0.0, -330.0, -65.0),   # Chin
    (-225.0, 170.0, -135.0),  # Left eye outer corner
    (225.0, 170.0, -135.0),   # Right eye outer corner
    (-150.0, -150.0, -125.0),  # Left mouth corner
    (150.0, -150.0, -125.0),   # Right mouth corner
], dtype=np.float64)


class PoseGazeMonitor:
    def __init__(self):
        model_path = ensure_model(FACE_LANDMARKER_FILENAME, FACE_LANDMARKER_URL)
        options = mp_vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=mp_vision.RunningMode.IMAGE,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.landmarker = mp_vision.FaceLandmarker.create_from_options(options)

    def _get_camera_matrix(self, w, h):
        focal_length = w
        center = (w / 2, h / 2)
        return np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1]
        ], dtype=np.float64)

    def analyze(self, frame_bgr):
        """
        Returns a dict:
            {
              "face_found": bool,
              "yaw": float or None,
              "pitch": float or None,
              "gaze_ratio": float or None,   # 0.5 = center, <0.5 left, >0.5 right
              "frame": annotated frame
            }
        """
        h, w, _ = frame_bgr.shape
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect(mp_image)

        output = {"face_found": False, "yaw": None, "pitch": None,
                  "gaze_ratio": None, "frame": frame_bgr}

        if not result.face_landmarks:
            return output

        output["face_found"] = True
        landmarks = result.face_landmarks[0]  # list of NormalizedLandmark

        def px(idx):
            lm = landmarks[idx]
            return np.array([lm.x * w, lm.y * h], dtype=np.float64)

        # ---- Head pose via solvePnP ----
        image_points = np.array([
            px(NOSE_TIP), px(CHIN), px(LEFT_EYE_OUTER),
            px(RIGHT_EYE_OUTER), px(LEFT_MOUTH), px(RIGHT_MOUTH)
        ], dtype=np.float64)

        camera_matrix = self._get_camera_matrix(w, h)
        dist_coeffs = np.zeros((4, 1))  # assume no lens distortion

        success, rotation_vec, _ = cv2.solvePnP(
            MODEL_POINTS_3D, image_points, camera_matrix, dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE
        )

        if success:
            rotation_mat, _ = cv2.Rodrigues(rotation_vec)
            proj_matrix = np.hstack((rotation_mat, np.zeros((3, 1))))
            euler_angles = cv2.decomposeProjectionMatrix(proj_matrix)[6].flatten()
            pitch, yaw, _roll = [float(a) for a in euler_angles]

            # Normalize pitch to a human-readable -90..90 range
            pitch = pitch - 180 if pitch > 90 else (pitch + 180 if pitch < -90 else pitch)

            output["yaw"] = yaw
            output["pitch"] = pitch

            cv2.putText(frame_bgr, f"Yaw:{yaw:.1f} Pitch:{pitch:.1f}",
                        (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        # ---- Gaze ratio (horizontal) ----
        try:
            left_ratio = self._eye_gaze_ratio(px(LEFT_EYE_OUTER), px(LEFT_EYE_INNER), px(LEFT_IRIS_CENTER))
            right_ratio = self._eye_gaze_ratio(px(RIGHT_EYE_INNER), px(RIGHT_EYE_OUTER), px(RIGHT_IRIS_CENTER))
            output["gaze_ratio"] = (left_ratio + right_ratio) / 2.0
        except IndexError:
            output["gaze_ratio"] = None

        return output

    @staticmethod
    def _eye_gaze_ratio(corner_a, corner_b, iris_center):
        """Horizontal position of iris between two eye corners: 0=at corner_a, 1=at corner_b."""
        eye_width = np.linalg.norm(corner_b - corner_a)
        if eye_width == 0:
            return 0.5
        projection = np.dot(iris_center - corner_a, (corner_b - corner_a) / eye_width)
        return float(np.clip(projection / eye_width, 0.0, 1.0))

    def close(self):
        self.landmarker.close()
