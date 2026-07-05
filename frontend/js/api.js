const API_BASE = "";

function getToken() {
  return localStorage.getItem("token");
}

function setAuth(token, user) {
  localStorage.setItem("token", token);
  localStorage.setItem("user", JSON.stringify(user));
  showAdminLink();
}

function clearAuth() {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
  showAdminLink();
}

function getUser() {
  try { return JSON.parse(localStorage.getItem("user")); } catch { return null; }
}

async function validateSession() {
  const token = getToken();
  if (!token) return false;

  try {
    await apiFetch("/auth/me");
    return true;
  } catch {
    clearAuth();
    return false;
  }
}

async function requireAuth() {
  if (!getToken()) {
    window.location.href = "/index.html";
    return false;
  }
  try {
    await apiFetch("/auth/me");
  } catch {
    clearAuth();
    return false;
  }
  showAdminLink();
  return true;
}

async function redirectIfLoggedIn() {
  if (!getToken()) return;
  const valid = await validateSession();
  if (valid) {
    window.location.href = "/home.html";
  }
}

function showAdminLink() {
  const adminLink = document.getElementById("admin-link");
  if (!adminLink) return;
  const user = getUser();
  adminLink.style.display = user && user.is_admin ? "inline-block" : "none";
}

async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(API_BASE + path, { ...options, headers });

  if (res.status === 401) {
    clearAuth();
    window.location.href = "/index.html";
    return null;
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || "An unexpected error occurred.");
  }
  return data;
}

async function apiUpload(path, formData) {
  const token = getToken();
  const headers = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(API_BASE + path, { method: "POST", headers, body: formData });
  if (res.status === 401) { clearAuth(); window.location.href = "/index.html"; return null; }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Upload failed.");
  return data;
}

function formatDate(str) {
  if (!str) return "-";
  const d = new Date(str);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function formatCurrency(n) {
  if (n == null) return "-";
  return "Rs." + Number(n).toFixed(2);
}

function statusBadge(status) {
  return `<span class="badge badge-${status}">${status.replace("_", " ")}</span>`;
}

function starsHtml(score, max = 5) {
  let html = '<span class="stars">';
  for (let i = 1; i <= max; i++) {
    html += `<span class="star${i <= Math.round(score) ? " filled" : ""}">&#9733;</span>`;
  }
  html += "</span>";
  return html;
}

function esc(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function showAlert(container, msg, type = "error") {
  container.innerHTML = `<div class="alert alert-${type}">${msg}</div>`;
}

function clearAlert(container) {
  container.innerHTML = "";
}

function setLoading(btn, loading, label = "Save") {
  if (loading) {
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span>`;
  } else {
    btn.disabled = false;
    btn.textContent = label;
  }
}

function logout() {
  clearAuth();
  window.location.href = "/index.html";
}
