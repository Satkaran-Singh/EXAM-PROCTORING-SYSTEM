"""
AI-Powered Exam Proctoring System -- Web (Flask) frontend
============================================================
Two ways to use this:

1. STUDENT EXAM FLOW (the main app):
     /              -> enter a unique exam code + name + candidate ID
     /instructions  -> exam rules, camera check, "Start Exam"
     /exam          -> timed exam with question navigation, proctoring
                       running underneath the whole time
     /result        -> score + integrity report after submission

2. STANDALONE PROCTOR DASHBOARD (for testing/demo of the CV pipeline
   on its own, independent of an exam):
     /dashboard     -> same dashboard from the desktop-GUI-equivalent web build

Both share the exact same detection pipeline (modules/session.py) and
the same underlying camera/session state -- only one proctoring session
(exam or dashboard) can be active at a time, since there's one physical
webcam.

Run:
    python app.py
Then open:
    http://localhost:5000
"""

import secrets
import threading
import time

import cv2
from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for

import config
import exam_data
from modules.session import ProctoringSession

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # regenerated each run; fine for a local demo

ACTIVITY_SNAPSHOT_INTERVAL = 2.0  # seconds between routine (non-violation) log entries
MAX_STORED_EVENTS = 500

lock = threading.Lock()
state = {
    "running": False,
    "session": None,
    "cap": None,
    "latest_jpeg": None,
    "status": {"face_count": 0, "yaw": None, "pitch": None, "gaze_ratio": None, "objects": []},
    "events": [],          # dicts: id, time, kind ("alert"/"activity"), event_type, severity, details
    "next_event_id": 1,
    "start_time": None,
    "candidate_id": None,
    "last_activity_snapshot": 0.0,
    "exam": None,           # set while an exam (not just the dashboard) is active -- see begin_exam
}


# ============================================================= Shared core
def _add_event(kind, event_type, severity, details):
    with lock:
        eid = state["next_event_id"]
        state["next_event_id"] += 1
        state["events"].append({
            "id": eid,
            "time": time.strftime("%H:%M:%S"),
            "kind": kind,
            "event_type": event_type,
            "severity": severity,
            "details": details,
        })
        if len(state["events"]) > MAX_STORED_EVENTS:
            state["events"] = state["events"][-MAX_STORED_EVENTS:]


def _on_violation(event_type, severity, details, timestamp):
    """Callback wired into ProctoringSession -> EventLogger; fires on every violation."""
    _add_event("alert", event_type, severity, details)


def _camera_loop():
    """Runs in a background thread: reads frames, runs detection, and
    updates shared state under a lock so HTTP request threads can read it."""
    cap = state["cap"]
    proctor_session = state["session"]

    while state["running"]:
        ret, frame = cap.read()
        if not ret:
            break

        frame, status = proctor_session.process_frame(frame)
        with lock:
            state["status"] = status

        now = time.time()
        if now - state["last_activity_snapshot"] >= ACTIVITY_SNAPSHOT_INTERVAL:
            state["last_activity_snapshot"] = now
            parts = [f"Faces={status['face_count']}"]
            if status["yaw"] is not None:
                parts.append(f"Yaw={status['yaw']:.1f}")
                parts.append(f"Pitch={status['pitch']:.1f}")
            if status["gaze_ratio"] is not None:
                parts.append(f"Gaze={status['gaze_ratio']:.2f}")
            parts.append(f"Objects={','.join(status['objects']) if status['objects'] else 'none'}")
            _add_event("activity", "STATUS", "INFO", "Status check -- " + ", ".join(parts))

        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ok:
            with lock:
                state["latest_jpeg"] = buf.tobytes()

    cap.release()


def _start_proctoring(candidate_id):
    """Shared by both the dashboard's /start and the exam flow's /begin_exam.
    Returns (ok: bool, error: str or None)."""
    if state["running"]:
        return False, "A proctoring session is already active on this machine."

    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
    if not cap.isOpened():
        return False, "Could not open webcam. Check CAMERA_INDEX in config.py."

    proctor_session = ProctoringSession(candidate_id, on_event=_on_violation)

    with lock:
        state["cap"] = cap
        state["session"] = proctor_session
        state["running"] = True
        state["start_time"] = time.time()
        state["candidate_id"] = candidate_id
        state["events"] = []
        state["next_event_id"] = 1
        state["last_activity_snapshot"] = 0.0
        state["latest_jpeg"] = None

    _add_event("activity", "SESSION", "INFO", f"Session started for candidate '{candidate_id}'.")
    threading.Thread(target=_camera_loop, daemon=True).start()
    return True, None


def _stop_proctoring():
    """Shared by both the dashboard's /stop and the exam flow's /submit_exam.
    Returns (report_text, score, summary) or (None, None, None) if nothing was running."""
    if not state["running"]:
        return None, None, None

    state["running"] = False
    time.sleep(0.3)  # let the camera loop exit and release the capture

    proctor_session = state["session"]
    report_text, score, summary = proctor_session.close()

    with lock:
        state["session"] = None
        state["cap"] = None
        state["latest_jpeg"] = None

    _add_event("activity", "SESSION", "INFO", "Session ended. Report generated.")
    return report_text, score, summary


def _gen_frames():
    while True:
        with lock:
            jpeg = state["latest_jpeg"]
        if jpeg is None:
            time.sleep(0.05)
            continue
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
        time.sleep(0.03)


@app.route("/video_feed")
def video_feed():
    return Response(_gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/events")
def events():
    """Polling endpoint: returns events with id > since, so the browser
    only fetches what's new each time. Shared by dashboard and exam page."""
    since = int(request.args.get("since", 0))
    with lock:
        new_events = [e for e in state["events"] if e["id"] > since]
    return jsonify({"events": new_events})


def _status_payload():
    with lock:
        s = dict(state["status"])
        running = state["running"]
        start_time = state["start_time"]
        violation_count = sum(1 for e in state["events"] if e["kind"] == "alert")

    elapsed = round(time.time() - start_time, 1) if (start_time and running) else 0

    face_ok = (s["face_count"] == 1)
    pose_ok = True
    if s["yaw"] is not None:
        pose_ok = not (abs(s["yaw"]) > config.YAW_THRESHOLD_DEG or
                        abs(s["pitch"]) > config.PITCH_THRESHOLD_DEG)
    gaze_ok = True
    if s["gaze_ratio"] is not None:
        gaze_ok = not (abs(s["gaze_ratio"] - 0.5) > config.GAZE_HORIZONTAL_THRESHOLD)
    objects_ok = len(s["objects"]) == 0

    s["face_ok"] = face_ok
    s["pose_ok"] = pose_ok
    s["gaze_ok"] = gaze_ok
    s["objects_ok"] = objects_ok

    return {"status": s, "running": running, "elapsed": elapsed, "violation_count": violation_count}


@app.route("/status")
def status():
    return jsonify(_status_payload())


# ============================================================= Dashboard (standalone tester)
@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/start", methods=["POST"])
def start():
    payload = request.get_json(silent=True) or {}
    candidate_id = (payload.get("candidate_id") or "candidate_01").strip() or "candidate_01"
    ok, error = _start_proctoring(candidate_id)
    if not ok:
        return jsonify({"ok": False, "error": error}), 400 if "already" in (error or "") else 500
    return jsonify({"ok": True})


@app.route("/stop", methods=["POST"])
def stop():
    report_text, score, summary = _stop_proctoring()
    if summary is None:
        return jsonify({"ok": False, "error": "No session is running."}), 400
    return jsonify({"ok": True, "score": score, "summary": summary, "report_text": report_text})


# ============================================================= Student exam flow
@app.route("/")
def join():
    return render_template("join.html")


@app.route("/join", methods=["POST"])
def do_join():
    exam_code = request.form.get("exam_code", "")
    candidate_name = request.form.get("candidate_name", "").strip()
    candidate_id = request.form.get("candidate_id", "").strip()

    exam = exam_data.get_exam(exam_code)
    if not exam:
        return render_template("join.html", error="Invalid exam code. Please check and try again.",
                                candidate_name=candidate_name, candidate_id=candidate_id)
    if not candidate_name or not candidate_id:
        return render_template("join.html", error="Please enter your name and candidate ID.",
                                exam_code=exam_code)

    session["exam_code"] = exam_code.strip().upper()
    session["candidate_name"] = candidate_name
    session["candidate_id"] = candidate_id
    return redirect(url_for("instructions"))


@app.route("/instructions")
def instructions():
    exam = exam_data.get_exam(session.get("exam_code", ""))
    if not exam:
        return redirect(url_for("join"))
    return render_template("instructions.html", exam=exam, exam_code=session["exam_code"])


@app.route("/begin_exam", methods=["POST"])
def begin_exam():
    exam = exam_data.get_exam(session.get("exam_code", ""))
    if not exam:
        return jsonify({"ok": False, "error": "Your session expired. Please rejoin the exam."}), 400

    candidate_id = session.get("candidate_id", "candidate_01")
    ok, error = _start_proctoring(candidate_id)
    if not ok:
        return jsonify({"ok": False, "error": error}), 400 if "already" in (error or "") else 500

    with lock:
        state["exam"] = {
            "code": session["exam_code"],
            "title": exam["title"],
            "duration_seconds": exam["duration_minutes"] * 60,
            "questions": exam["questions"],
            "answers": {},     # question_id -> selected option index
            "marked": [],      # question_ids marked for review
            "start_time": time.time(),
            "auto_submitted": False,
        }

    return jsonify({"ok": True, "redirect": url_for("exam_page")})


@app.route("/exam")
def exam_page():
    if not state["running"] or not state.get("exam"):
        return redirect(url_for("join"))

    exam = state["exam"]
    # Strip correct answers before sending to the browser -- students shouldn't
    # see them in the page source.
    questions_public = [
        {"id": q["id"], "text": q["text"], "options": q["options"]}
        for q in exam["questions"]
    ]
    return render_template(
        "exam.html",
        exam_title=exam["title"],
        duration_seconds=exam["duration_seconds"],
        questions=questions_public,
        candidate_name=session.get("candidate_name", ""),
        candidate_id=session.get("candidate_id", ""),
        auto_submit_threshold=config.AUTO_SUBMIT_VIOLATION_THRESHOLD,
    )


@app.route("/answer", methods=["POST"])
def save_answer():
    data = request.get_json(silent=True) or {}
    question_id = data.get("question_id")
    selected = data.get("selected")       # int index or None (clear response)
    marked = data.get("marked")           # bool or None (leave unchanged)

    with lock:
        exam = state.get("exam")
        if not exam or question_id is None:
            return jsonify({"ok": False}), 400

        if selected is None:
            exam["answers"].pop(question_id, None)
        else:
            exam["answers"][question_id] = selected

        if marked is True and question_id not in exam["marked"]:
            exam["marked"].append(question_id)
        elif marked is False and question_id in exam["marked"]:
            exam["marked"].remove(question_id)

    return jsonify({"ok": True})


@app.route("/exam_status")
def exam_status():
    with lock:
        exam = state.get("exam")
        if not exam:
            return jsonify({"ok": False}), 400
        elapsed = time.time() - exam["start_time"]
        remaining = max(0, exam["duration_seconds"] - elapsed)
        answered = list(exam["answers"].keys())
        marked = list(exam["marked"])

    base = _status_payload()
    return jsonify({
        "ok": True,
        "remaining_seconds": round(remaining),
        "answered": answered,
        "marked": marked,
        "violation_count": base["violation_count"],
    })


@app.route("/submit_exam", methods=["POST"])
def submit_exam():
    with lock:
        exam = state.get("exam")
    if not exam:
        return jsonify({"ok": False, "error": "No active exam to submit."}), 400

    payload = request.get_json(silent=True) or {}
    reason = payload.get("reason", "manual")  # "manual" | "timeout" | "violations"

    correct = 0
    total = len(exam["questions"])
    per_question = []
    for q in exam["questions"]:
        selected = exam["answers"].get(q["id"])
        is_correct = (selected is not None and int(selected) == q["answer"])
        if is_correct:
            correct += 1
        per_question.append({
            "id": q["id"], "text": q["text"], "options": q["options"],
            "correct_index": q["answer"], "selected_index": selected, "is_correct": is_correct,
        })

    report_text, score, summary = _stop_proctoring()

    with lock:
        state["exam"] = None

    result = {
        "exam_title": exam["title"],
        "candidate_name": session.get("candidate_name", ""),
        "candidate_id": session.get("candidate_id", ""),
        "correct": correct,
        "total": total,
        "percentage": round(correct / total * 100, 1) if total else 0,
        "integrity_score": score,
        "summary": summary,
        "per_question": per_question,
        "submit_reason": reason,
    }
    session["last_result"] = result
    return jsonify({"ok": True, "redirect": url_for("result")})


@app.route("/result")
def result():
    result_data = session.get("last_result")
    if not result_data:
        return redirect(url_for("join"))
    return render_template("result.html", result=result_data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True, debug=False)
