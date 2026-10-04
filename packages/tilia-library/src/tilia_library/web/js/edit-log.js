import { closest, evTarget, q } from './lib/dom.js';
import { noteGeneration, onRerun } from './liveness.js';
import { notAvailable, panelSection } from './panels.js';
import { errMsg, escapeHtml, setStatus } from './util.js';

const NAMES_SHOWN = 5;
const EMPTY = "No edits yet. Edits applied from the Query tab appear here.";

const section = () => panelSection("edit-log");

let entries = [];     // the log as last loaded, newest first
let names = {};       // file id -> name, for the files the log mentions

function buildShell() {
  section().innerHTML = `<div id="edit-log-result" role="status"></div><div id="edit-log-list"></div>`;
}

const nameOf = id => names[id] || id;

function filesText(ids) {
  const shown = ids.slice(0, NAMES_SHOWN).map(nameOf).join(", ");
  const more = ids.length > NAMES_SHOWN ? ` and ${ids.length - NAMES_SHOWN} more` : "";
  return `${ids.length} ${ids.length === 1 ? "file" : "files"}: ${shown}${more}`;
}

function entryHtml(entry) {
  const action = entry.undone
    ? `<span class="edit-undone">Undone</span>`
    : `<button type="button" class="edit-undo">Undo</button>`;
  return `<div class="edit-entry" data-entry="${escapeHtml(entry.entry)}">` +
    `<code class="edit-statement" dir="auto">${escapeHtml(entry.statement)}</code>` +
    `<span class="edit-at">${escapeHtml(new Date(entry.at).toLocaleString())}</span>` +
    `<span class="edit-files" dir="auto">${escapeHtml(filesText(entry.files))}</span>` +
    `${action}</div>`;
}

function render() {
  q(section(), "#edit-log-list").innerHTML = entries.length
    ? entries.map(entryHtml).join("")
    : `<p class="muted">${escapeHtml(EMPTY)}</p>`;
}

function resultHtml(data) {
  const n = data.restored.length;
  let html = `<p>Restored ${n} ${n === 1 ? "file" : "files"}.</p>`;
  if (data.refused.length) {
    html += `<div class="edit-refused"><p>Not restored, changed since the edit:</p><ul>` +
      data.refused.map(r =>
        `<li>${escapeHtml(`${data.file_names[r.file_id] || r.file_id}: ${r.what_changed}`)}</li>`).join("") +
      `</ul></div>`;
  }
  if (data.skipped.length) {
    html += `<ul>` + data.skipped.map(s =>
      `<li>${escapeHtml(`Skipped ${data.file_names[s.file_id] || s.file_id}: ${s.reason}`)}</li>`).join("") +
      `</ul>`;
  }
  return html;
}

async function undo(entry) {
  const ok = confirm(`Undo this edit?\n\n${entry.statement}\n\nFiles changed since the edit are left as they are.`);
  if (!ok) return;
  const r = await fetch(`/api/edit-log/${encodeURIComponent(entry.entry)}/undo`, { method: "POST", body: "{}" });
  const data = await r.json().catch(() => null);
  if (r.status === 501) { notAvailable(section(), data && data.needs); return; }
  const result = q(section(), "#edit-log-result");
  if (!r.ok) { result.textContent = errMsg(r.status, data); return; }
  result.innerHTML = resultHtml(data);
  await loadEditLog(true);
}

function onClick(event) {
  const target = evTarget(event);
  if (!target.closest(".edit-undo")) return;
  const row = closest(target, ".edit-entry");
  const entry = entries.find(e => e.entry === row.dataset.entry);
  if (entry) undo(entry).catch(e => setStatus(String(e), "error"));
}

/** Load the log into the panel; the result of an undo stays when `keepResult`. */
export async function loadEditLog(keepResult = false) {
  const root = section();
  if (!root.querySelector("#edit-log-list")) {
    buildShell();
    root.addEventListener("click", onClick);
  }
  const r = await fetch("/api/edit-log");
  const data = await r.json().catch(() => null);
  if (r.status === 501) { notAvailable(root, data && data.needs); return; }
  if (!r.ok) { setStatus(errMsg(r.status, data), "error"); return; }
  if (!keepResult) q(root, "#edit-log-result").textContent = "";
  entries = data.entries;
  names = data.file_names;
  render();
  noteGeneration("edit-log", data.generation);
}

onRerun("edit-log", () => loadEditLog(true));
