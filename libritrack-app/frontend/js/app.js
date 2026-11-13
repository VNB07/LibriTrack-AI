// Page wiring: login, views, and loading data into tables and forms.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const say = (el, text, ok) => { el.textContent = text; el.className = "msg " + (ok ? "ok" : "warn"); };

function showApp(loggedIn) {
  $("login").hidden = loggedIn;
  $("app").hidden = !loggedIn;
  $("logout").hidden = !loggedIn;
  $("who").textContent = loggedIn ? Session.name : "";
  if (loggedIn) refreshAll();
}

// Login
$("loginForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  try {
    const data = await api("/auth/login", { method: "POST", body: { email: f.get("email"), password: f.get("password") } });
    Session.token = data.token;
    Session.name = data.name;
    showApp(true);
  } catch (err) {
    say($("loginMsg"), err.message, false);
  }
};
$("logout").onclick = () => { Session.token = null; Session.name = null; location.reload(); };

// Views switching
document.querySelectorAll(".tab[data-view]").forEach(btn => btn.onclick = () => {
  document.querySelectorAll(".tab[data-view]").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  btn.classList.add("active");
  $(btn.dataset.view).classList.add("active");
  refreshAll();
});

// Modal viewer for security audit snapshots
window.viewSnapshot = (filename) => {
  if (!filename) return;
  $("modalImg").src = "/api/snapshots/" + encodeURIComponent(filename);
  $("imageModal").classList.add("active");
};
window.closeModal = () => {
  $("imageModal").classList.remove("active");
};

// 1. Dashboard Loaders
async function loadDashboard() {
  const d = await api("/dashboard");
  const statsList = [
    ["Inside now", d.inside],
    ["Active Loans", d.open_loans],
    ["Overdue Loans", d.overdue],
    ["Enrolled Students", d.students]
  ];
  if (d.unattended_books !== undefined) {
    statsList.push(["Unattended sightings", d.unattended_books]);
  }
  $("stats").innerHTML = statsList.map(([label, n]) => `<div class="stat"><b>${n}</b><span>${label}</span></div>`).join("");
}

async function loadInsideStudents() {
  const inside = await api("/students/inside");
  $("insideStudentsList").innerHTML = inside.length ? `
    <table>
      <thead>
        <tr>
          <th>Student Name</th>
          <th>Student ID</th>
          <th>Check-in Time</th>
          <th>Verification Method</th>
        </tr>
      </thead>
      <tbody>
        ${inside.map(s => `<tr>
          <td><b>${esc(s.name)}</b></td>
          <td>${esc(s.student_code)}</td>
          <td>${esc(new Date(s.entered_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))}</td>
          <td><span class="badge-in">${esc(s.source === 'face' ? 'Face Recognition' : 'Manual Entry')}</span></td>
        </tr>`).join("")}
      </tbody>
    </table>`
    : "<p class='hint'>No students currently inside the library.</p>";
}

async function loadNameLog() {
  const rows = await api("/events/recent");
  $("nameLog").innerHTML = rows.length ? rows.map(r => `
    <div class="logrow">
      <span class="small">${esc(new Date(r.at).toLocaleTimeString())}</span>
      <b>${esc(r.name)}</b> (${esc(r.student_code || '')})
      <span class="small">${esc(r.kind)} via ${esc(r.source)}</span>
    </div>`).join("")
    : "<p class='hint'>No activity yet.</p>";
}

// 2. Students Loader
async function loadStudents() {
  const students = await api("/students");
  const options = students.map(s => `<option value="${s.id}">${esc(s.name)} (${esc(s.student_code)})</option>`).join("");
  document.querySelectorAll(".studentSelect").forEach(sel => sel.innerHTML = options);

  $("studentList").innerHTML = students.length ? `
    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Student ID</th>
          <th>Consent</th>
          <th>Photos Enrolled</th>
          <th>Current Status</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        ${students.map(s => `<tr>
          <td><b>${esc(s.name)}</b></td>
          <td>${esc(s.student_code)}</td>
          <td>${s.consent_at ? "Yes" : "No"}</td>
          <td>${s.photos ? `${s.photos} photo(s)` : '<span class="hint">None</span>'}</td>
          <td>${s.last_event === "entry" ? '<span class="badge-in">Inside</span>' : '<span class="badge-out">Outside</span>'}</td>
          <td>${s.photos ? `<button class="ghost" onclick="withdraw(${s.id})">Withdraw Face</button>` : ""}</td>
        </tr>`).join("")}
      </tbody>
    </table>` : "<p class='hint'>No students registered yet.</p>";
}

// 3. Loans & Who Borrowed What
async function loadLoans() {
  const [loans, unattended] = await Promise.all([api("/loans"), api("/unattended-books")]);

  // Active Loans Table
  $("loanList").innerHTML = loans.length ? `
    <table>
      <thead>
        <tr>
          <th>Borrower</th>
          <th>Student ID</th>
          <th>Book Title</th>
          <th>Barcode</th>
          <th>Borrowed At</th>
          <th>Due Date</th>
          <th>Snapshot Audit</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>
        ${loans.map(l => `<tr>
          <td><b>${esc(l.student)}</b></td>
          <td>${esc(l.student_code)}</td>
          <td>${esc(l.title)}</td>
          <td><code>${esc(l.barcode)}</code></td>
          <td>${esc(new Date(l.borrowed_at).toLocaleDateString())}</td>
          <td>${esc(l.due_at.slice(0, 10))} ${l.overdue ? '<span class="badge late">Overdue</span>' : ''}</td>
          <td>${l.snapshot_path ? `<img class="snapshot-thumb" src="/api/snapshots/${esc(l.snapshot_path)}" onclick="viewSnapshot('${esc(l.snapshot_path)}')">` : '<span class="hint">Manual</span>'}</td>
          <td><button class="ghost" onclick="quickReturn('${esc(l.barcode)}')">Return</button></td>
        </tr>`).join("")}
      </tbody>
    </table>`
    : "<p class='hint'>No active book loans.</p>";

  // Unattended Sightings Table
  $("unattendedList").innerHTML = unattended.length ? `
    <table>
      <thead>
        <tr>
          <th>Detected Time</th>
          <th>Book Title</th>
          <th>Barcode</th>
          <th>Snapshot Frame</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>
        ${unattended.map(u => `<tr>
          <td>${esc(new Date(u.detected_at).toLocaleTimeString())}</td>
          <td><b>${esc(u.title || "Unregistered")}</b></td>
          <td><code>${esc(u.barcode)}</code></td>
          <td>${u.snapshot_path ? `<img class="snapshot-thumb" src="/api/snapshots/${esc(u.snapshot_path)}" onclick="viewSnapshot('${esc(u.snapshot_path)}')">` : "None"}</td>
          <td><button class="ghost" onclick="dismissUnattended(${u.id})">Dismiss</button></td>
        </tr>`).join("")}
      </tbody>
    </table>`
    : "<p class='hint'>No unattended book alerts.</p>";
}

window.quickReturn = async (barcode) => {
  try {
    await api("/loans/return", { method: "POST", body: { barcode } });
    loadLoans();
    loadDashboard();
  } catch (err) { alert(err.message); }
};

window.dismissUnattended = async (id) => {
  try {
    await api(`/unattended-books/${id}/dismiss`, { method: "POST" });
    loadLoans();
    loadDashboard();
  } catch (err) { alert(err.message); }
};

// 4. Book Inventory
async function loadBooks() {
  const books = await api("/books");
  $("bookList").innerHTML = books.length ? `
    <table>
      <thead>
        <tr>
          <th>Title</th>
          <th>Author</th>
          <th>Barcode</th>
          <th>Available / Total Copies</th>
          <th>Cover Status</th>
        </tr>
      </thead>
      <tbody>
        ${books.map(b => `<tr>
          <td><b>${esc(b.title)}</b></td>
          <td>${esc(b.author || '-')}</td>
          <td><code>${esc(b.barcode)}</code></td>
          <td>${b.available} / ${b.copies} available</td>
          <td>${b.cover_path ? '<span class="badge-in">Visual Scan Ready</span>' : '<span class="hint">Barcode only</span>'}</td>
        </tr>`).join("")}
      </tbody>
    </table>`
    : "<p class='hint'>No books registered yet.</p>";
}

// 5. Uploads
async function loadMyUploads() {
  const photos = await api("/me/photos");
  $("myPhotos").innerHTML = photos.length ? `
    <table>
      <thead><tr><th>Student</th><th>Student ID</th><th>Upload Timestamp</th></tr></thead>
      <tbody>
        ${photos.map(p => `<tr><td><b>${esc(p.student)}</b></td><td>${esc(p.student_code)}</td><td>${esc(p.created_at)}</td></tr>`).join("")}
      </tbody>
    </table>`
    : "<p class='hint'>You have not uploaded any photos yet.</p>";
}

function refreshAll() {
  const active = document.querySelector(".view.active").id;
  const loaders = {
    dashboard: () => Promise.all([loadDashboard(), loadInsideStudents(), loadNameLog()]),
    loansView: loadLoans,
    students: loadStudents,
    books: loadBooks,
    uploads: loadMyUploads
  };
  loadStudents().catch(() => {});
  if (loaders[active]) loaders[active]().catch(err => console.error(err));
}

// Forms
$("manualForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  try {
    await api("/events", { method: "POST", body: { student_id: +f.get("student_id"), kind: f.get("kind"), source: "manual" } });
    say($("manualMsg"), "Recorded successfully.", true);
    refreshAll();
  } catch (err) { say($("manualMsg"), err.message, false); }
};

$("addStudentForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  try {
    await api("/students", { method: "POST", body: {
      code: f.get("code"), name: f.get("name"), email: f.get("email") || null, consent: f.get("consent") === "on"
    }});
    e.target.reset();
    say($("addStudentMsg"), "Student registered with recorded consent.", true);
    refreshAll();
  } catch (err) { say($("addStudentMsg"), err.message, false); }
};

$("uploadForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  try {
    await api("/students/" + f.get("student_id") + "/photos", { method: "POST", form: f });
    e.target.file.value = "";
    say($("uploadMsg"), "Face photo saved and enrolled.", true);
    refreshAll();
  } catch (err) { say($("uploadMsg"), err.message, false); }
};

window.withdraw = async (studentId) => {
  if (!confirm("Delete face templates for this student and withdraw consent?")) return;
  try {
    const r = await api("/students/" + studentId + "/photos", { method: "DELETE" });
    alert(r.message);
    refreshAll();
  } catch (err) { alert(err.message); }
};

$("addBookForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  try {
    await api("/books", { method: "POST", form: f });
    e.target.reset();
    say($("bookMsg"), "Book registered into catalog.", true);
    refreshAll();
  } catch (err) { say($("bookMsg"), err.message, false); }
};

$("checkoutForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  try {
    const r = await api("/loans/checkout", { method: "POST", body: { barcode: f.get("barcode"), student_id: +f.get("student_id") } });
    say($("loanMsg"), "Checked out. Due " + r.due_at.slice(0, 10) + ".", true);
    refreshAll();
  } catch (err) { say($("loanMsg"), err.message, false); }
};

$("returnForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  try {
    await api("/loans/return", { method: "POST", body: { barcode: f.get("barcode") } });
    e.target.reset();
    say($("loanMsg"), "Book marked as returned.", true);
    refreshAll();
  } catch (err) { say($("loanMsg"), err.message, false); }
};

// URL Hash routing
showApp(!!Session.token);
const startView = location.hash.slice(1);
const startTab = document.querySelector('.tab[data-view="' + startView + '"]');
if (startView && startTab && Session.token) startTab.click();

// 3-second live refresh for Dashboard and Inside Students
setInterval(() => {
  const onDashboard = $("dashboard").classList.contains("active");
  if (Session.token && onDashboard && !$("app").hidden) {
    loadDashboard().catch(() => {});
    loadInsideStudents().catch(() => {});
    loadNameLog().catch(() => {});
  }
}, 3000);