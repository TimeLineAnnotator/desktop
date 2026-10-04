import { CORPUS } from './corpus.js';
import { downloadCsv, toCsv } from './csv.js';
import { renderFormStrip, stripExtent } from './form-strip.js';
import { closest, evTarget, q, qArea, qInput, qa } from './lib/dom.js';
import { noteGeneration, onRerun } from './liveness.js';
import { notAvailable, panelSection } from './panels.js';
import { query } from './state.js';
import { errMsg, escapeHtml, mmss, setStatus } from './util.js';

const DEBOUNCE_MS = 400;
const LINE_CAP = 20;     // match lines per card
const CARD_CAP = 200;
const ROW_CAP = 1000;    // table rows drawn
const STOPPED = {
  max_matches: "Stopped: more than 20,000 matches; narrow the query.",
  time_limit: "Stopped after 30 seconds; narrow the query.",
  cancelled: "Stopped.",
};
const NOUNS = { match: ["match", "matches"], timeline: ["timeline", "timelines"], file: ["file", "files"] };

const section = () => panelSection("query");
const box = () => qArea(section(), "#ql-box");
const results = () => q(section(), "#ql-results");
const isCards = () => query.result.grain === "match" && !qInput(section(), "#ql-table").checked;
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// ---- remembering the text ------------------------------------------------- //
// localStorage may be refused (private windows), and remembering is a convenience.

const storeKey = () => `tilia-library.query.${CORPUS}`;

function remember(text) {
  try { localStorage.setItem(storeKey(), text); } catch (e) { /* not remembered */ }
}

function remembered() {
  try { return localStorage.getItem(storeKey()) || ""; } catch (e) { return ""; }
}

// ---- the box and the marks behind it -------------------------------------- //

/** A code-point offset (Python's) as a UTF-16 index (JS's) into text. */
function utf16(text, cp) {
  let i = 0, n = 0;
  for (const ch of text) {
    if (n >= cp) break;
    i += ch.length;
    n += 1;
  }
  return i;
}

let marked = null;   // the span marked now, kept so typing doesn't lose it

/** Mirror the text behind the (transparent) textarea, marking [pos, end) when given. */
function setMarks(span) {
  marked = span;
  const text = box().value;
  let html;
  if (span) {
    const pos = Math.min(span.pos, text.length);
    const end = Math.max(pos, Math.min(span.end, text.length));
    // an error at the very end still gets a visible mark: one space past the text
    html = escapeHtml(text.slice(0, pos)) +
      `<mark class="err">${end > pos ? escapeHtml(text.slice(pos, end)) : " "}</mark>` +
      escapeHtml(text.slice(end));
  } else {
    html = escapeHtml(text);
  }
  // the trailing space keeps a final newline's empty line, as the textarea does
  const marks = q(section(), "#ql-marks");
  marks.innerHTML = html + " ";
  marks.scrollTop = box().scrollTop;
}

function clearError() {
  const root = section();
  box().classList.remove("bad");
  q(root, "#ql-error").hidden = true;
  q(root, "#ql-error").textContent = "";
  results().classList.remove("stale");
  setMarks(null);
}

function showError(text, data) {
  const root = section();
  const err = q(root, "#ql-error");
  err.textContent = data && (data.detail || data.error) || errMsg(0, data);
  err.hidden = false;
  box().classList.add("bad");
  if (query.result) results().classList.add("stale");
  if (data && typeof data.pos === "number") {
    const pos = utf16(text, data.pos);
    const end = utf16(text, Math.max(typeof data.end === "number" ? data.end : data.pos + 1, data.pos + 1));
    setMarks({ pos, end: Math.max(end, pos + 1) });
  } else {
    setMarks(null);
  }
}

// ---- running ---------------------------------------------------------------- //

function post(url, body) {
  return fetch(url, { method: "POST", body: JSON.stringify(body) });
}

function setPending(delta) {
  query.pending += delta;
  q(section(), "#ql-stop").hidden = query.pending === 0;
}

function clearResults() {
  const root = section();
  query.result = null;
  clearError();
  q(root, "#ql-explain").textContent = "";
  q(root, "#ql-warnings").hidden = true;
  q(root, "#ql-count").textContent = "";
  q(root, "#ql-stopped").hidden = true;
  qInput(root, "#ql-csv").disabled = true;
  results().innerHTML = "";
  noteGeneration("query", null);
}

let timer = null;

function schedule() {
  clearTimeout(timer);
  timer = setTimeout(run, DEBOUNCE_MS);
}

/** Run the box's query now; only the newest answer is drawn. */
export async function run() {
  clearTimeout(timer);
  const text = box().value;
  const mine = ++query.seq;
  if (!text.trim()) {
    if (query.pending) post("/api/ql-stop", { tab: query.tab }).catch(() => {});
    clearResults();
    return;
  }
  setPending(1);
  let status = 0, data = null;
  try {
    const r = await post("/api/ql", { query: text, tab: query.tab });
    status = r.status;
    data = await r.json().catch(() => null);
  } catch (e) {
    data = { error: `could not reach the server (${e})` };
  } finally {
    setPending(-1);
  }
  if (mine !== query.seq) return;
  if (status === 501) { notAvailable(section(), data && data.needs); return; }
  if (status !== 200) { showError(text, data); return; }
  clearError();
  if (data.generation !== query.contextsGeneration) {
    query.contexts.clear();
    query.contextsGeneration = data.generation;
  }
  query.result = data;
  renderAnswer();
  noteGeneration("query", data.generation);
}

async function stop() {
  const r = await post("/api/ql-stop", { tab: query.tab });
  if (!r.ok) setStatus(errMsg(r.status, await r.json().catch(() => null)), "error");
}

// ---- the answer ------------------------------------------------------------- //

function countText(d) {
  const [one, many] = NOUNS[d.grain] || NOUNS.match;
  let s = plural(d.rows.length, one, many);
  if (d.grain !== "file") s += ` · ${plural(d.files, "file", "files")}`;
  if (d.truncated) s += ` (total ${d.total})`;
  return s;
}

function renderAnswer() {
  const root = section();
  const d = query.result;
  q(root, "#ql-explain").textContent = d.explain || "";
  const warnings = q(root, "#ql-warnings");
  warnings.innerHTML = (d.warnings || []).map(w => `<li>${escapeHtml(String(w))}</li>`).join("");
  warnings.hidden = !(d.warnings || []).length;
  q(root, "#ql-count").textContent = countText(d);
  const stopped = q(root, "#ql-stopped");
  stopped.textContent = STOPPED[d.stopped] || "";
  stopped.hidden = !STOPPED[d.stopped];
  qInput(root, "#ql-csv").disabled = !d.rows.length;
  qInput(root, "#ql-table").disabled = d.grain !== "match";   // timelines and files only have the table
  renderResults();
}

function renderResults() {
  const d = query.result;
  if (!d) return;
  if (cardObserver) { cardObserver.disconnect(); cardObserver = null; }
  if (isCards()) renderCards(); else renderTable();
}

// ---- cards ------------------------------------------------------------------ //

let cardObserver = null;
let cards = [];   // what the drawn cards show, by index

function groupCards(d) {
  const byFile = new Map();
  d.matches.forEach(m => {
    let c = byFile.get(m.file_id);
    if (!c) {
      c = { fileId: m.file_id, name: m.name, matches: [], timelineIds: [], names: new Map() };
      byFile.set(m.file_id, c);
    }
    c.matches.push(m);
    for (const t of m.timelines || []) if (!c.timelineIds.includes(t)) c.timelineIds.push(t);
    for (const u of m.slots.flat()) c.names.set(u.timeline_id, u.timeline);
  });
  return [...byFile.values()];
}

const laneText = u => `${u.timeline} · ${u.level != null ? `level ${u.level}` : u.kind}`;
const isContext = u => u.target === false;

function unitHtml(slot, n, withLane) {
  const tag = `<span class="ql-n ${n === 0 ? "n1" : "n2"}">$${n + 1}</span>`;
  if (!slot.length) return `<span class="ql-unit">${tag}<span class="muted" title="this step matched nothing here">—</span></span>`;
  const ctx = slot.every(isContext);
  const labels = slot.map(u => {
    const t = u.label ? escapeHtml(u.label) : '<span class="muted" title="empty label">∅</span>';
    return isContext(u) && !ctx ? `<span class="ql-ctx">${t}</span>` : t;
  }).join(" → ");
  const u0 = slot[0];
  const at = typeof u0.start === "number"
    ? `<span class="ql-time" title="${u0.start.toFixed(2)} s">${mmss(u0.start)}</span>` : "";
  const lane = withLane ? `<span class="ql-lane">${escapeHtml(laneText(u0))}</span>` : "";
  return `<span class="ql-unit${ctx ? " ql-ctx" : ""}">${tag}${labels}${lane}${at}</span>`;
}

/** One match: each numbered unit; a lane every unit shares is said once, at the end. */
function lineHtml(m) {
  const lanes = m.slots.filter(s => s.length).map(s => laneText(s[0]));
  const shared = lanes.length > 0 && lanes.every(l => l === lanes[0]);
  const body = m.slots.map((s, n) => unitHtml(s, n, !shared)).join("");
  const lane = shared ? `<span class="ql-lane">${escapeHtml(lanes[0])}</span>` : "";
  return `<div class="seq-run ql-run"><span class="seq-labels">${body}</span>${lane}</div>`;
}

function linesHtml(c, i) {
  const list = query.expanded.has(c.fileId) ? c.matches : c.matches.slice(0, LINE_CAP);
  const rest = c.matches.length - list.length;
  return list.map(lineHtml).join("") +
    (rest > 0 ? `<button type="button" class="ql-more" data-i="${i}">show all ${c.matches.length} matches (${rest} more)</button>` : "");
}

function cardHtml(c, i) {
  return `<div class="seq-card ql-card" data-i="${i}" data-file-id="${escapeHtml(String(c.fileId))}">` +
    `<div class="seq-head"><span class="seq-title">${escapeHtml(c.name)}</span>` +
    `<span class="seq-meta">${plural(c.matches.length, "match", "matches")}</span></div>` +
    `<div class="seq-runs">${linesHtml(c, i)}</div>` +
    `<div class="seq-strip-wrap ql-strips"><div class="seq-strip-loading">loading timelines…</div></div></div>`;
}

function renderCards() {
  cards = groupCards(query.result);
  const drawn = cards.slice(0, CARD_CAP);
  const further = cards.length - drawn.length;
  results().innerHTML = drawn.map(cardHtml).join("") +
    (further > 0
      ? `<div class="seq-empty">${further} further files matched but are not drawn — narrow the query, or switch to the table (which the CSV exports whole).</div>`
      : "");
  cardObserver = new IntersectionObserver((entries, obs) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      obs.unobserve(e.target);
      paintStrips(Number(/** @type {HTMLElement} */ (e.target).dataset.i));
    }
  }, { rootMargin: "400px 0px" });
  for (const el of qa(results(), ".ql-card")) cardObserver.observe(el);
}

function context(fileId, ids) {
  const key = `${fileId}|${ids.join(",")}`;
  if (!query.contexts.has(key)) {
    query.contexts.set(key, (async () => {
      try {
        const r = await fetch(`/api/ql-context/${encodeURIComponent(fileId)}?tl=${ids.map(encodeURIComponent).join(",")}`);
        return r.ok ? await r.json() : null;
      } catch (e) {
        return null;
      }
    })());
  }
  return query.contexts.get(key);
}

/** The card's components of one timeline: those that are $1, those of any later slot, and context. */
function slotSets(c, timelineId) {
  const first = new Set(), other = new Set(), ctx = new Set();
  for (const m of c.matches) {
    m.slots.forEach((slot, n) => {
      for (const u of slot) {
        if (u.timeline_id === timelineId) (isContext(u) ? ctx : n === 0 ? first : other).add(u.component_id);
      }
    });
  }
  for (const id of first) { other.delete(id); ctx.delete(id); }
  for (const id of other) ctx.delete(id);
  return { first, other, ctx };
}

async function paintStrips(i) {
  const c = cards[i];
  const el = results().querySelector(`.ql-card[data-i="${i}"]`);
  if (!c || !el) return;
  const data = await context(c.fileId, c.timelineIds);
  // the list may have been redrawn while this loaded
  if (cards[i] !== c || !el.isConnected) return;
  const wrap = q(el, ".ql-strips");
  if (!data) { wrap.innerHTML = '<div class="seq-strip-loading">timelines unavailable</div>'; return; }
  const tls = [...data.timelines].sort((a, b) => c.timelineIds.indexOf(a.id) - c.timelineIds.indexOf(b.id));
  const extent = stripExtent(tls.flatMap(t => t.components), data.end);
  wrap.innerHTML = tls.map(t => {
    const { first, other, ctx } = slotSets(c, t.id);
    const kind = String(t.kind || "").toLowerCase();
    const name = t.name || "(unnamed)";
    return `<div class="ql-tl" data-tl="${escapeHtml(String(t.id))}"><div class="ql-tl-name">${escapeHtml(name)}` +
      (kind && kind !== name.toLowerCase() ? ` <span class="muted">${escapeHtml(kind)}</span>` : "") + "</div>" +
      renderFormStrip(t.components, { highlightIds: first, parentIds: other, contextIds: ctx, extent, rowLabels: t.rows }) +
      "</div>";
  }).join("");
}

// ---- tables ------------------------------------------------------------------ //

function tableHtml(columns, rows, id, valueOf) {
  const head = columns.map(c => `<th>${escapeHtml(c)}</th>`).join("");
  const body = rows.slice(0, ROW_CAP).map(row =>
    "<tr>" + columns.map((c, i) => {
      const v = valueOf(row, c, i);
      return `<td dir="auto">${v == null ? "" : escapeHtml(v)}</td>`;
    }).join("") + "</tr>").join("");
  const note = rows.length > ROW_CAP
    ? `<div class="seq-empty">Showing the first ${ROW_CAP.toLocaleString("en-US")} rows; the CSV has all ${rows.length}.</div>` : "";
  return `<table class="ql-table"${id ? ` id="${id}"` : ""}><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>${note}`;
}

function renderTable() {
  const d = query.result;
  results().innerHTML = tableHtml(d.columns, d.rows, "ql-grid", (row, c) => row[c]);
}

// ---- CSV ---------------------------------------------------------------------- //

function csv() {
  const d = query.result;
  if (!d || !d.rows.length) return;
  downloadCsv(`${CORPUS}-query.csv`, toCsv(d.columns, d.rows));
}

// ---- the SQL ------------------------------------------------------------------ //

async function showSql() {
  const root = section();
  const text = box().value;
  if (!text.trim()) return;
  const r = await post("/api/ql-sql", { query: text });
  const data = await r.json().catch(() => null);
  if (r.status === 501) { notAvailable(root, data && data.needs); return; }
  if (!r.ok) { showError(text, data); return; }
  q(root, "#ql-sql").hidden = false;
  qArea(root, "#ql-sql-box").value = data.sql;
  q(root, "#ql-sql-notes").innerHTML = (data.notes || []).map(n => `<li>${escapeHtml(String(n))}</li>`).join("");
  q(root, "#ql-sql-error").textContent = "";
  q(root, "#ql-sql-result").innerHTML = "";
}

async function runSql() {
  const root = section();
  const error = q(root, "#ql-sql-error");
  const out = q(root, "#ql-sql-result");
  const r = await post("/api/sql", { sql: qArea(root, "#ql-sql-box").value, tab: query.tab });
  const data = await r.json().catch(() => null);
  if (!r.ok) { error.textContent = errMsg(r.status, data); return; }
  error.textContent = "";
  const stopped = STOPPED[data.stopped] ? `<p class="ql-stopped">${escapeHtml(STOPPED[data.stopped])}</p>` : "";
  out.innerHTML = stopped + tableHtml(data.columns, data.rows, "", (row, c, i) => row[i]);
}

// ---- the panel ---------------------------------------------------------------- //

function buildShell() {
  const root = section();
  root.innerHTML =
    '<div class="ql-bar"><div class="ql-box-wrap"><div id="ql-marks" class="ql-backdrop" aria-hidden="true"></div>' +
    '<textarea id="ql-box" placeholder="Write a query" aria-label="Query" spellcheck="false" autocomplete="off"></textarea></div>' +
    '<div class="ql-side"><div class="ql-side-row"><button id="ql-run" type="button">Run</button>' +
    '<button id="ql-stop" type="button" hidden>Stop</button></div>' +
    '<div class="ql-side-row"><label><input id="ql-table" type="checkbox"> Table</label>' +
    '<button id="ql-csv" type="button" disabled>CSV</button><button id="ql-show-sql" type="button">Show SQL</button></div></div></div>' +
    '<div class="ql-info"><p id="ql-error" class="ql-error" role="alert" hidden></p><div id="ql-explain" class="ql-explain"></div>' +
    '<ul id="ql-warnings" class="ql-warnings" hidden></ul>' +
    '<div class="ql-status"><span id="ql-count"></span><span id="ql-stopped" class="ql-stopped" hidden></span></div></div>' +
    '<div id="ql-sql" class="ql-sql" hidden><textarea id="ql-sql-box" aria-label="SQL" spellcheck="false"></textarea>' +
    '<ul id="ql-sql-notes" class="muted"></ul><div><button id="ql-sql-run" type="button">Run SQL</button></div>' +
    '<p id="ql-sql-error" class="ql-error"></p><div id="ql-sql-result"></div></div>' +
    '<div id="ql-results"></div>';
  const area = box();
  area.addEventListener("input", () => {
    remember(area.value);
    setMarks(marked);
    schedule();
  });
  area.addEventListener("scroll", () => { q(root, "#ql-marks").scrollTop = area.scrollTop; });
  area.addEventListener("keydown", e => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); run(); }
  });
  q(root, "#ql-run").addEventListener("click", run);
  q(root, "#ql-stop").addEventListener("click", () => stop().catch(e => setStatus(String(e), "error")));
  q(root, "#ql-table").addEventListener("change", renderResults);
  q(root, "#ql-csv").addEventListener("click", csv);
  q(root, "#ql-show-sql").addEventListener("click", () => showSql().catch(e => setStatus(String(e), "error")));
  q(root, "#ql-sql-run").addEventListener("click", () => runSql().catch(e => setStatus(String(e), "error")));
  results().addEventListener("click", e => {
    const more = closest(evTarget(e), "button.ql-more");
    if (!more) return;
    query.expanded.add(cards[Number(more.dataset.i)].fileId);
    renderResults();
  });
}

/** Build the panel the first time it is shown. */
export function loadQuery() {
  if (!section().querySelector("#ql-box")) buildShell();
  if (!query.restored) {
    query.restored = true;
    box().value = remembered();
    setMarks(null);
  }
}

onRerun("query", run);
