export function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c]));
}

export function setStatus(msg, kind) {
  const el = document.getElementById("status");
  el.textContent = msg;
  el.className = kind || "";
}

/**
 * The message for a failed request.
 * @param {number} status
 * @param {any} data  the parsed body, if it was JSON
 */
export function errMsg(status, data) {
  if (data && typeof data === "object" && typeof data.error === "string") {
    return data.detail ? `${data.error} — ${data.detail}` : data.error;
  }
  return `HTTP ${status}`;
}

/** Seconds as m:ss, for display only: 65.4 is "1:05". */
export function mmss(seconds) {
  const s = Number(seconds);
  if (!isFinite(s)) return "";
  const m = Math.floor(s / 60), ss = Math.floor(s % 60);
  return `${m}:${String(ss).padStart(2, "0")}`;
}
