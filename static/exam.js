// QUESTIONS, DURATION_SECONDS, AUTO_SUBMIT_THRESHOLD are set inline in exam.html

const state = {
  currentIndex: 0,
  answers: {},        // question_id -> selected option index
  marked: new Set(),  // question_ids marked for review
  visited: new Set([0]),
};

let submitted = false;
let sinceEventId = 0;
let warningHideHandle = null;

const els = {
  questionIndexLabel: document.getElementById("questionIndexLabel"),
  questionText: document.getElementById("questionText"),
  optionsList: document.getElementById("optionsList"),
  paletteGrid: document.getElementById("paletteGrid"),
  answeredCount: document.getElementById("answeredCount"),
  notAnsweredCount: document.getElementById("notAnsweredCount"),
  markedCount: document.getElementById("markedCount"),
  violationCountMini: document.getElementById("violationCountMini"),
  timer: document.getElementById("timer"),
  warningBanner: document.getElementById("warningBanner"),
  prevBtn: document.getElementById("prevBtn"),
  clearBtn: document.getElementById("clearBtn"),
  markNextBtn: document.getElementById("markNextBtn"),
  saveNextBtn: document.getElementById("saveNextBtn"),
  submitBtn: document.getElementById("submitBtn"),
  submitModal: document.getElementById("submitModal"),
  submitSummaryText: document.getElementById("submitSummaryText"),
  cancelSubmitBtn: document.getElementById("cancelSubmitBtn"),
  confirmSubmitBtn: document.getElementById("confirmSubmitBtn"),
};

// ---------------- Rendering ----------------
function renderQuestion() {
  const q = QUESTIONS[state.currentIndex];
  els.questionIndexLabel.textContent = `Question ${state.currentIndex + 1} of ${QUESTIONS.length}`;
  els.questionText.textContent = q.text;

  els.optionsList.innerHTML = "";
  q.options.forEach((optionText, i) => {
    const item = document.createElement("label");
    item.className = "option-item";
    if (state.answers[q.id] === i) item.classList.add("selected");

    const input = document.createElement("input");
    input.type = "radio";
    input.name = "option";
    input.checked = state.answers[q.id] === i;
    input.addEventListener("change", () => selectOption(i));

    const span = document.createElement("span");
    span.textContent = optionText;

    item.appendChild(input);
    item.appendChild(span);
    item.addEventListener("click", (e) => {
      if (e.target.tagName !== "INPUT") selectOption(i);
    });

    els.optionsList.appendChild(item);
  });

  renderPalette();
}

function selectOption(optionIndex) {
  const q = QUESTIONS[state.currentIndex];
  state.answers[q.id] = optionIndex;
  saveAnswer(q.id, optionIndex, null);
  renderQuestion();
}

function renderPalette() {
  els.paletteGrid.innerHTML = "";
  let answered = 0, marked = 0;

  QUESTIONS.forEach((q, i) => {
    const cell = document.createElement("button");
    cell.className = "palette-cell";
    cell.textContent = i + 1;

    const isAnswered = state.answers[q.id] !== undefined;
    const isMarked = state.marked.has(q.id);
    const isVisited = state.visited.has(i);

    if (isAnswered) { cell.classList.add("answered"); answered++; }
    else if (isVisited) { cell.classList.add("not-answered"); }
    if (isMarked) { cell.classList.add("marked"); marked++; }
    if (i === state.currentIndex) cell.classList.add("current");

    cell.addEventListener("click", () => goToQuestion(i));
    els.paletteGrid.appendChild(cell);
  });

  els.answeredCount.textContent = answered;
  els.markedCount.textContent = marked;
  els.notAnsweredCount.textContent = QUESTIONS.length - answered;
}

function goToQuestion(index) {
  state.currentIndex = index;
  state.visited.add(index);
  renderQuestion();
}

// ---------------- Navigation buttons ----------------
els.prevBtn.addEventListener("click", () => {
  if (state.currentIndex > 0) goToQuestion(state.currentIndex - 1);
});

els.clearBtn.addEventListener("click", () => {
  const q = QUESTIONS[state.currentIndex];
  delete state.answers[q.id];
  saveAnswer(q.id, null, null);
  renderQuestion();
});

els.markNextBtn.addEventListener("click", () => {
  const q = QUESTIONS[state.currentIndex];
  state.marked.add(q.id);
  saveAnswer(q.id, state.answers[q.id] ?? null, true);
  advance();
});

els.saveNextBtn.addEventListener("click", () => {
  advance();
});

function advance() {
  if (state.currentIndex < QUESTIONS.length - 1) {
    goToQuestion(state.currentIndex + 1);
  } else {
    renderPalette();
  }
}

// ---------------- Backend sync ----------------
async function saveAnswer(questionId, selected, marked) {
  try {
    await fetch("/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_id: questionId, selected: selected, marked: marked }),
    });
  } catch (e) {
    // best-effort autosave; local state is still authoritative for the UI
  }
}

// ---------------- Timer ----------------
async function pollExamStatus() {
  if (submitted) return;
  try {
    const res = await fetch("/exam_status");
    const data = await res.json();
    if (!data.ok) return;

    const mins = String(Math.floor(data.remaining_seconds / 60)).padStart(2, "0");
    const secs = String(Math.floor(data.remaining_seconds % 60)).padStart(2, "0");
    els.timer.textContent = `${mins}:${secs}`;
    els.timer.classList.toggle("low-time", data.remaining_seconds <= 60);

    els.violationCountMini.textContent = data.violation_count;

    if (data.remaining_seconds <= 0) {
      doSubmit("timeout");
      return;
    }
    if (data.violation_count >= AUTO_SUBMIT_THRESHOLD) {
      doSubmit("violations");
      return;
    }
  } catch (e) {
    // transient network hiccup -- next tick retries
  }
}

// ---------------- Violation warnings ----------------
async function pollEvents() {
  if (submitted) return;
  try {
    const res = await fetch(`/events?since=${sinceEventId}`);
    const data = await res.json();
    for (const ev of data.events) {
      sinceEventId = Math.max(sinceEventId, ev.id);
      if (ev.kind === "alert") {
        showWarning(`${ev.event_type.replace(/_/g, " ")}: ${ev.details}`);
      }
    }
  } catch (e) {
    // ignore transient errors
  }
}

function showWarning(text) {
  els.warningBanner.textContent = "\u26A0 " + text;
  els.warningBanner.classList.remove("hidden");
  clearTimeout(warningHideHandle);
  warningHideHandle = setTimeout(() => {
    els.warningBanner.classList.add("hidden");
  }, 5000);
}

// ---------------- Submit ----------------
els.submitBtn.addEventListener("click", () => {
  const answered = parseInt(els.answeredCount.textContent, 10);
  const notAnswered = QUESTIONS.length - answered;
  const marked = state.marked.size;
  els.submitSummaryText.textContent =
    `${answered} answered, ${notAnswered} not answered, ${marked} marked for review. This cannot be undone.`;
  els.submitModal.classList.remove("hidden");
});

els.cancelSubmitBtn.addEventListener("click", () => {
  els.submitModal.classList.add("hidden");
});

els.confirmSubmitBtn.addEventListener("click", () => {
  els.submitModal.classList.add("hidden");
  doSubmit("manual");
});

async function doSubmit(reason) {
  if (submitted) return;
  submitted = true;
  els.submitBtn.disabled = true;
  els.submitBtn.textContent = "Submitting...";

  try {
    const res = await fetch("/submit_exam", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    });
    const data = await res.json();
    if (data.ok) {
      window.location.href = data.redirect;
    } else {
      alert(data.error || "Could not submit the exam.");
      submitted = false;
      els.submitBtn.disabled = false;
      els.submitBtn.textContent = "Submit Exam";
    }
  } catch (e) {
    alert("Network error while submitting. Please try again.");
    submitted = false;
    els.submitBtn.disabled = false;
    els.submitBtn.textContent = "Submit Exam";
  }
}

// ---------------- Init ----------------
renderQuestion();
setInterval(pollExamStatus, 1000);
setInterval(pollEvents, 1500);
pollExamStatus();
