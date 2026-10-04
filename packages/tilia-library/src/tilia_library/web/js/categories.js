import { closest, evTarget, q, qInput, qa } from './lib/dom.js';
import { noteGeneration, onRerun } from './liveness.js';
import { notAvailable, panelSection, showPanel } from './panels.js';
import { play } from './playback.js';
import { loadQuery } from './query.js';
import { openPreview } from './ql-edit.js';
import { query } from './state.js';
import { errMsg, escapeHtml, setStatus } from './util.js';

const TOP = 15;        // categories shown until "more"
const ROW_CAP = 1000;  // table rows drawn
const OTHER = "other"; // the group of a category without one

const section = () => panelSection("categories");
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

let answer = { grammar: false, categories: [] };   // the last /api/categories answer
let selected = [];       // the chosen categories, in the order chosen
let expanded = false;    // every category, not only the TOP most frequent
let filter = "";
let seq = 0;             // the newest components request; an older answer is dropped
let listed = null;       // the last components answer

/** Case-insensitive subsequence test: do the letters of `typed` (spaces ignored) appear in order in `name`? */
function fuzzyMatch(typed, name) {
  const letters = typed.toLowerCase().replace(/\s+/g, "");
  const s = name.toLowerCase();
  let i = 0;
  for (let j = 0; j < s.length && i < letters.length; j++) if (s[j] === letters[i]) i++;
  return i === letters.length;
}

async function post(url, body) {
  try {
    const r = await fetch(url, { method: "POST", body: JSON.stringify(body) });
    return [r.status, await r.json().catch(() => null)];
  } catch (e) {
    return [0, { error: `could not reach the server (${e})` }];
  }
}

// ---- the chips -------------------------------------------------------------- //

function chipHtml({ category, n }) {
  return `<button type="button" class="chip${selected.includes(category) ? " active" : ""}" data-cat="${escapeHtml(category)}">` +
    `${escapeHtml(category)} <span class="n">${n}</span></button>`;
}

function groupedHtml(rows) {
  const groups = new Map();
  for (const row of rows) {
    const name = row.group || OTHER;
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(row);
  }
  return [...groups].map(([name, items]) =>
    `<div class="chip-group"><span class="chip-group-name">${escapeHtml(name)}</span>${items.map(chipHtml).join("")}</div>`
  ).join("");
}

function renderChips() {
  const all = answer.categories;
  const typed = filter.trim();
  const shown = typed ? all.filter(c => fuzzyMatch(typed, c.category))
    : expanded ? all : all.slice(0, TOP);
  let html = answer.grammar ? groupedHtml(shown) : shown.map(chipHtml).join("");
  if (typed && !shown.length) html = `<span class="muted">No category matches “${escapeHtml(typed)}”.</span>`;
  if (!typed && all.length > TOP) {
    html += `<button type="button" id="cat-more" class="chip more">${expanded ? "Fewer" : `+${all.length - TOP} more`}</button>`;
  }
  q(section(), "#cat-chips").innerHTML = html;
}

function syncControls() {
  const root = section();
  q(root, "#cat-mode").hidden = selected.length < 2;
  q(root, "#cat-clear").hidden = !selected.length;
  q(root, "#cat-edit").hidden = !selected.length;
  const all = /** @type {HTMLOptionElement} */ (q(root, '#cat-mode option[value="all"]'));
  all.disabled = !answer.grammar;
  all.title = answer.grammar ? "" : "needs a label grammar";
  if (!answer.grammar) qInput(root, "#cat-mode").value = "any";
}

function onChipClick(e) {
  const target = evTarget(e);
  if (closest(target, "#cat-more")) {
    expanded = !expanded;
    renderChips();
    return;
  }
  const chip = closest(target, "button.chip[data-cat]");
  if (!chip) return;
  const category = chip.dataset.cat;
  if (e.shiftKey || e.ctrlKey || e.metaKey) {
    selected = selected.includes(category) ? selected.filter(c => c !== category) : [...selected, category];
  } else if (selected.length === 1 && selected[0] === category) {
    selected = [];
  } else {
    selected = [category];
  }
  selectionChanged();
}

// ---- the components of the selection ------------------------------------------ //

const mode = () => qInput(section(), "#cat-mode").value;
const fold = () => qInput(section(), "#cat-fold").checked;
const selectionBody = () => ({ categories: selected, mode: mode(), fold: fold(), tab: query.tab });

function showError(text) {
  const el = q(section(), "#cat-error");
  el.textContent = text;
  el.hidden = !text;
}

function clearList() {
  const root = section();
  listed = null;
  q(root, "#cat-statement").innerHTML = "";
  q(root, "#cat-count").textContent = "";
  q(root, "#cat-list").innerHTML = "";
}

function tableHtml(d) {
  const head = d.columns.map(c => `<th>${escapeHtml(c)}</th>`).join("");
  const body = d.rows.slice(0, ROW_CAP).map(row =>
    `<tr>${d.columns.map(c => `<td dir="auto">${row[c] == null ? "" : escapeHtml(row[c])}</td>`).join("")}</tr>`).join("");
  const note = d.rows.length > ROW_CAP ? `<div class="muted">Showing the first ${ROW_CAP} of ${d.rows.length} rows.</div>` : "";
  return `<table id="cat-grid" class="ql-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>${note}`;
}

function showList(d) {
  const root = section();
  listed = d;
  q(root, "#cat-statement").innerHTML = `<code dir="auto">${escapeHtml(d.statement)}</code>`;
  q(root, "#cat-count").textContent = `${plural(d.rows.length, "component", "components")} · ${plural(d.files, "file", "files")}`;
  q(root, "#cat-list").innerHTML = tableHtml(d);
}

async function loadComponents() {
  const mine = ++seq;
  const [status, data] = await post("/api/categories/components", selectionBody());
  if (mine !== seq) return;
  showError("");
  if (status === 501) { notAvailable(section(), data && data.needs); return; }
  if (status !== 200) {
    clearList();
    showError(errMsg(status, data));
    return;
  }
  showList(data);
}

function selectionChanged() {
  renderChips();
  syncControls();
  showError("");
  if (selected.length) {
    loadComponents().catch(e => setStatus(String(e), "error"));
  } else {
    seq++;
    clearList();
  }
}

function onListDblClick(e) {
  const row = closest(evTarget(e), "#cat-grid tbody tr");
  const m = row && listed && listed.matches && listed.matches[row.sectionRowIndex];
  if (!m) return;
  getSelection().removeAllRanges();
  play(m.file_id, m.name, m.start, m.end);
}

// ---- the edit ------------------------------------------------------------------ //

function syncOp() {
  const root = section();
  const replace = qInput(root, "#cat-op").value === "replace";
  for (const id of ["#cat-pattern", "#cat-replacement"]) q(root, id).hidden = !replace;
  q(root, "#cat-value").hidden = replace;
}

function editBody() {
  const root = section();
  const body = { ...selectionBody(), op: qInput(root, "#cat-op").value, field: qInput(root, "#cat-field").value };
  if (body.op === "replace") {
    body.pattern = qInput(root, "#cat-pattern").value;
    body.replacement = qInput(root, "#cat-replacement").value;
  } else {
    body.value = qInput(root, "#cat-value").value;
  }
  return body;
}

async function previewEdit() {
  const button = /** @type {HTMLButtonElement} */ (q(section(), "#cat-preview"));
  button.disabled = true;
  let status, data;
  try {
    [status, data] = await post("/api/categories/edit", editBody());
  } finally {
    button.disabled = false;
  }
  showError("");
  if (status === 501) { showError(`Not available yet: this needs ${data && data.needs}.`); return; }
  if (status !== 200) { showError(errMsg(status, data)); return; }
  showPanel("query");
  loadQuery();
  await openPreview(data);
}

// ---- the panel ----------------------------------------------------------------- //

function buildShell() {
  const root = section();
  root.innerHTML =
    '<div class="cat-bar"><input id="cat-search" type="search" placeholder="Find a category" aria-label="Find a category">' +
    '<label><input id="cat-fold" type="checkbox"> Fold subtypes</label>' +
    '<select id="cat-mode" aria-label="Mode" hidden><option value="any">any</option><option value="all">all</option></select>' +
    '<button id="cat-clear" type="button" hidden>Clear</button></div>' +
    '<div id="cat-chips" class="chips"></div>' +
    '<p id="cat-error" class="ql-error" role="alert" hidden></p>' +
    '<div id="cat-statement"></div><div id="cat-count" class="muted"></div>' +
    '<div id="cat-edit" class="cat-edit" hidden>' +
    '<select id="cat-op" aria-label="Operation"><option value="set">set</option><option value="replace">replace</option></select>' +
    '<select id="cat-field" aria-label="Field"><option value="label">label</option><option value="color">color</option><option value="comments">comments</option></select>' +
    '<input id="cat-value" aria-label="Value" placeholder="new value">' +
    '<input id="cat-pattern" placeholder="regular expression" aria-label="Pattern" hidden>' +
    '<input id="cat-replacement" placeholder="replacement" aria-label="Replacement" hidden>' +
    '<button id="cat-preview" type="button">Preview in the Query tab</button></div>' +
    '<div id="cat-list"></div>';
  q(root, "#cat-search").addEventListener("input", e => {
    filter = /** @type {HTMLInputElement} */ (evTarget(e)).value;
    renderChips();
  });
  q(root, "#cat-fold").addEventListener("change", () => reload().catch(e => setStatus(String(e), "error")));
  q(root, "#cat-mode").addEventListener("change", selectionChanged);
  q(root, "#cat-clear").addEventListener("click", () => { selected = []; selectionChanged(); });
  q(root, "#cat-chips").addEventListener("click", onChipClick);
  q(root, "#cat-op").addEventListener("change", syncOp);
  q(root, "#cat-preview").addEventListener("click", () => previewEdit().catch(e => setStatus(String(e), "error")));
  q(root, "#cat-list").addEventListener("dblclick", onListDblClick);
  syncOp();
}

/** Fetch the chips again (keeping the selection that still exists) and redraw. */
async function reload() {
  if (!section().querySelector("#cat-chips")) buildShell();
  const r = await fetch(`/api/categories?fold=${fold() ? 1 : 0}`);
  const data = await r.json().catch(() => null);
  if (r.status === 501) { notAvailable(section(), data && data.needs); return; }
  if (!r.ok) { showError(errMsg(r.status, data)); return; }
  answer = data;
  const known = new Set(data.categories.map(c => c.category));
  selected = selected.filter(c => known.has(c));
  noteGeneration("categories", data.generation);
  selectionChanged();
}

/** Build the panel the first time it is shown; load the chips each time. */
export const loadCategories = reload;

onRerun("categories", () => reload().catch(e => setStatus(String(e), "error")));
