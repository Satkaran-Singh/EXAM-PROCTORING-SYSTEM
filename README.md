# AI-Powered Exam Proctoring System

Real-time webcam-based proctoring for online/offline exams using computer
vision and ML. Built for the problem statement: detecting multiple faces,
unusual head/eye movement, and unauthorized objects during an exam.

## Features

| Module | What it does | Flags raised |
|---|---|---|
| `face_monitor.py` | Detects and counts faces (MediaPipe Face Detection) | `NO_FACE`, `MULTIPLE_FACES` |
| `pose_gaze_monitor.py` | Head pose (yaw/pitch via solvePnP) + eye gaze (iris tracking) | `LOOKING_AWAY`, `GAZE_OFF_SCREEN` |
| `object_monitor.py` | Detects phones, books, laptops, tablets (YOLOv8n, COCO-pretrained) | `SUSPICIOUS_OBJECT` |
| `logger.py` | Timestamped CSV event log, screenshot capture, end-of-session integrity report | — |

## How it works

1. Webcam frames are pulled in a loop (`main.py`).
2. Each frame is passed through the face, pose/gaze, and (periodically) object
   detectors.
3. A condition must persist for a configurable number of seconds
   (see `config.py`) before it's logged — this avoids false alarms from a
   single blurry frame or a natural blink/glance.
4. Every violation is timestamped, screenshotted, and written to a CSV log.
5. On exit (`q` key), a session report is generated with a simple
   **Integrity Score** (100 = clean, deducted per violation type/frequency).

## Setup

```bash
pip install -r requirements.txt
```

### Option A -- Web App (full exam flow, recommended)

```bash
python app.py
```

Open **http://localhost:5000** and you'll get a real exam-taking flow:

1. **Join** (`/`) -- student enters a unique exam code + name + candidate ID.
   Demo codes: `MATH101`, `CS101` (edit/add exams in `exam_data.py`).
2. **Instructions** (`/instructions`) -- exam rules, a local camera self-test
   (via the browser, not recorded), and an "I agree to be monitored" checkbox
   gating the Start button.
3. **Exam** (`/exam`) -- timed, with a question palette (numbered grid showing
   answered / not-answered / marked-for-review / not-visited), Save & Next,
   Mark for Review & Next, Clear Response, and Previous -- the same pattern
   used by real exam platforms. A small proctoring feed runs in the header the
   whole time, and a warning banner pops up the instant a violation fires.
   The exam **auto-submits** when the timer hits zero, or if violations reach
   the configurable threshold (`config.AUTO_SUBMIT_VIOLATION_THRESHOLD`).
4. **Result** (`/result`) -- score, integrity score, a full violation
   breakdown table, and a per-question answer review (your answer vs. the
   correct one).

There's also a **standalone dashboard** at `/dashboard` for testing/demoing
the proctoring pipeline on its own, independent of any exam -- useful for
verifying camera/detection setup before running a real exam session.

> **Note:** only one proctoring session (exam or dashboard) can run at a time,
> since there's one physical webcam. Also, the instructions page's camera
> self-test uses the *browser's* camera API purely for a local preview and
> releases it after a few seconds -- the actual exam capture is done
> server-side via OpenCV, and most systems won't let both hold the camera at
> the same time.

### Option B -- Desktop GUI

```bash
python gui_app.py
```

A dashboard opens with:
- **Live annotated video feed** (face boxes, object boxes, pose readout drawn directly on frame)
- **Status cards** -- faces detected, head pose (yaw/pitch), gaze ratio, objects detected, all updating live and turning red when out of threshold
- **Alerts tab** -- only actual violations, color-coded by severity
- **Full Activity Log tab** -- a continuous feed of everything the system observes (a status snapshot every ~2 seconds) *plus* every violation, so you have a complete record of the session, not just the flagged moments
- **Live violation counter** and session timer
- On clicking **End Session**, a detailed report dialog appears: integrity score, a breakdown table of violations by type, and the file paths for the full CSV log and screenshots

Enter a candidate ID before clicking **Start Session**.

> **Tkinter note:** On Windows, `tkinter` ships with the standard Python
> installer, so no extra install is needed. On Linux, if `python gui_app.py`
> fails with `ModuleNotFoundError: No module named 'tkinter'`, install it via
> your package manager, e.g. `sudo apt install python3-tk`.

### Option C -- CLI / raw OpenCV window

```bash
python main.py --candidate-id 21103045
```

Press **q** in the video window to end the session and generate the report (same report format, printed to the terminal and saved to `logs/`).

> **Note on model downloads:** On first run, `ultralytics` auto-downloads
> `yolov8n.pt` (~6 MB) and the app auto-downloads two MediaPipe model files
> (`blaze_face_short_range.tflite` and `face_landmarker.task`, ~10 MB total)
> into a local `models/` folder. Make sure you have internet access on first
> run; after that everything is cached locally and works offline.

## Output

After a session, you'll find in `logs/`:
- `<session_id>_events.csv` — every flagged event with timestamp, severity, and details
- `<session_id>_session_report.txt` — human-readable summary + integrity score

And in `screenshots/`: a JPEG for every violation, named by event type and time.

## Tuning

All thresholds live in `config.py` — e.g. how many degrees of head turn counts
as "looking away," how long a condition must persist before it's flagged, and
which object classes count as suspicious. Adjust these based on your camera
quality, lighting, and how strict you want the system to be (a webcam-based
system will always need looser thresholds than a proctor watching in person).

## Known limitations / next steps

- **Single camera, 2D pose only.** No depth sensing — extreme lighting or a
  low-quality webcam will degrade face mesh and head-pose accuracy.
- **No audio monitoring.** Talking, whispering, or a second voice in the room
  isn't detected. Adding a `sounddevice`-based audio-level/voice-activity
  module is a natural next step.
- **No liveness/spoof detection.** Doesn't currently check whether the face
  is a live person vs. a photo/video (anti-spoofing via blink detection or
  texture analysis would harden this for high-stakes exams).
- **Local-only, single active session.** Only one proctoring session (exam
  or dashboard) can run at a time on this machine, since there's one physical
  webcam. For a real deployment with many simultaneous candidates, you'd want
  one server per exam room/session, or per-candidate camera streams in the cloud.
- **Client-triggered auto-submit is a soft check.** The exam page polls
  violation counts and calls submit itself when the threshold is hit; a
  tampered or JS-disabled browser could in theory delay that. The exam timer
  (enforced server-side via elapsed time in `/exam_status`) is the hard
  backstop — it always ends the exam regardless of what the client does.
- **Integrity score is a simple heuristic**, not a validated statistical
  model — treat it as a triage signal for human review, not a final verdict.

## Project structure

```
ai_proctor/
├── app.py                     # Flask web app (exam flow + dashboard) -- recommended
├── main.py                    # CLI entry point (raw OpenCV window)
├── gui_app.py                 # Desktop GUI entry point
├── exam_data.py                # sample exam/question bank, keyed by exam code
├── config.py                  # all tunable thresholds
├── requirements.txt
├── modules/
│   ├── session.py              # shared detection pipeline (used by all three entry points)
│   ├── face_monitor.py
│   ├── pose_gaze_monitor.py
│   ├── object_monitor.py
│   ├── model_utils.py          # auto-downloads MediaPipe model files
│   └── logger.py
├── templates/                  # Flask/Jinja pages
│   ├── join.html               # exam code entry
│   ├── instructions.html       # rules + camera self-test
│   ├── exam.html                # timed exam with question navigation
│   ├── result.html              # score + integrity report
│   └── dashboard.html          # standalone proctor test dashboard
├── static/
│   ├── style.css               # dashboard styles
│   ├── exam-flow.css           # join/instructions/exam/result styles
│   ├── dashboard.js
│   └── exam.js
├── logs/                       # generated at runtime
└── screenshots/                # generated at runtime
```
