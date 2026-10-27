import { escapeHtml, mmss } from './util.js';

// Read-only form strips for query results. One row per level, outermost first;
// each block sits at its start/end on the strip's extent.
//   opts.highlightIds  gold `matched`            opts.parentIds   blue `matched-parent`
//   opts.contextIds    `matched-ctx`             every other block is `dim` once any is given
//   opts.rowLabels     {level: name}, every named row is drawn, even an empty one
//   opts.adds          [{level, start, end, label}]: components a pending edit would add, drawn dashed
//   opts.marks         Map component_id -> {kind: "set" | "del", newLabel?}: blocks a pending edit changes
//   opts.extent        {tmin, tmax}, shared by the strips of one card
// A point (a marker) is drawn as a tick, its label running to the right.

const HEX_COLOR = /^#(?:[0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i;
const DEFAULT_COLOR = "#9aa";

/** A colour comes from the user's files: only a hex colour goes into a style. */
export function safeColor(color) {
  return typeof color === "string" && HEX_COLOR.test(color) ? color : DEFAULT_COLOR;
}

/**
 * @param {Array<{start?: number, end?: number}>} comps
 * @param {number} [totalDur]  the file's length, when known: the axis then starts at 0
 */
export function stripExtent(comps, totalDur) {
  let tmin = Infinity, tmax = -Infinity;
  for (const c of comps) {
    if (typeof c.start === "number") tmin = Math.min(tmin, c.start);
    if (typeof c.end === "number") tmax = Math.max(tmax, c.end);
  }
  if (!isFinite(tmin) || !isFinite(tmax) || tmax <= tmin) { tmin = 0; tmax = 1; }
  if (totalDur && totalDur > 0) { tmin = 0; tmax = Math.max(totalDur, tmax); }
  return { tmin, tmax };
}

export function renderFormStrip(comps, opts = {}) {
  const highlight = opts.highlightIds || null;
  const parents = opts.parentIds || null;
  const context = opts.contextIds || null;
  const active = highlight || parents || context;
  const rowLabels = opts.rowLabels || null;
  const adds = opts.adds || [];
  const marks = opts.marks || null;
  const { tmin, tmax } = opts.extent || stripExtent(comps, opts.totalDur);
  const dur = (tmax - tmin) || 1;

  const byLevel = new Map();
  for (const c of comps) {
    const lv = c.level == null ? 0 : c.level;
    if (!byLevel.has(lv)) byLevel.set(lv, []);
    byLevel.get(lv).push(c);
  }
  if (rowLabels)
    for (const k of Object.keys(rowLabels)) if (!byLevel.has(Number(k))) byLevel.set(Number(k), []);
  // a new component may sit at a level the timeline has no row for yet
  for (const a of adds) if (!byLevel.has(a.level)) byLevel.set(a.level, []);
  const levels = [...byLevel.keys()].sort((a, b) => b - a);
  const left = s => `left:${Math.max(0, (s - tmin) / dur * 100).toFixed(2)}%`;
  const pos = (s, e) => `${left(s)};width:${Math.max(0.4, (e - s) / dur * 100).toFixed(2)}%`;

  let html = "";
  for (const lv of levels) {
    const name = rowLabels && rowLabels[lv] != null ? String(rowLabels[lv]) : `lv ${lv}`;
    let blocks = "";
    for (const c of byLevel.get(lv)) {
      const s = typeof c.start === "number" ? c.start : tmin;
      const e = typeof c.end === "number" ? c.end : s;
      const isParent = parents && parents.has(c.component_id);
      const isHot = highlight && highlight.has(c.component_id);
      const isCtx = context && context.has(c.component_id);
      const mark = marks && marks.get(c.component_id);
      const cls = "strip-block"
        + (c.point ? " point" : "")
        + (active ? (isParent ? " matched matched-parent" : isHot ? " matched"
                     : isCtx ? " matched-ctx" : " dim") : "")
        + (mark ? ` plan-${mark.kind}` : "");
      const label = (mark && mark.newLabel != null ? mark.newLabel : c.label) || "";
      const where = c.point ? mmss(s) : `${mmss(s)}–${mmss(e)}`;
      blocks +=
        `<div class="${cls}" data-cid="${escapeHtml(String(c.component_id))}"` +
        ` style="${c.point ? left(s) : pos(s, e)};background:${safeColor(c.color)}"` +
        ` title="${escapeHtml(`${label}  (${where}, ${name})`)}">${escapeHtml(label)}</div>`;
    }
    for (const a of adds) {
      if (a.level !== lv) continue;
      blocks +=
        `<div class="strip-block plan-add" style="${pos(a.start, a.end)}"` +
        ` title="${escapeHtml(`new: ${a.label}  (${mmss(a.start)}–${mmss(a.end)}, ${name})`)}">` +
        `${escapeHtml(a.label == null ? "" : a.label)}</div>`;
    }
    html +=
      `<div class="strip-row"><span class="lvl" title="${escapeHtml(name)}">${escapeHtml(name)}</span>` +
      `<div class="strip">${blocks}</div></div>`;
  }
  return html;
}
