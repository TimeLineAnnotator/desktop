import { closest, q, qInput } from './lib/dom.js';
import { notAvailable, panelSection } from './panels.js';
import { files } from './state.js';
import { errMsg, escapeHtml, setStatus } from './util.js';

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
const COLUMNS = [["name", "Name"], ["state", "State"], ["timelines", "Timelines"], ["path", "Path"]];
const STATE_LABEL = { ok: "ok", unreadable: "can't read", unavailable: "unavailable" };

const section = () => panelSection("files");
const text = (s, extra = "") => `<td dir="auto"${extra}>${s}</td>`;

function joined(value) {
  return Array.isArray(value) ? value.join(", ") : String(value);
}

function kindsText(kinds) {
  return Object.entries(kinds).map(([kind, n]) => `${n} ${kind}`).join(", ");
}

function haystack(row) {
  const fields = Object.entries(row.fields).flatMap(([k, v]) => [k, joined(v)]);
  return [row.name, row.path, row.reason || "", ...fields, ...Object.keys(row.timelines.kinds)]
    .join("\n").toLowerCase();
}

function visibleRows() {
  const needle = files.filter.trim().toLowerCase();
  const rows = needle ? files.rows.filter(r => haystack(r).includes(needle)) : files.rows.slice();
  const key = files.sortKey;
  if (key) {
    const value = r => (key === "timelines" ? r.timelines.count : String(r[key] ?? ""));
    rows.sort((a, b) => {
      const [x, y] = [value(a), value(b)];
      const cmp = typeof x === "number" ? x - y : collator.compare(x, y);
      return cmp * files.sortDir;
    });
  }
  return rows;
}

function stateCell(row) {
  const reason = row.reason ? ` <span class="muted">${escapeHtml(row.reason)}</span>` : "";
  return text(`${escapeHtml(STATE_LABEL[row.state] || row.state)}${reason}`);
}

function fieldsCell(fields) {
  const pairs = Object.entries(fields).map(([k, v]) =>
    `<span class="pair">${escapeHtml(k)}: ${escapeHtml(joined(v))}</span>`);
  return text(pairs.join(""));
}

function rowHtml(row) {
  const id = escapeHtml(row.file_id);
  const open = files.expanded.has(row.file_id);
  const kinds = kindsText(row.timelines.kinds);
  const timelines = `${row.timelines.count}${kinds ? ` <span class="muted">(${escapeHtml(kinds)})</span>` : ""}`;
  const main = `<tr data-file-id="${id}">` +
    `<td class="expand-cell"><button type="button" class="expand" data-file-id="${id}" aria-expanded="${open}">${open ? "▾" : "▸"}</button></td>` +
    text(escapeHtml(row.name)) + stateCell(row) + text(timelines) + fieldsCell(row.fields) +
    text(escapeHtml(row.path), ' class="muted"') + "</tr>";
  return open ? main + detailHtml(row.file_id) : main;
}

function detailHtml(fileId) {
  const detail = files.details.get(fileId);
  const body = detail.timelines.map(t =>
    `<tr data-timeline-id="${escapeHtml(t.id)}">${text(escapeHtml(t.name))}${text(escapeHtml(t.kind))}${fieldsCell(t.fields)}</tr>`).join("");
  return `<tr class="detail" data-file-id="${escapeHtml(fileId)}"><td colspan="6"><table>` +
    `<thead><tr><th>Name</th><th>Kind</th><th>Fields</th></tr></thead><tbody>${body}</tbody></table></td></tr>`;
}

function render() {
  const root = section();
  const rows = visibleRows();
  const total = files.rows.length;
  const noun = total === 1 ? "file" : "files";
  q(root, "#files-count").textContent = rows.length === total ? `${total} ${noun}` : `${rows.length} of ${total} ${noun}`;
  const heads = COLUMNS.map(([key, label]) => {
    const arrow = files.sortKey === key ? ` <span class="arrow">${files.sortDir === 1 ? "▲" : "▼"}</span>` : "";
    return `<th data-sort="${key}">${label}${arrow}</th>`;
  });
  q(root, "thead").innerHTML = `<tr><th></th>${heads[0]}${heads[1]}${heads[2]}<th>Fields</th>${heads[3]}</tr>`;
  q(root, "tbody").innerHTML = rows.map(rowHtml).join("");
}

function buildShell() {
  const root = section();
  root.innerHTML = `<div class="bar"><input id="files-filter" type="search" placeholder="Filter files" aria-label="Filter files">` +
    `<span id="files-count" class="count"></span></div><table><thead></thead><tbody></tbody></table>`;
  qInput(root, "#files-filter").addEventListener("input", e => {
    files.filter = /** @type {HTMLInputElement} */ (e.target).value;
    render();
  });
  q(root, "thead").addEventListener("click", e => {
    const th = closest(/** @type {Element} */ (e.target), "th[data-sort]");
    if (!th) return;
    const key = th.dataset.sort;
    files.sortDir = files.sortKey === key ? -files.sortDir : 1;
    files.sortKey = key;
    render();
  });
  q(root, "tbody").addEventListener("click", e => {
    const button = closest(/** @type {Element} */ (e.target), "button.expand");
    if (button) toggle(button.dataset.fileId);
  });
}

async function toggle(fileId) {
  if (files.expanded.has(fileId)) {
    files.expanded.delete(fileId);
    render();
    return;
  }
  if (!files.details.has(fileId)) {
    const r = await fetch(`/api/files/${encodeURIComponent(fileId)}`);
    const data = await r.json().catch(() => null);
    if (!r.ok) { setStatus(errMsg(r.status, data), "error"); return; }
    files.details.set(fileId, data);
  }
  files.expanded.add(fileId);
  render();
}

export async function loadFiles() {
  const root = section();
  if (!root.querySelector("#files-filter")) buildShell();
  const r = await fetch("/api/files");
  const data = await r.json().catch(() => null);
  if (r.status === 501) { notAvailable(root, data.needs); return; }
  if (!r.ok) { setStatus(errMsg(r.status, data), "error"); return; }
  files.rows = data.rows;
  files.details.clear();
  files.expanded.clear();
  render();
}
