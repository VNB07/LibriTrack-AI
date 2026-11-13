// Live camera controller supporting Attendance Mode and Two-Stage Guided Borrow Mode.
if (!Session.token) location.href = "index.html";

const camBtn = document.getElementById("camBtn");
const camVideo = document.getElementById("camVideo");
const overlay = document.getElementById("overlay");
const btnModeAttendance = document.getElementById("btnModeAttendance");
const btnModeBorrow = document.getElementById("btnModeBorrow");
const borrowBanner = document.getElementById("borrowBanner");
const borrowStepText = document.getElementById("borrowStepText");
const btnResetBorrow = document.getElementById("btnResetBorrow");
const attendanceLegend = document.getElementById("attendanceLegend");

const FRAME_GAP_MS = 320;
let camStream = null;
let camTimer = null;
let sending = false;

// Modes: "attendance" | "borrow"
let currentMode = "attendance";

// Borrow Mode States: "VERIFY_STUDENT" | "SCAN_BOOK" | "SUCCESS"
let borrowState = "VERIFY_STUDENT";
let activeStudent = null;

document.getElementById("who").textContent = Session.name || "";
document.getElementById("logout").onclick = () => {
  Session.token = null; Session.name = null; location.href = "index.html";
};

function camSay(text, ok) {
  const el = document.getElementById("camMsg");
  el.textContent = text;
  el.className = "msg " + (ok ? "ok" : "warn");
}

// Mode Selection Handlers
btnModeAttendance.onclick = () => {
  currentMode = "attendance";
  btnModeAttendance.classList.add("active");
  btnModeBorrow.classList.remove("active");
  borrowBanner.style.display = "none";
  attendanceLegend.style.display = "flex";
  camSay("Switched to Attendance Mode.", true);
  clearOverlay();
};

btnModeBorrow.onclick = () => {
  currentMode = "borrow";
  btnModeBorrow.classList.add("active");
  btnModeAttendance.classList.remove("active");
  borrowBanner.style.display = "flex";
  attendanceLegend.style.display = "none";
  resetBorrowSession();
  camSay("Switched to Borrow Mode. Stand in front of camera to verify identity.", true);
  clearOverlay();
};

btnResetBorrow.onclick = resetBorrowSession;

function resetBorrowSession() {
  borrowState = "VERIFY_STUDENT";
  activeStudent = null;
  borrowBanner.className = "kiosk-status";
  borrowStepText.textContent = "Step 1: Stand in front of camera to verify identity";
  btnResetBorrow.style.display = "none";
  clearOverlay();
}

function clearOverlay() {
  overlay.getContext("2d").clearRect(0, 0, overlay.width, overlay.height);
}

camBtn.onclick = () => (camStream ? stopCamera() : startCamera());

async function startCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    return camSay("This browser cannot access the camera. Use Chrome or Edge.", false);
  }
  camSay("Requesting camera permission. Click Allow in the browser prompt.", true);
  try {
    camStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
  } catch (e) {
    return camSay("Camera error: " + e.name, false);
  }
  camVideo.srcObject = camStream;
  await camVideo.play();
  camBtn.textContent = "Turn off camera";
  camSay("Camera on.", true);
  camTimer = setInterval(tickFrame, FRAME_GAP_MS);
}

function stopCamera() {
  clearInterval(camTimer);
  if (camStream) camStream.getTracks().forEach(t => t.stop());
  camStream = null;
  camVideo.srcObject = null;
  clearOverlay();
  camBtn.textContent = "Turn on camera";
  camSay("Camera is off.", true);
}

async function tickFrame() {
  if (sending || !camVideo.videoWidth || borrowState === "SUCCESS") return;
  sending = true;

  try {
    const canvas = document.createElement("canvas");
    canvas.width = camVideo.videoWidth;
    canvas.height = camVideo.videoHeight;
    canvas.getContext("2d").drawImage(camVideo, 0, 0);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/jpeg", 0.85));

    const form = new FormData();
    form.append("file", blob, "frame.jpg");

    if (currentMode === "attendance") {
      await processAttendance(form);
    } else {
      await processBorrowMode(form);
    }
  } catch (err) {
    camSay("Error: " + err.message, false);
  } finally {
    sending = false;
  }
}

// Attendance processing: continuous entry recording
async function processAttendance(form) {
  const result = await api("/recognise", { method: "POST", form });
  renderAttendanceBoxes(result);
  const names = [...new Set(result.faces.filter(f => f.student_id !== null).map(f => f.name))];
  camSay(names.length ? "Recognised: " + names.join(", ") : "Camera on. No enrolled faces in view.", true);
}

// Borrow Mode state machine
async function processBorrowMode(form) {
  if (borrowState === "VERIFY_STUDENT") {
    const result = await api("/borrow/verify-student", { method: "POST", form });
    renderAttendanceBoxes(result);

    if (result.verified && result.student) {
      activeStudent = result.student;
      borrowState = "SCAN_BOOK";
      borrowBanner.className = "kiosk-status step2";
      borrowStepText.innerHTML = `&#10003; <b>${activeStudent.name}</b> verified! Now hold book cover to the camera.`;
      btnResetBorrow.style.display = "inline-block";
      camSay(`Verified ${activeStudent.name}. Ready for book.`, true);
    }
  } else if (borrowState === "SCAN_BOOK") {
    form.append("student_id", activeStudent.id);
    const result = await api("/borrow/scan-book", { method: "POST", form });

    if (result.matched) {
      borrowState = "SUCCESS";
      renderBookBox(result);
      borrowBanner.className = "kiosk-status success";
      borrowStepText.innerHTML = `&#127881; Borrowed: <b>${result.title}</b>! Snapshot captured.`;
      camSay(`Loan recorded: "${result.title}" checked out to ${result.student_name}.`, true);

      // Auto-reset back to Step 1 after 3.5 seconds for the next student
      setTimeout(() => {
        resetBorrowSession();
      }, 3500);
    } else {
      clearOverlay();
      camSay(`Looking for registered book cover held by ${activeStudent.name}...`, true);
    }
  }
}

function renderAttendanceBoxes(result) {
  overlay.width = camVideo.clientWidth;
  overlay.height = camVideo.clientHeight;
  const ctx = overlay.getContext("2d");
  ctx.clearRect(0, 0, overlay.width, overlay.height);

  const sx = overlay.width / result.width;
  const sy = overlay.height / result.height;
  ctx.lineWidth = 3;
  ctx.font = "15px system-ui";

  for (const face of (result.faces || [])) {
    const [top, right, bottom, left] = face.box;
    const x = left * sx, y = top * sy;
    const w = (right - left) * sx, h = (bottom - top) * sy;
    const isEnrolled = face.student_id !== null;
    const color = isEnrolled ? "#1f8a4c" : "#b54708";

    ctx.strokeStyle = color;
    ctx.strokeRect(x, y, w, h);
    ctx.fillStyle = color;
    ctx.fillText(face.name || "Unknown", x, Math.max(y - 6, 14));
  }
}

function renderBookBox(result) {
  overlay.width = camVideo.clientWidth;
  overlay.height = camVideo.clientHeight;
  const ctx = overlay.getContext("2d");
  ctx.clearRect(0, 0, overlay.width, overlay.height);

  const sx = overlay.width / result.width;
  const sy = overlay.height / result.height;
  const [top, right, bottom, left] = result.box;
  const x = left * sx, y = top * sy;
  const w = (right - left) * sx, h = (bottom - top) * sy;

  ctx.strokeStyle = "#0284c7";
  ctx.lineWidth = 4;
  ctx.strokeRect(x, y, w, h);
  ctx.fillStyle = "#0284c7";
  ctx.font = "bold 16px system-ui";
  ctx.fillText(`Book: ${result.title} (Confirmed)`, x, Math.max(y - 8, 16));
}