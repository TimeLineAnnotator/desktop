import { closest, evTarget, q, qa } from './lib/dom.js';
import { panelSection } from './panels.js';
import { cards, markError, paintStrips, run, renderResults, showError, clearError, boxText } from './query.js';
import { edit, query } from './state.js';
import { errMsg, escapeHtml } from './util.js';

// The write half of the query panel, `query -> ACTION`:
//   * preview and apply are two requests; apply only ever sends a preview whose
//     statement is the box's current text, so every keystroke ends the preview;
//   * the plan is drawn onto the cards and table rows, never into a second list
//     that could disagree with them about what will happen;
//   * `only` carries the ticked keys; the server plans again and writes only those.

const section = () => panelSection("query");
const bar = () => q(section(), "#ql-edit-bar");
const button = id => /** @type {HTMLButtonElement} */ (q(section(), id));
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const shown = v => (v == null || v === "") ? "∅" : String(v);

let note = "";   // what the summary says when no preview is live: an action error, a 501

export function editBarHtml() {
  return '<div id="ql-edit-bar" class="ql-edit-bar" hidden><div class="ql-edit-row">' +
    '<span id="ql-edit-verb" class="ql-edit-verb"></span>' +
    '<button id="ql-preview" type="button">Preview</button>' +
    '<button id="ql-apply" type="button" disabled>Apply</button>' +
    '<button id="ql-all" type="button" hidden>Tick all</button>' +
    '<button id="ql-none" type="button" hidden>Untick all</button>' +
    '<span id="ql-edit-summary" class="ql-edit-summary"></span></div>' +
    '<ul id="ql-edit-skipped" class="ql-edit-skipped muted" hidden></ul>' +
    '<div id="ql-edit-result" class="ql-edit-result"></div></div>';
}

// ---- the plan on the results ------------------------------------------------ //

/** The plan entry of one match, or null when no preview is live. */
export function planFor(m) {
  return edit.live && m ? edit.live.plan.get(m.key) || null : null;
}

const hasWrites = p => !!(p && p.writes.length);

/** Ticked? The user's own choice where they made one; otherwise exactly when the entry writes. */
export function picked(key) {
  if (edit.picks.has(key)) return edit.picks.get(key);
  return hasWrites(edit.live && edit.live.plan.get(key));
}

/** A card's matches that have something to write: the ones a tick decides. */
function writable(c) {
  return c.matches.filter(m => hasWrites(planFor(m)));
}

function writeText(w) {
  if (w.op === "add") return `+ ${shown(w.new)}`;
  if (w.op === "delete") return `− ${shown(w.old)}`;
  return `${w.field}: ${shown(w.old)} → ${shown(w.new)}`;
}

/** What the entry does, short enough to sit beside the labels. */
function diffHtml(p) {
  if (p.do === "skip") {
    return `<span class="plan-diff plan-skip">skipped${p.reason ? `: ${escapeHtml(p.reason)}` : ""}</span>`;
  }
  const w = p.writes[0];
  if (!w) {
    return p.reason
      ? `<span class="plan-diff plan-skip">${escapeHtml(p.reason)}</span>`
      : '<span class="plan-diff plan-none">nothing to write</span>';
  }
  let body;
  if (w.op === "add") body = `<b>+ ${escapeHtml(shown(w.new))}</b>`;
  else if (w.op === "delete") body = `<s>− ${escapeHtml(shown(w.old))}</s>`;
  else {
    body = (w.field && w.field !== "label" ? `${escapeHtml(w.field)}: ` : "") +
      `<s>${escapeHtml(shown(w.old))}</s> → <b>${escapeHtml(shown(w.new))}</b>`;
  }
  const more = p.writes.length > 1 ? ` <span class="muted">+${p.writes.length - 1} more</span>` : "";
  const cls = w.op === "delete" ? " plan-del" : "";
  return `<span class="plan-diff${cls}" title="${escapeHtml(p.writes.map(writeText).join("\n"))}">${body}${more}</span>`;
}

/** The checkbox of one entry. */
function pickHtml(p, key) {
  const has = hasWrites(p);
  return `<input type="checkbox" class="run-pick" data-key="${escapeHtml(key)}"` +
    `${picked(key) ? " checked" : ""}${has ? "" : " disabled"}` +
    ` title="${has ? "include this match in the write" : "nothing to write here"}">`;
}

/** The edit's part of a match line: its box, to go first, and its diff, to go last. */
export function lineParts(m) {
  const p = planFor(m);
  if (!p) return { off: false, pick: "", diff: "" };
  return { off: hasWrites(p) && !picked(m.key), pick: pickHtml(p, m.key), diff: diffHtml(p) };
}

/** The card head's box, and the " · K/M ticked" that syncCardPicks fills in. */
export function cardHeadParts(c, i) {
  if (!writable(c).length) return { pick: "", ticked: "" };
  return {
    pick: `<input type="checkbox" class="card-pick" data-i="${i}" title="include this file's matches in the write">`,
    ticked: '<span class="card-ticked"></span>',
  };
}

/** The ticked writes of a card's entries on one timeline: new blocks, and blocks to re-dress. */
export function overlay(c, timelineId) {
  const adds = [], marks = new Map();
  for (const m of c.matches) {
    const p = planFor(m);
    if (!p || !picked(m.key)) continue;
    for (const w of p.writes) {
      if (w.timeline_id !== timelineId) continue;
      if (w.op === "add") {
        adds.push({ level: w.level, start: w.start, end: w.end, label: w.new });
      } else if (w.op === "delete") {
        marks.set(w.component_id, { kind: "del" });
      } else if (w.op === "set") {
        const mark = marks.get(w.component_id) || { kind: "set" };
        if (w.field === "label") mark.newLabel = w.new;
        if (mark.kind !== "del") marks.set(w.component_id, mark);
      }
    }
  }
  return { adds, marks };
}

/** Each card's box and its "K/M ticked": ticked, or indeterminate when only some are. */
export function syncCardPicks() {
  if (!edit.live) return;
  for (const box of /** @type {NodeListOf<HTMLInputElement>} */ (qa(q(section(), "#ql-results"), ".card-pick"))) {
    const c = cards[Number(box.dataset.i)];
    if (!c) continue;
    const planned = writable(c);
    const on = planned.filter(m => picked(m.key)).length;
    box.checked = on > 0;
    box.indeterminate = on > 0 && on < planned.length;
    const card = closest(box, ".ql-card");
    card.classList.toggle("card-off", planned.length > 0 && on === 0);
    q(card, ".card-ticked").textContent = ` · ${on}/${planned.length} ticked`;
  }
}

// ---- the bar ------------------------------------------------------------------ //

/** The ticked writes: what Apply would send, and their size. */
function selection() {
  const entries = edit.live ? [...edit.live.plan.values()].filter(p => hasWrites(p) && picked(p.key)) : [];
  let writes = 0, deletes = 0;
  for (const p of entries) {
    writes += p.writes.length;
    deletes += p.writes.filter(w => w.op === "delete").length;
  }
  return { keys: entries.map(p => p.key), writes, deletes, files: new Set(entries.map(p => p.file_id)).size };
}

function summaryText() {
  const s = edit.live.summary;
  const { writes, files } = selection();
  let text = `${plural(s.matches, "match", "matches")}, ${plural(s.writes, "write", "writes")} in ${plural(s.files, "file", "files")}`;
  if (s.deletes) text += `, ${plural(s.deletes, "deletion", "deletions")}`;
  return `${text} · ticked: ${plural(writes, "write", "writes")} in ${plural(files, "file", "files")}`;
}

/** The summary, the Apply button and the tick buttons, from what is live now. */
function renderBar() {
  const live = !!edit.live;
  const { writes } = selection();
  q(section(), "#ql-edit-summary").textContent = live ? summaryText() : note;
  const apply = button("#ql-apply");
  apply.textContent = live && writes ? `Apply (${writes})` : "Apply";
  apply.disabled = !live || writes === 0;
  button("#ql-all").hidden = !live;
  button("#ql-none").hidden = !live;
}

function fileName(fileId) {
  const m = query.result && query.result.matches.find(x => x.file_id === fileId);
  return m ? m.name : fileId;
}

function listSkipped(items) {
  const list = q(section(), "#ql-edit-skipped");
  list.innerHTML = items.map(s => `<li>${escapeHtml(`${fileName(s.file_id)}: ${s.reason}`)}</li>`).join("");
  list.hidden = !items.length;
}

function setResult(text, skipped = []) {
  q(section(), "#ql-edit-result").innerHTML = text
    ? `<div>${escapeHtml(text)}</div>` +
      (skipped.length
        ? `<ul>${skipped.map(s => `<li>${escapeHtml(`Skipped ${fileName(s.file_id)}: ${s.reason}`)}</li>`).join("")}</ul>`
        : "")
    : "";
}

/** Make an answer of ql-edit the live preview, and draw it. */
function setLive(data) {
  const plan = new Map(data.plan.map(p => [p.key, p]));
  for (const key of [...edit.picks.keys()]) if (!plan.has(key)) edit.picks.delete(key);
  edit.live = { id: data.preview, statement: data.statement, plan, summary: data.summary };
  note = "";
  listSkipped(data.skipped_files || []);
  renderResults();
  renderBar();
}

/** End the live preview. The user's ticks stay, by key. */
function endPreview(redraw = true) {
  const was = edit.live;
  edit.live = null;
  listSkipped([]);
  setResult("");
  renderBar();
  if (was && redraw) renderResults();
}

/** The box's text changed: what a preview showed is no longer what would be written. */
export function textChanged() {
  note = "";
  endPreview();
}

/** Show or hide the bar for an answer of /api/ql (null when there is none). */
export function syncEditBar(data) {
  const verb = data && data.action;
  bar().hidden = !verb;
  if (!verb) {
    note = "";
    endPreview(false);
    return;
  }
  q(section(), "#ql-edit-verb").textContent = String(verb).toUpperCase();
  const bad = data.action_error;
  button("#ql-preview").disabled = !!bad;
  if (bad) {
    note = bad.error;
    markError(boxText(), bad);
  } else if (!edit.live) {
    note = "";
  }
  renderBar();
}

// ---- preview and apply ---------------------------------------------------------- //

/** A POST that answers [status, body]; a dropped connection is status 0. */
async function post(url, body) {
  try {
    const r = await fetch(url, { method: "POST", body: JSON.stringify(body) });
    return [r.status, await r.json().catch(() => null)];
  } catch (e) {
    return [0, { error: `could not reach the server (${e})` }];
  }
}

async function preview() {
  const text = boxText();
  const btn = button("#ql-preview");
  btn.disabled = true;
  const [status, data] = await post("/api/ql-edit", { statement: text, tab: query.tab });
  btn.disabled = !!(query.result && query.result.action_error);
  if (boxText() !== text) return;   // edited while it planned: that plan is stale
  setResult("");
  if (status === 200) {
    clearError();
    setLive(data);
  } else if (status === 501) {
    endPreview();
    note = `Not available yet: this needs ${data && data.needs}.`;
    renderBar();
  } else {
    endPreview();
    showError(text, data);
  }
}

function confirmText(statement, { writes, deletes, files }) {
  return `Write ${plural(writes, "change", "changes")} to ${plural(files, "file", "files")}?` +
    (deletes ? `\n${deletes} of them delete components.` : "") +
    `\n\n${statement}\n\nThis rewrites the .tla files on disk.`;
}

async function apply() {
  const live = edit.live;
  if (!live || live.statement !== boxText()) return;
  const chosen = selection();
  if (!chosen.writes || !confirm(confirmText(live.statement, chosen))) return;
  button("#ql-apply").disabled = true;
  const [status, data] = await post("/api/ql-apply", { preview: live.id, only: chosen.keys });
  if (status === 200) {
    edit.picks.clear();
    query.contexts.clear();
    endPreview(false);
    const n = (data.written || []).length;
    setResult(`Wrote ${plural(n, "file", "files")}.`, data.skipped || []);
    await run();
  } else if (status === 409) {
    setLive(data);
    setResult("The files changed since the preview. This is the new preview; nothing was written.");
  } else if (status === 410) {
    endPreview();
    setResult("The preview expired; preview again.");
  } else {
    setResult((data && data.error) || errMsg(status, data));
    renderBar();
  }
}

// ---- ticks --------------------------------------------------------------------- //

function selectionChanged() {
  syncCardPicks();
  renderBar();
}

function onChange(e) {
  const t = /** @type {HTMLInputElement} */ (evTarget(e));
  if (!edit.live) return;
  if (t.classList.contains("run-pick")) {
    edit.picks.set(t.dataset.key, t.checked);
    closest(t, ".ql-run, tr").classList.toggle("run-off", !t.checked);
    const card = t.closest(".ql-card");
    if (card) paintStrips(Number(/** @type {HTMLElement} */ (card).dataset.i));
    selectionChanged();
  } else if (t.classList.contains("card-pick")) {
    const i = Number(t.dataset.i);
    const c = cards[i];
    if (!c) return;
    for (const m of writable(c)) edit.picks.set(m.key, t.checked);
    for (const box of /** @type {NodeListOf<HTMLInputElement>} */ (qa(closest(t, ".ql-card"), ".run-pick"))) {
      if (box.disabled) continue;
      box.checked = t.checked;
      closest(box, ".ql-run").classList.toggle("run-off", !t.checked);
    }
    paintStrips(i);
    selectionChanged();
  }
}

function tickAll(on) {
  for (const p of edit.live.plan.values()) if (hasWrites(p)) edit.picks.set(p.key, on);
  renderResults();
  renderBar();
}

/** Wire the bar and the ticks; the panel's markup is already built. */
export function wireEdit() {
  const root = section();
  q(root, "#ql-preview").addEventListener("click", preview);
  q(root, "#ql-apply").addEventListener("click", apply);
  q(root, "#ql-all").addEventListener("click", () => tickAll(true));
  q(root, "#ql-none").addEventListener("click", () => tickAll(false));
  q(root, "#ql-results").addEventListener("change", onChange);
}
