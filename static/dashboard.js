const els = {
  candidateId: document.getElementById("candidateId"),
  statusDot: document.getElementById("statusDot"),
  statusText: document.getElementById("statusText"),
  timer: document.getElementById("timer"),
  toggleBtn: document.getElementById("toggleBtn"),
  videoFeed: document.getElementById("videoFeed"),
  videoPlaceholder: document.getElementById("videoPlaceholder"),
  cardFaces: document.getElementById("cardFaces"),
  cardPose: document.getElementById("cardPose"),
  cardGaze: document.getElementById("cardGaze"),
  cardObjects: document.getElementById("cardObjects"),
  violationCount: document.getElementById("violationCount"),
  alertsPane: document.getElementById("alertsPane"),
  activityPane: document.getElementById("activityPane"),
  reportModal: document.getElementById("reportModal"),
  reportMeta: document.getElementById("reportMeta"),
  reportScore: document.getElementById("reportScore"),
  breakdownTable: document.querySelector("#breakdownTable tbody"),
  reportPaths: document.getElementById("reportPaths"),
  closeReportBtn: document.getElementById("closeReportBtn"),
};

let running = false;
let statusPollHandle = null;
let eventsPollHandle = null;
let sinceEventId = 0;

// ---------------- Tabs ----------------
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".log-pane").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab + "Pane").classList.add("active");
  });
});

// ---------------- Start / Stop ----------------
els.toggleBtn.addEventListener("click", () => {
  if (running) {
    stopSession();
  } else {
    startSession();
  }
});

async function startSession() {
  const candidateId = els.candidateId.value.trim() || "candidate_01";

  const res = await fetch("/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_id: candidateId }),
  });
  const data = await res.json();

  if (!data.ok) {
    alert(data.error || "Could not start session.");
    return;
  }

  running = true;
  sinceEventId = 0;
  els.alertsPane.innerHTML = "";
  els.activityPane.innerHTML = "";
  els.violationCount.textContent = "0";

  els.candidateId.disabled = true;
  els.toggleBtn.textContent = "End Session";
  els.statusDot.className = "dot recording";
  els.statusText.textContent = "Recording";

  els.videoFeed.src = "/video_feed?t=" + Date.now();
  els.videoFeed.classList.add("active");
  els.videoPlaceholder.classList.add("hidden");

  statusPollHandle = setInterval(pollStatus, 700);
  eventsPollHandle = setInterval(pollEvents, 1000);
}

async function stopSession() {
  els.toggleBtn.disabled = true;
  const res = await fetch("/stop", { method: "POST" });
  const data = await res.json();
  els.toggleBtn.disabled = false;

  running = false;
  clearInterval(statusPollHandle);
  clearInterval(eventsPollHandle);
  pollEvents(); // grab any final events (e.g. "Session ended")

  els.candidateId.disabled = false;
  els.toggleBtn.textContent = "Start Session";
  els.statusDot.className = "dot idle";
  els.statusText.textContent = "Idle";

  els.videoFeed.classList.remove("active");
  els.videoFeed.src = "";
  els.videoPlaceholder.textContent = "Session ended.";
  els.videoPlaceholder.classList.remove("hidden");

  if (data.ok) {
    showReport(data);
  }
}

// ---------------- Polling ----------------
async function pollStatus() {
  try {
    const res = await fetch("/status");
    const data = await res.json();
    if (!data.running) return;

    const s = data.status;
    const mins = String(Math.floor(data.elapsed / 60)).padStart(2, "0");
    const secs = String(Math.floor(data.elapsed % 60)).padStart(2, "0");
    els.timer.textContent = `${mins}:${secs}`;

    setCard(els.cardFaces, String(s.face_count), s.face_ok);

    if (s.yaw !== null && s.yaw !== undefined) {
      setCard(els.cardPose, `${s.yaw.toFixed(0)}\u00b0 / ${s.pitch.toFixed(0)}\u00b0`, s.pose_ok);
    } else {
      setCard(els.cardPose, "--", true);
    }

    if (s.gaze_ratio !== null && s.gaze_ratio !== undefined) {
      setCard(els.cardGaze, s.gaze_ratio.toFixed(2), s.gaze_ok);
    } else {
      setCard(els.cardGaze, "--", true);
    }

    if (s.objects && s.objects.length > 0) {
      setCard(els.cardObjects, s.objects.slice(0, 2).join(", "), false);
    } else {
      setCard(els.cardObjects, "None", true);
    }

    els.violationCount.textContent = String(data.violation_count);
  } catch (e) {
    // Transient network hiccup during polling -- ignore, next tick will retry.
  }
}

function setCard(el, text, ok) {
  el.textContent = text;
  el.classList.toggle("alert", !ok);
}

async function pollEvents() {
  try {
    const res = await fetch(`/events?since=${sinceEventId}`);
    const data = await res.json();
    for (const ev of data.events) {
      sinceEventId = Math.max(sinceEventId, ev.id);
      appendLogLine(els.activityPane, ev);
      if (ev.kind === "alert") {
        appendLogLine(els.alertsPane, ev);
      }
    }
  } catch (e) {
    // ignore transient errors
  }
}

function appendLogLine(pane, ev) {
  const line = document.createElement("div");
  line.className = `log-line ${ev.severity}`;
  line.textContent = `[${ev.time}] ${ev.event_type}: ${ev.details}`;
  pane.appendChild(line);
  pane.scrollTop = pane.scrollHeight;
}

// ---------------- Report modal ----------------
function showReport(data) {
  const summary = data.summary;
  els.reportMeta.textContent =
    `${summary.candidate_id} \u2022 ${summary.duration_seconds}s \u2022 ${summary.total_events} violation(s)`;

  els.reportScore.textContent = `${data.score}/100`;
  els.reportScore.className =
    "score-value " + (data.score >= 70 ? "ok" : data.score >= 40 ? "warn" : "alert");

  els.breakdownTable.innerHTML = "";
  const entries = Object.entries(summary.event_counts || {});
  if (entries.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = "<td>No violations -- clean session</td><td></td>";
    els.breakdownTable.appendChild(tr);
  } else {
    for (const [type, count] of entries) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${type}</td><td>${count}</td>`;
      els.breakdownTable.appendChild(tr);
    }
  }

  els.reportPaths.textContent =
    `Event log: ${summary.log_path}\nScreenshots: ${summary.screenshot_dir}`;

  els.reportModal.classList.remove("hidden");
}

els.closeReportBtn.addEventListener("click", () => {
  els.reportModal.classList.add("hidden");
});
