import { q } from './lib/dom.js';
import { escapeHtml, errMsg, setStatus } from './util.js';

// ---- the active corpus, and a fetch that is scoped to it ------------------ //
export let CORPUS = null;   // the active corpus id; null until bootLibrary, or when there is none
export let LIBRARY = null;  // the last /api/library answer

const UNSCOPED = /^\/api\/(library|corpora|ping|windows)(?=$|[/?#])/;

/** /api/x becomes /api/<CORPUS>/x, except for the library's own routes. */
export function scopeURL(url) {
  if (typeof url !== "string" || !url.startsWith("/api/") || UNSCOPED.test(url)) return url;
  return CORPUS ? `/api/${CORPUS}${url.slice(4)}` : url;
}

const origFetch = window.fetch.bind(window);
window.fetch = (url, opts = {}) => {
  const method = (opts.method || "GET").toUpperCase();
  if (method === "GET" || method === "HEAD") return origFetch(scopeURL(url), opts);
  const headers = new Headers(opts.headers);
  headers.set("X-Tilia-Library", "1");
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  return origFetch(scopeURL(url), { ...opts, headers });
};

function loadPage(corpus) {
  const url = new URL(location.href);
  if (corpus) url.searchParams.set("corpus", corpus);
  else url.searchParams.delete("corpus");
  location.href = url.toString();
}

export async function bootLibrary() {
  const r = await fetch("/api/library");
  const data = await r.json().catch(() => null);
  if (!r.ok) { setStatus(errMsg(r.status, data), "error"); return; }
  LIBRARY = data;
  const corpora = data.corpora;
  if (!corpora.length) {
    for (const sel of ["#corpus-pick", "#corpus-remove", "#corpus-path", "#tabs"]) q(document, sel).hidden = true;
    q(document, "#how-to-add code").textContent = data.how_to_add;
    q(document, "#how-to-add").hidden = false;
    return;
  }
  const want = new URLSearchParams(location.search).get("corpus");
  const active = corpora.find(c => c.id === want) || corpora.find(c => c.id === data.last_corpus) || corpora[0];
  CORPUS = active.id;
  buildPicker(corpora, active);
  q(document, "#corpus-path").textContent = active.path;
  const notices = q(document, "#notices");
  notices.innerHTML = data.notices.map(n => `<div>${escapeHtml(n)}</div>`).join("");
}

function buildPicker(corpora, active) {
  const pick = /** @type {HTMLSelectElement} */ (q(document, "#corpus-pick"));
  pick.innerHTML = corpora.map(c => {
    const name = c.available ? c.name : `${c.name} (unavailable)`;
    return `<option value="${escapeHtml(c.id)}"${c.id === active.id ? " selected" : ""}>${escapeHtml(name)}</option>`;
  }).join("");
  pick.addEventListener("change", async () => {
    const chosen = corpora.find(c => c.id === pick.value);
    const r = await fetch("/api/corpora", { method: "POST", body: JSON.stringify({ path: chosen.path }) });
    if (!r.ok) { setStatus(errMsg(r.status, await r.json().catch(() => null)), "error"); return; }
    loadPage(chosen.id);
  });
  q(document, "#corpus-remove").addEventListener("click", async () => {
    if (!confirm(`Remove “${active.name}” from the library? Its files stay where they are.`)) return;
    const r = await fetch(`/api/corpora/${encodeURIComponent(active.id)}`, { method: "DELETE" });
    if (!r.ok) { setStatus(errMsg(r.status, await r.json().catch(() => null)), "error"); return; }
    loadPage(null);
  });
}
