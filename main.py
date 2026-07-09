"""
AI-Powered Exam Proctoring System -- CLI entry point
======================================================
Real-time webcam monitoring for online/offline exams. Detects:
  - Absence / multiple faces
  - Head turned away for a sustained period
  - Eyes looking off-screen (possible notes/second monitor)
  - Unauthorized objects (phone, book, laptop, etc.)

Run:
    python main.py --candidate-id 12345

Controls:
    q  - end session and generate report

For a desktop GUI instead of the raw OpenCV window, run gui_app.py.
"""

import argparse

import cv2

import config
from modules.session import ProctoringSession


def main():
    parser = argparse.ArgumentParser(description="AI Exam Proctoring System")
    parser.add_argument("--candidate-id", default="candidate_01",
                         help="Identifier for this exam session")
    args = parser.parse_args()

    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)

    if not cap.isOpened():
        print("ERROR: Could not open webcam. Check CAMERA_INDEX in config.py.")
        return

    session = ProctoringSession(args.candidate_id)
    print("Proctoring session started. Press 'q' to end and generate report.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Failed to read frame from camera. Exiting.")
                break

            frame, status = session.process_frame(frame)

            status_text = f"Faces: {status['face_count']}"
            if status["yaw"] is not None:
                status_text += f" | Yaw:{status['yaw']:.1f}"

            cv2.rectangle(frame, (0, 0), (frame.shape[1], 25), (30, 30, 30), -1)
            cv2.putText(frame, status_text, (8, 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            cv2.imshow(config.WINDOW_NAME, frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        session.close()


if __name__ == "__main__":
    main()
