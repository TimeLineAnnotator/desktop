"use strict";
// TiLiA's score viewer. Python calls the `tilia*` functions below with
// runJavaScript, and hears back through the `tilia` object on the web channel.
//
// Score positions go between the two sides as a measure number (MEI's @n)
// and a fraction of that measure; Python turns them into times with the beat
// timeline. Inside the page, positions are quarter notes from the start of
// the score (Verovio's qstamp).

// The continuous layout: one system, scrolled horizontally.
const OPTIONS = {
  breaks: "none",
  header: "none",
  footer: "none",
  adjustPageHeight: true,
  adjustPageWidth: true,
  mnumInterval: 5,
  scale: 40,
  svgViewBox: true,
  svgRemoveXlink: true,
  svgAdditionalAttribute: ["measure@n"],
};
// Pages as wide as the box, scrolled vertically. Verovio breaks systems to fit
// the width, and pages only where a score is longer than this.
const PAGE_HEIGHT = 60000;
const RELAYOUT_DELAY = 150; // ms after the box stops changing width

const scoreEl = document.getElementById("score");
let toolkit = null;
let bridge = null;
let measures = []; // {id, n, qStart, qEnd}, in score order
let onsets = new Map(); // element id -> qstamp of its onset
// {top, bottom, bandTop, bandBottom, qStart, qEnd, anchors}, top to bottom.
// Anchors are {q, x}, both increasing; x and y are in pixels from the score's
// top left. A system's band reaches halfway to its neighbours.
let systems = [];
let layout = "continuous"; // or "pages"
let layoutWidth = 0; // the box's width the pages were laid out for
let relayoutTimer = null;
let colors = new Map(); // element id -> colour, as Python gives them
let lastViewport = "";
let groups = []; // {id, ids, color, text}, as Python gives them
let blobShapes = []; // {id, points, edges, radius}, as drawn
let activeGroup = null; // the id of the group whose notes are selected
let highlights = []; // {qStart, qEnd}: what's selected in other timelines
let zoom = 1;
let band = null; // the drag that may become a selection box
let wasDragged = false;

const SVG_NS = "http://www.w3.org/2000/svg";
const DRAG_THRESHOLD = 4; // pixels
const MIN_ZOOM = 1;
const MAX_ZOOM = 5;

function send(slot, payload) {
  if (bridge) bridge[slot](JSON.stringify(payload));
}

function onReady() {
  if (bridge && toolkit) bridge.viewerReady();
}

function sanitizedSvg(text) {
  // Parsed as XML and imported, never assigned to innerHTML, and stripped of
  // anything that could run: scripts, foreign (HTML) content, event handlers.
  const doc = new DOMParser().parseFromString(text, "image/svg+xml");
  const svg = doc.documentElement;
  if (svg.nodeName !== "svg") {
    throw new Error("Verovio returned no SVG.");
  }
  svg.querySelectorAll("script, foreignObject").forEach((el) => el.remove());
  for (const el of [svg, ...svg.querySelectorAll("*")]) {
    for (const attr of [...el.attributes]) {
      if (attr.name.toLowerCase().startsWith("on")) el.removeAttribute(attr.name);
    }
  }
  const page = document.importNode(svg, true);
  page.classList.add("tilia-page");
  return page;
}

function pages() {
  return [...scoreEl.querySelectorAll("svg.tilia-page")];
}

function setOverflow() {
  // In pages, the scrollbar always shows, so that it doesn't take width the
  // pages were laid out with.
  const isPages = layout === "pages";
  scoreEl.style.overflowX = isPages ? "hidden" : "auto";
  // Zoomed in, a continuous score can scroll vertically too.
  scoreEl.style.overflowY = isPages ? "scroll" : zoom > 1 ? "auto" : "hidden";
}

function setLayoutOptions() {
  setOverflow();
  if (layout === "pages") {
    layoutWidth = scoreEl.clientWidth;
    // Laid out this many pixels wide, it shows at the size the zoom asks for.
    const width = layoutWidth / zoom;
    toolkit.setOptions({
      ...OPTIONS,
      breaks: "auto",
      adjustPageWidth: false,
      pageWidth: Math.max(100, Math.round((width * 100) / OPTIONS.scale)),
      pageHeight: PAGE_HEIGHT,
    });
  } else {
    toolkit.setOptions(OPTIONS);
  }
}

// Draws the laid-out score, keeping the colours and the selection shown.
function showPages() {
  const selected = selectedIds();
  const svgs = [];
  for (let page = 1; page <= toolkit.getPageCount(); page++) {
    svgs.push(sanitizedSvg(toolkit.renderToSVG(page)));
  }
  scoreEl.replaceChildren(...svgs);
  for (const [id, color] of colors) paint(id, color);
  for (const id of selected) document.getElementById(id)?.classList.add("tilia-selected");
}

function paint(id, color) {
  const el = document.getElementById(id);
  if (!el) return;
  el.style.color = color || "";
  el.style.fill = color || "";
}

function readTimemap(timemap) {
  measures = [];
  onsets = new Map();
  const seen = new Set();
  let qEnd = 0;
  for (const entry of timemap) {
    if (entry.measureOn && !seen.has(entry.measureOn)) {
      seen.add(entry.measureOn);
      const el = document.getElementById(entry.measureOn);
      measures.push({
        id: entry.measureOn,
        n: el ? el.getAttribute("data-n") : null,
        qStart: entry.qstamp,
      });
    }
    // Verovio lists rests apart from notes.
    for (const id of [...(entry.on || []), ...(entry.restsOn || [])]) {
      if (!onsets.has(id)) onsets.set(id, entry.qstamp);
    }
    qEnd = Math.max(qEnd, entry.qstamp);
  }
  measures.forEach((m, i) => {
    m.qEnd = i + 1 < measures.length ? measures[i + 1].qStart : qEnd;
  });
}

function scoreX(clientX) {
  return clientX - scoreEl.getBoundingClientRect().left + scoreEl.scrollLeft;
}

function headOf(el) {
  return el.querySelector(".notehead") || el;
}

function staffLineOf(measure) {
  const el = measure && document.getElementById(measure.id);
  return el ? el.querySelector(".staff > path") : null;
}

function systemOf(el) {
  return el.closest("g.system") || el.ownerSVGElement || el;
}

function measureSystems() {
  const bySystem = new Map(); // g.system -> Map of q -> x
  const add = (el, q, x) => {
    const system = systemOf(el);
    if (!bySystem.has(system)) bySystem.set(system, new Map());
    const byQ = bySystem.get(system);
    if (!byQ.has(q) || x < byQ.get(q)) byQ.set(q, x);
  };
  const lastOf = new Map(); // g.system -> its last measure
  for (const m of measures) {
    const line = staffLineOf(m);
    if (!line) continue;
    add(line, m.qStart, scoreX(line.getBoundingClientRect().left));
    lastOf.set(systemOf(line), m);
  }
  for (const [id, q] of onsets) {
    const el = document.getElementById(id);
    if (el) add(el, q, scoreX(headOf(el).getBoundingClientRect().left));
  }
  // A system ends where its last measure does.
  for (const [system, m] of lastOf) {
    const line = staffLineOf(m);
    bySystem.get(system).set(m.qEnd, scoreX(line.getBoundingClientRect().right));
  }

  systems = [];
  for (const [system, byQ] of bySystem) {
    const anchors = [];
    for (const [q, x] of [...byQ].sort((a, b) => a[0] - b[0])) {
      if (!anchors.length || x > anchors[anchors.length - 1].x) anchors.push({ q, x });
    }
    const rect = system.getBoundingClientRect();
    systems.push({
      top: scoreY(rect.top),
      bottom: scoreY(rect.bottom),
      qStart: anchors[0].q,
      qEnd: anchors[anchors.length - 1].q,
      anchors,
    });
  }
  systems.sort((a, b) => a.top - b.top);
  const height = contentSize().height;
  systems.forEach((system, i) => {
    const previous = systems[i - 1];
    const next = systems[i + 1];
    system.bandTop = previous ? (previous.bottom + system.top) / 2 : 0;
    system.bandBottom = next ? (system.bottom + next.top) / 2 : height;
  });
}

function interpolate(anchors, from, to, value) {
  if (!anchors.length) return 0;
  if (value <= anchors[0][from]) return anchors[0][to];
  for (let i = 1; i < anchors.length; i++) {
    const a = anchors[i - 1];
    const b = anchors[i];
    if (value <= b[from]) {
      return a[to] + ((b[to] - a[to]) * (value - a[from])) / (b[from] - a[from]);
    }
  }
  return anchors[anchors.length - 1][to];
}

// The system a score position starts in: at a line break, the later one.
function systemAtQ(q) {
  return systems.find((system) => q < system.qEnd) || systems[systems.length - 1];
}

function systemAtY(y) {
  return systems.find((system) => y < system.bandBottom) || systems[systems.length - 1];
}

function xAt(system, q) {
  return interpolate(system.anchors, "q", "x", q);
}

function qAtPoint(x, y) {
  const system = systemAtY(y);
  return system ? interpolate(system.anchors, "x", "q", x) : 0;
}

function positionIn(m, q) {
  const length = m.qEnd - m.qStart;
  const fraction = length > 0 ? (q - m.qStart) / length : 0;
  return { measure: m.n, fraction: Math.min(1, Math.max(0, fraction)) };
}

function positionAt(q) {
  let found = measures[0];
  for (const m of measures) {
    if (m.qStart > q) break;
    found = m;
  }
  return positionIn(found, q);
}

function qAt(measure, fraction) {
  const m = measures.find((each) => each.n === String(measure));
  return m ? m.qStart + (m.qEnd - m.qStart) * fraction : null;
}

function contentSize() {
  const all = pages();
  return {
    width: Math.max(0, ...all.map((svg) => parseFloat(svg.style.width) || 0)),
    height: all.reduce((sum, svg) => sum + (parseFloat(svg.style.height) || 0), 0),
  };
}

function fit() {
  const all = pages();
  if (!all.length) return;
  setOverflow();
  if (layout === "pages") {
    for (const svg of all) {
      const [, , width, height] = svg.getAttribute("viewBox").split(/\s+/).map(Number);
      // Laid out `layoutWidth / zoom` wide: shown as wide as the box.
      const k = layoutWidth / width;
      svg.style.width = `${width * k}px`;
      svg.style.height = `${height * k}px`;
    }
  } else {
    const svg = all[0];
    const [, , width, height] = svg.getAttribute("viewBox").split(/\s+/).map(Number);
    // Twice: widening the score can bring in the horizontal scrollbar, which
    // takes height from the box.
    for (let pass = 0; pass < 2; pass++) {
      const k = Math.min(1, scoreEl.clientHeight / height) * zoom;
      svg.style.width = `${width * k}px`;
      svg.style.height = `${height * k}px`;
    }
  }
  measureSystems();
  drawGroups();
  drawHighlights();
}

// The systems in view: those whose staves show, or else the one around the
// middle of the box.
function visibleSystems() {
  const top = scoreEl.scrollTop;
  const bottom = top + scoreEl.clientHeight;
  const shown = systems.filter((system) => system.bottom > top && system.top < bottom);
  return shown.length ? shown : [systemAtY((top + bottom) / 2)].filter(Boolean);
}

function reportViewport(force) {
  if (!measures.length || !systems.length) return;
  const shown = visibleSystems();
  const left = scoreEl.scrollLeft;
  const right = left + scoreEl.clientWidth;
  const payload = {
    start: positionAt(interpolate(shown[0].anchors, "x", "q", left)),
    end: positionAt(interpolate(shown[shown.length - 1].anchors, "x", "q", right)),
  };
  const key = JSON.stringify(payload);
  if (!force && key === lastViewport) return;
  lastViewport = key;
  send("onViewportChanged", payload);
}

// In pages, scrolls a stretch of the score into view, from `top` to `bottom`:
// centred, or near the top of the box if it isn't all in view.
function revealY(top, bottom, centered) {
  if (layout !== "pages") return;
  const height = scoreEl.clientHeight;
  const margin = height / 10;
  const viewTop = scoreEl.scrollTop;
  if (centered) {
    scoreEl.scrollTop = (top + bottom - height) / 2;
  } else if (top < viewTop || bottom > viewTop + height) {
    scoreEl.scrollTop = top - margin;
  }
}

function clickable(target) {
  return target.closest ? target.closest("g.note, g.rest, g.chord") : null;
}

function onsetOf(el) {
  if (onsets.has(el.id)) return onsets.get(el.id);
  const notes = [...el.querySelectorAll("g.note")].filter((n) => onsets.has(n.id));
  if (notes.length) return Math.min(...notes.map((n) => onsets.get(n.id)));
  const rect = headOf(el).getBoundingClientRect();
  return qAtPoint(scoreX(rect.left), scoreY(rect.top + rect.height / 2));
}

function selectedIds() {
  return [...scoreEl.querySelectorAll(".tilia-selected")].map((el) => el.id);
}

function notesOf(ids) {
  const notes = new Set();
  for (const id of ids) {
    const el = document.getElementById(id);
    if (!el) continue;
    if (el.matches("g.note")) notes.add(id);
    el.querySelectorAll("g.note").forEach((note) => notes.add(note.id));
  }
  return [...notes];
}

function select(ids) {
  scoreEl.querySelectorAll(".tilia-selected").forEach((el) => {
    el.classList.remove("tilia-selected");
  });
  for (const id of ids) {
    const el = document.getElementById(id);
    if (el) el.classList.add("tilia-selected");
  }
  const selected = selectedIds();
  send("onSelectionChanged", {
    ids: selected,
    noteIds: notesOf(selected),
    group: activeGroup,
  });
}

function scoreY(clientY) {
  return clientY - scoreEl.getBoundingClientRect().top + scoreEl.scrollTop;
}

function headCentre(el) {
  const rect = headOf(el).getBoundingClientRect();
  return {
    x: scoreX(rect.left + rect.width / 2),
    y: scoreY(rect.top + rect.height / 2),
    radius: Math.max(rect.width, rect.height),
  };
}

// The edges joining points into one tree with the least total length, so that
// a blob follows its notes instead of covering all that lies between them.
function spanningTree(points) {
  const edges = [];
  const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  const best = points.map((p) => ({ from: points[0], d: distance(points[0], p) }));
  const done = points.map((_, i) => i === 0);
  for (let count = 1; count < points.length; count++) {
    let next = -1;
    best.forEach((entry, i) => {
      if (!done[i] && (next < 0 || entry.d < best[next].d)) next = i;
    });
    edges.push([best[next].from, points[next]]);
    done[next] = true;
    points.forEach((p, i) => {
      const d = distance(points[next], p);
      if (!done[i] && d < best[i].d) best[i] = { from: points[next], d };
    });
  }
  return edges;
}

function svgElement(name, attributes) {
  const el = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) el.setAttribute(key, value);
  return el;
}

function drawGroups() {
  scoreEl.querySelector("#tilia-groups")?.remove();
  scoreEl.querySelector("#tilia-group-labels")?.remove();
  blobShapes = [];
  if (!pages().length || !groups.length) return;
  const { width, height } = contentSize();
  const overlay = svgElement("svg", { id: "tilia-groups", width, height });
  // Blobs go behind the score, and labels in front, to be read over the notes.
  const labels = svgElement("svg", { id: "tilia-group-labels", width, height });
  for (const group of groups) {
    const points = group.ids
      .map((id) => document.getElementById(id))
      .filter(Boolean)
      .map(headCentre);
    if (!points.length) continue;
    const radius = Math.max(...points.map((p) => p.radius));
    const blob = svgElement("g", {
      class: group.id === activeGroup ? "blob active" : "blob",
      "data-group": group.id,
      fill: group.color,
      stroke: group.color,
      "stroke-width": radius * 2,
      "stroke-linecap": "round",
    });
    for (const p of points) {
      blob.append(svgElement("circle", { cx: p.x, cy: p.y, r: radius, stroke: "none" }));
    }
    const edges = spanningTree(points);
    for (const [a, b] of edges) {
      blob.append(svgElement("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y }));
    }
    blobShapes.push({ id: group.id, points, edges, radius });
    overlay.append(blob);
    const top = points.reduce((a, b) => (b.y < a.y ? b : a));
    const text = svgElement("text", { x: top.x - radius, y: Math.max(11, top.y - radius - 3) });
    text.textContent = group.text;
    labels.append(text);
  }
  scoreEl.append(overlay, labels);
  separateLabels(labels);
}

// A highlight's rectangles, one in each system it reaches.
function highlightRects(highlight) {
  const rects = [];
  for (const system of systems) {
    const qStart = Math.max(highlight.qStart, system.qStart);
    const qEnd = Math.min(highlight.qEnd, system.qEnd);
    if (qEnd <= qStart) continue;
    const x = xAt(system, qStart);
    rects.push({
      x,
      y: system.bandTop,
      width: xAt(system, qEnd) - x,
      height: system.bandBottom - system.bandTop,
    });
  }
  return rects;
}

function drawHighlights() {
  scoreEl.querySelector("#tilia-highlights")?.remove();
  if (!pages().length || !highlights.length) return;
  const { width, height } = contentSize();
  const layer = svgElement("svg", { id: "tilia-highlights", width, height });
  for (const highlight of highlights) {
    for (const rect of highlightRects(highlight)) layer.append(svgElement("rect", rect));
  }
  scoreEl.append(layer);
}

// Scrolls to the first highlight, unless one is in view.
function revealHighlights() {
  const rects = highlights.flatMap(highlightRects);
  if (!rects.length) return;
  const left = scoreEl.scrollLeft;
  const right = left + scoreEl.clientWidth;
  const top = scoreEl.scrollTop;
  const bottom = top + scoreEl.clientHeight;
  const inView = (r) => r.x + r.width > left && r.x < right && r.y + r.height > top && r.y < bottom;
  if (rects.some(inView)) return;
  const [first] = rects;
  scoreEl.scrollLeft = first.x - scoreEl.clientWidth / 10;
  const system = systemAtY(first.y + first.height / 2);
  revealY(system.top, system.bottom, false);
  reportViewport(false);
}

function separateLabels(labels) {
  // Up while there's room, and then to the right of the label in the way.
  const placed = [];
  for (const text of labels.querySelectorAll("text")) {
    for (let tries = 0; tries < 20; tries++) {
      const box = text.getBBox();
      const hit = placed.find(
        (other) =>
          box.x < other.x + other.width &&
          other.x < box.x + box.width &&
          box.y < other.y + other.height &&
          other.y < box.y + box.height,
      );
      if (!hit) break;
      const y = Number(text.getAttribute("y"));
      if (hit.y - box.height - 1 >= 0) {
        text.setAttribute("y", y - (box.y + box.height - hit.y) - 1);
      } else {
        text.setAttribute("x", hit.x + hit.width + 6);
      }
    }
    placed.push(text.getBBox());
  }
}

function distanceToSegment(p, a, b) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const length2 = dx * dx + dy * dy;
  const t = length2
    ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / length2))
    : 0;
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

function groupAt(clientX, clientY) {
  // The score lies over the blobs, so it's worked out from their shapes. Of
  // overlapping blobs, the one drawn last.
  const p = { x: scoreX(clientX), y: scoreY(clientY) };
  for (const shape of [...blobShapes].reverse()) {
    const near = (a, b) => distanceToSegment(p, a, b) <= shape.radius;
    if (shape.points.some((a) => near(a, a)) || shape.edges.some(([a, b]) => near(a, b))) {
      return shape.id;
    }
  }
  return null;
}

function activateGroup(id) {
  activeGroup = id;
  const group = groups.find((each) => each.id === id);
  drawGroups();
  select(group ? group.ids : []);
}

scoreEl.addEventListener("click", (event) => {
  if (wasDragged) {
    wasDragged = false;
    return;
  }
  const el = clickable(event.target);
  const keep = event.ctrlKey || event.metaKey || event.shiftKey;
  if (!el && !keep) {
    const group = groupAt(event.clientX, event.clientY);
    if (group !== null) {
      activateGroup(group);
      return;
    }
  }
  if (!keep && activeGroup !== null) {
    activeGroup = null;
    drawGroups();
  }
  let ids = keep ? selectedIds() : [];
  if (el) {
    ids = ids.includes(el.id) ? ids.filter((id) => id !== el.id) : [...ids, el.id];
  }
  select(ids);
});

function insideScoreBox(event) {
  const rect = scoreEl.getBoundingClientRect();
  // Not on a scrollbar.
  return (
    event.clientX - rect.left < scoreEl.clientWidth &&
    event.clientY - rect.top < scoreEl.clientHeight
  );
}

scoreEl.addEventListener("mousedown", (event) => {
  if (event.button !== 0 || !insideScoreBox(event)) return;
  band = { x: event.clientX, y: event.clientY, el: null };
  wasDragged = false;
});

window.addEventListener("mousemove", (event) => {
  if (!band) return;
  const moved = Math.hypot(event.clientX - band.x, event.clientY - band.y);
  if (!band.el) {
    if (moved < DRAG_THRESHOLD) return;
    band.el = document.createElement("div");
    band.el.id = "tilia-band";
    document.body.append(band.el);
  }
  const { el } = band;
  el.style.left = `${Math.min(event.clientX, band.x)}px`;
  el.style.top = `${Math.min(event.clientY, band.y)}px`;
  el.style.width = `${Math.abs(event.clientX - band.x)}px`;
  el.style.height = `${Math.abs(event.clientY - band.y)}px`;
});

window.addEventListener("mouseup", (event) => {
  if (!band) return;
  const { el } = band;
  const start = band;
  band = null;
  if (!el) return;
  el.remove();
  wasDragged = true;
  const left = Math.min(event.clientX, start.x);
  const right = Math.max(event.clientX, start.x);
  const top = Math.min(event.clientY, start.y);
  const bottom = Math.max(event.clientY, start.y);
  const inside = [...scoreEl.querySelectorAll("g.note")]
    .filter((note) => {
      const rect = headOf(note).getBoundingClientRect();
      return rect.right > left && rect.left < right && rect.bottom > top && rect.top < bottom;
    })
    .map((note) => note.id);
  const keep = event.ctrlKey || event.metaKey || event.shiftKey;
  if (!keep && activeGroup !== null) {
    activeGroup = null;
    drawGroups();
  }
  select(keep ? [...new Set([...selectedIds(), ...inside])] : inside);
});

scoreEl.addEventListener(
  "wheel",
  (event) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom * (event.deltaY < 0 ? 1.15 : 1 / 1.15)));
    if (layout === "pages") {
      scheduleRelayout();
      return;
    }
    fit();
    reportViewport(false);
  },
  { passive: false },
);

scoreEl.addEventListener("dblclick", (event) => {
  const el = clickable(event.target);
  if (!el) return;
  const q = onsetOf(el);
  const measureEl = el.closest("g.measure");
  const m = measures.find((each) => measureEl && each.id === measureEl.id);
  send("onElementDoubleClicked", { id: el.id, ...(m ? positionIn(m, q) : positionAt(q)) });
});

scoreEl.addEventListener("scroll", () => reportViewport(false));

window.addEventListener("resize", () => {
  if (layout === "pages" && scoreEl.clientWidth !== layoutWidth) {
    scheduleRelayout();
    return;
  }
  fit();
  reportViewport(false);
});

function scheduleRelayout() {
  clearTimeout(relayoutTimer);
  relayoutTimer = setTimeout(relayout, RELAYOUT_DELAY);
}

// Lays the score out again, as the layout, the zoom or the box's width
// changed, and keeps in view the part of the score that was.
function relayout() {
  clearTimeout(relayoutTimer);
  if (!measures.length) return;
  const shown = systems.length ? visibleSystems()[0] : null;
  const q = shown ? interpolate(shown.anchors, "x", "q", scoreEl.scrollLeft) : 0;
  setLayoutOptions();
  toolkit.redoLayout();
  showPages();
  scoreEl.scrollLeft = 0;
  scoreEl.scrollTop = 0;
  fit();
  const system = systemAtQ(q);
  if (system) {
    scoreEl.scrollLeft = xAt(system, q) - scoreEl.clientWidth / 10;
    revealY(system.top, system.bottom, false);
  }
  reportViewport(true);
}

// Shows a score, in `newLayout`: "continuous" or "pages".
window.tiliaLoadScore = (text, newLayout) => {
  try {
    layout = newLayout === "pages" ? "pages" : "continuous";
    scoreEl.replaceChildren();
    setLayoutOptions();
    if (!toolkit.loadData(text)) {
      send("onError", { message: "Verovio could not read the score." });
      return;
    }
    colors = new Map();
    activeGroup = null;
    showPages();
    highlights = [];
    readTimemap(toolkit.renderToTimemap({ includeRests: true, includeMeasures: true }));
    fit();
    send("onScoreLoaded", { mei: toolkit.getMEI() });
    reportViewport(true);
  } catch (error) {
    send("onError", { message: String(error) });
  }
};

window.tiliaScrollTo = (measure, fraction, centered) => {
  const q = qAt(measure, fraction);
  if (q === null || !systems.length) return;
  const system = systemAtQ(q);
  const x = xAt(system, q);
  revealY(system.top, system.bottom, centered);
  const width = scoreEl.clientWidth;
  const margin = width / 10;
  const left = scoreEl.scrollLeft;
  if (centered) {
    scoreEl.scrollLeft = x - width / 2;
  } else if (!(left + margin < x && x < left + width - margin)) {
    scoreEl.scrollLeft = x - width / 2 + margin * 4;
  }
  reportViewport(false);
};

window.tiliaSetColors = (newColors) => {
  for (const [id, color] of Object.entries(newColors)) {
    paint(id, color);
    if (color) colors.set(id, color);
    else colors.delete(id);
  }
};

window.tiliaReportViewport = () => reportViewport(true);

// Shows the score in one system scrolled sideways ("continuous"), or in pages
// as wide as the box, scrolled down ("pages").
window.tiliaSetLayout = (newLayout) => {
  const next = newLayout === "pages" ? "pages" : "continuous";
  if (next === layout) return;
  layout = next;
  zoom = 1;
  relayout();
};

// Shades score ranges, each a start measure and fraction and an end measure
// and fraction, and, if `reveal`, scrolls to them unless one is in view. A
// range that runs past the score, as beats past its last measure do, is cut at
// the score's ends.
window.tiliaSetHighlights = (ranges, reveal) => {
  const first = measures[0]?.qStart ?? 0;
  const last = measures.at(-1)?.qEnd ?? 0;
  highlights = ranges
    .map(([startMeasure, startFraction, endMeasure, endFraction]) => {
      const qStart = qAt(startMeasure, startFraction);
      const qEnd = qAt(endMeasure, endFraction);
      if (qStart === null && qEnd === null) return null;
      return { qStart: qStart ?? first, qEnd: qEnd ?? last };
    })
    .filter((highlight) => highlight && highlight.qEnd > highlight.qStart);
  drawHighlights();
  if (reveal) revealHighlights();
};

// Makes a group the active one, and scrolls to it unless it's all in view.
window.tiliaShowGroup = (id) => {
  activateGroup(id);
  const shape = blobShapes.find((each) => each.id === id);
  if (!shape) return;
  const xs = shape.points.map((p) => p.x);
  const ys = shape.points.map((p) => p.y);
  revealY(Math.min(...ys) - shape.radius, Math.max(...ys) + shape.radius, false);
  const start = Math.min(...xs) - shape.radius;
  const end = Math.max(...xs) + shape.radius;
  const left = scoreEl.scrollLeft;
  const width = scoreEl.clientWidth;
  if (start < left || end > left + width) {
    // A group wider than the box shows its start.
    scoreEl.scrollLeft = end - start < width ? (start + end - width) / 2 : start;
  }
  reportViewport(false);
};

// `active` makes that group the active one, with its notes selected. Otherwise
// the active group stays, unless it's gone.
window.tiliaSetGroups = (newGroups, active) => {
  groups = newGroups;
  if (active !== null && active !== undefined) {
    activateGroup(active);
    return;
  }
  if (activeGroup !== null && !groups.some((group) => group.id === activeGroup)) {
    activeGroup = null;
    select([]);
  }
  drawGroups();
  // Whatever the panel shows of the active group may have changed.
  select(selectedIds());
};

new QWebChannel(qt.webChannelTransport, (channel) => {
  bridge = channel.objects.tilia;
  onReady();
});

function startToolkit() {
  toolkit = new verovio.toolkit();
  toolkit.setOptions(OPTIONS);
  onReady();
}

// viewer.html loads the toolkit after this script. The toolkit's load event
// fires as soon as it has run, while its WebAssembly is still being compiled,
// so its runtime can't be ready before we ask to hear of it. (Verovio 6.3
// doesn't set Module.calledRun, so a script after the toolkit can't tell
// whether the runtime is already ready.)
document.addEventListener(
  "load",
  (event) => {
    if (event.target.id === "verovio-toolkit") {
      verovio.module.onRuntimeInitialized = startToolkit;
    }
  },
  true, // a script's load event doesn't bubble
);
