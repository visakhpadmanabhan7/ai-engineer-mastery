/* AI Engineer Mastery — API client + shared UI helpers.
   Plain script (no modules): all helpers are global. */

const TOKEN_KEY = "aimp_token";
const getToken = () => localStorage.getItem(TOKEN_KEY);
const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
const clearToken = () => localStorage.removeItem(TOKEN_KEY);

/* ---------- theme (light / dark) ---------- */
const THEME_KEY = "aimp_theme";
const prefersLight = () => window.matchMedia && matchMedia("(prefers-color-scheme: light)").matches;
const storedTheme = () => { try { return localStorage.getItem(THEME_KEY); } catch (_) { return null; } };
const getTheme = () => storedTheme() || (prefersLight() ? "light" : "dark");
const currentTheme = () => document.documentElement.getAttribute("data-theme") || getTheme();
const themeIcon = (t) => (t === "light" ? "🌙" : "☀️");
function setTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem(THEME_KEY, t); } catch (_) {}
  document.querySelectorAll(".theme-toggle").forEach((b) => {
    b.textContent = themeIcon(t);
    b.title = t === "light" ? "Switch to dark theme" : "Switch to light theme";
  });
}
function toggleTheme() { setTheme(currentTheme() === "light" ? "dark" : "light"); }
// Ensure the attribute is set even if a page lacks the pre-paint head snippet.
setTheme(currentTheme());

async function api(path, { method = "GET", body, auth = true, raw = false } = {}) {
  const headers = {};
  const isForm = body instanceof FormData;
  if (body && !isForm) headers["Content-Type"] = "application/json";
  if (auth) {
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  const res = await fetch(path, {
    method,
    headers,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    clearToken();
    if (!location.pathname.endsWith("login.html")) location.href = "login.html";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  if (raw) return res;
  if (res.status === 204) return null;
  return res.json();
}

/* ---------- auth ---------- */
async function login(email, password) {
  const fd = new FormData();
  fd.append("username", email);
  fd.append("password", password);
  const t = await api("/api/auth/login", { method: "POST", body: fd, auth: false });
  setToken(t.access_token);
  return t;
}
async function register(email, password, display_name) {
  const t = await api("/api/auth/register", {
    method: "POST",
    body: { email, password, display_name },
    auth: false,
  });
  setToken(t.access_token);
  return t;
}
function logout() {
  clearToken();
  location.href = "login.html";
}
const me = () => api("/api/auth/me");
function requireAuth() {
  if (!getToken()) {
    location.href = "login.html";
    return false;
  }
  return true;
}

/* ---------- content / progress ---------- */
const getMeta = () => api("/api/meta", { auth: false });
const getCurriculum = () => api("/api/curriculum");
const getProgress = () => api("/api/progress");
const setProgress = (lesson_id, completed = true, secs = 0) =>
  api("/api/progress", { method: "POST", body: { lesson_id, completed, time_spent_seconds: secs } });
const getLesson = (day) => api(`/api/lessons/${day}`);

/* ---------- review (SRS) ---------- */
const getReviewQueue = (limit = 20) => api(`/api/review/queue?limit=${limit}`);
const gradeCard = (question_id, rating) =>
  api("/api/review/grade", { method: "POST", body: { question_id, rating } });
const getReviewStats = () => api("/api/review/stats");

/* ---------- AI tutor ---------- */
const tutorGrade = (question, user_answer, opts = {}) =>
  api("/api/tutor/grade", {
    method: "POST",
    body: { kind: opts.kind || "grade", message: question, question, user_answer, lesson_id: opts.lesson_id || null },
  });
const getTutorSessions = () => api("/api/tutor/sessions");
const getTutorMessages = (sid) => api(`/api/tutor/sessions/${sid}/messages`);
const tutorStatus = () => api("/api/tutor/status");

/* Stream a tutor reply. onChunk(text) called per chunk. Returns session id. */
async function tutorStream(body, onChunk) {
  const res = await api("/api/tutor/chat", { method: "POST", body, raw: true });
  const sid = res.headers.get("X-Session-Id");
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    onChunk(dec.decode(value, { stream: true }));
  }
  return sid;
}

/* ---------- notes / analytics ---------- */
const createNote = (content, lesson_id = null) =>
  api("/api/notes", { method: "POST", body: { content, lesson_id } });
const getNotes = (lesson_id) => api(`/api/notes${lesson_id ? `?lesson_id=${lesson_id}` : ""}`);
const getAnalytics = () => api("/api/analytics");

/* ---------- shared UI ---------- */
function renderNav(active) {
  const link = (id, href, label, badge = "") =>
    `<a href="${href}" class="${active === id ? "active" : ""}">${label}${badge}</a>`;
  document.body.insertAdjacentHTML(
    "afterbegin",
    `<div class="topbar"><div class="inner">
       <a class="brand" href="index.html" style="text-decoration:none"><span class="dot"></span> AI Engineer Mastery</a>
       <nav class="navlinks">
         ${link("dash", "index.html", "Dashboard")}
         ${link("review", "review.html", "Review", ' <span id="navDue" class="nav-badge"></span>')}
         ${link("tutor", "tutor.html", "AI Tutor")}
         ${link("mock", "mock.html", "Mock")}
         ${link("analytics", "analytics.html", "Analytics")}
         <span class="nav-streak" id="navStreak"></span>
         <button class="theme-toggle" onclick="toggleTheme()" aria-label="Toggle light/dark theme">${themeIcon(currentTheme())}</button>
         <a href="#" onclick="logout();return false;" class="nav-logout">Sign out</a>
       </nav>
     </div></div>`
  );
  getReviewStats()
    .then((s) => {
      const b = document.getElementById("navDue");
      if (b && s.due_now > 0) b.textContent = s.due_now;
    })
    .catch(() => {});
  me()
    .then((u) => {
      const el = document.getElementById("navStreak");
      if (el) el.innerHTML = `&#128293; ${u.current_streak}`;
      el && el.setAttribute("title", `Streak: ${u.current_streak} days (best ${u.longest_streak})`);
    })
    .catch(() => {});
}

const escapeHtml = (s) =>
  (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const qs = (k) => new URLSearchParams(location.search).get(k);
function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2600);
}
