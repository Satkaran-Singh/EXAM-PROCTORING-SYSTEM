"""
FaceMonitor
-----------
Detects how many faces are present in the frame.
Flags:
  - NO_FACE          -> candidate has left the frame / camera blocked
  - MULTIPLE_FACES   -> a second person is present (possible collusion)

Uses MediaPipe's Tasks API FaceDetector (BlazeFace short-range model),
which replaces the older `mp.solutions.face_detection` API removed in
mediapipe >= 0.10.15.
"""

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision as mp_vision

from modules.model_utils import ensure_model

FACE_DETECTOR_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
)
FACE_DETECTOR_FILENAME = "blaze_face_short_range.tflite"


class FaceMonitor:
    def __init__(self, min_confidence: float = 0.6):
        model_path = ensure_model(FACE_DETECTOR_FILENAME, FACE_DETECTOR_URL)
        options = mp_vision.FaceDetectorOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=mp_vision.RunningMode.IMAGE,
            min_detection_confidence=min_confidence,
        )
        self.detector = mp_vision.FaceDetector.create_from_options(options)

    def analyze(self, frame_bgr):
        """
        Returns:
            face_count (int)
            boxes (list of (x, y, w, h) in pixel coords)
            annotated_frame (frame with boxes drawn, if faces found)
        """
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.detector.detect(mp_image)

        boxes = []
        for detection in result.detections:
            bb = detection.bounding_box
            x, y, w, h = bb.origin_x, bb.origin_y, bb.width, bb.height
            boxes.append((x, y, w, h))
            cv2.rectangle(frame_bgr, (x, y), (x + w, y + h), (0, 200, 0), 2)

        return len(boxes), boxes, frame_bgr

    def close(self):
        self.detector.close()
