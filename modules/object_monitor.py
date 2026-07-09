"""
ObjectMonitor
-------------
Runs a YOLOv8 (COCO-pretrained) detector to catch unauthorized items in
frame: phones, books, laptops, tablets, remotes, etc.

YOLOv8n ("nano") is used for speed -- it's the smallest/fastest variant,
suitable for real-time CPU inference. The weight file (~6MB) is downloaded
automatically by ultralytics on first run.

To detect additional classes, just add their COCO label to
config.SUSPICIOUS_OBJECT_CLASSES.
"""

import cv2
from ultralytics import YOLO


class ObjectMonitor:
    def __init__(self, model_path: str, confidence_threshold: float,
                 suspicious_classes: set):
        self.model = YOLO(model_path)
        self.confidence_threshold = confidence_threshold
        self.suspicious_classes = {c.lower() for c in suspicious_classes}

    def analyze(self, frame_bgr):
        """
        Returns:
            detections: list of dicts {"label": str, "confidence": float, "box": (x1,y1,x2,y2)}
            annotated_frame
        """
        results = self.model(frame_bgr, verbose=False)[0]
        detections = []

        for box in results.boxes:
            conf = float(box.conf[0])
            if conf < self.confidence_threshold:
                continue
            cls_id = int(box.cls[0])
            label = self.model.names[cls_id].lower()

            if label in self.suspicious_classes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append({"label": label, "confidence": conf, "box": (x1, y1, x2, y2)})
                cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), (0, 0, 255), 2)
                cv2.putText(frame_bgr, f"{label} {conf:.2f}", (x1, max(y1 - 8, 0)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)

        return detections, frame_bgr
