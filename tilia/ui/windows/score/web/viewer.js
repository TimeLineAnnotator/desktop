"use strict";
// TiLiA's score viewer. Python calls the `tilia*` functions below with
// runJavaScript, and hears back through the `tilia` object on the web channel.
//
// Score positions go between the two sides as a measure number (MEI's @n)
// and a fraction of that measure; Python turns them into times with the beat
// timeline. Inside the page, positions are quarter notes from the start of
// the score (Verovio's qstamp).

const OPTIONS = {
  breaks: "none", // one system, scrolled horizontally
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

const scoreEl = document.getElementById("score");
let toolkit = null;
let bridge = null;
let measures = []; // {id, n, qStart, qEnd}, in score order
let onsets = new Map(); // element id -> qstamp of its onset
let anchors = []; // {q, x}, both increasing; x in pixels from the score's left
let lastViewport = "";

function send(slot, payload) {
  if (bridge) bridge[slot](JSON.stringify(payload));
}

function onReady() {
  if (bridge && toolkit) bridge.viewerReady();
}

function showSvg(text) {
  // Parsed as XML and imported, never assigned to innerHTML.
  const doc = new DOMParser().parseFromString(text, "image/svg+xml");
  if (doc.documentElement.nodeName !== "svg") {
    throw new Error("Verovio returned no SVG.");
  }
  scoreEl.replaceChildren(document.importNode(doc.documentElement, true));
}

function readTimemap(timemap) {
  measures = [];
  onsets = new Map();
  let qEnd = 0;
  for (const entry of timemap) {
    if (entry.measureOn && !measures.some((m) => m.id === entry.measureOn)) {
      const el = document.getElementById(entry.measureOn);
      measures.push({
        id: entry.measureOn,
        n: el ? el.getAttribute("data-n") : null,
        qStart: entry.qstamp,
      });
    }
    for (const id of entry.on || []) {
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

function measureAnchors() {
  const byQ = new Map();
  const add = (q, x) => {
    if (!byQ.has(q) || x < byQ.get(q)) byQ.set(q, x);
  };
  for (const m of measures) {
    const line = document.querySelector(`[id="${m.id}"] .staff > path`);
    if (line) add(m.qStart, scoreX(line.getBoundingClientRect().left));
  }
  for (const [id, q] of onsets) {
    const el = document.getElementById(id);
    if (el) add(q, scoreX(headOf(el).getBoundingClientRect().left));
  }
  const last = measures[measures.length - 1];
  const line = last && document.querySelector(`[id="${last.id}"] .staff > path`);
  if (line) byQ.set(last.qEnd, scoreX(line.getBoundingClientRect().right));

  anchors = [];
  for (const [q, x] of [...byQ].sort((a, b) => a[0] - b[0])) {
    if (!anchors.length || x > anchors[anchors.length - 1].x) anchors.push({ q, x });
  }
}

function interpolate(from, to, value) {
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

function fit() {
  const svg = scoreEl.querySelector("svg");
  if (!svg) return;
  const [, , width, height] = svg.getAttribute("viewBox").split(/\s+/).map(Number);
  const k = Math.min(1, scoreEl.clientHeight / height);
  svg.style.width = `${width * k}px`;
  svg.style.height = `${height * k}px`;
  measureAnchors();
}

function reportViewport(force) {
  if (!measures.length) return;
  const left = scoreEl.scrollLeft;
  const right = left + scoreEl.clientWidth;
  const payload = {
    start: positionAt(interpolate("x", "q", left)),
    end: positionAt(interpolate("x", "q", right)),
  };
  const key = JSON.stringify(payload);
  if (!force && key === lastViewport) return;
  lastViewport = key;
  send("onViewportChanged", payload);
}

function clickable(target) {
  return target.closest ? target.closest("g.note, g.rest, g.chord") : null;
}

function onsetOf(el) {
  if (onsets.has(el.id)) return onsets.get(el.id);
  const notes = [...el.querySelectorAll("g.note")].filter((n) => onsets.has(n.id));
  if (notes.length) return Math.min(...notes.map((n) => onsets.get(n.id)));
  return interpolate("x", "q", scoreX(headOf(el).getBoundingClientRect().left));
}

function selectedIds() {
  return [...scoreEl.querySelectorAll(".tilia-selected")].map((el) => el.id);
}

function select(ids) {
  scoreEl.querySelectorAll(".tilia-selected").forEach((el) => {
    el.classList.remove("tilia-selected");
  });
  for (const id of ids) {
    const el = document.getElementById(id);
    if (el) el.classList.add("tilia-selected");
  }
  send("onSelectionChanged", { ids: selectedIds() });
}

scoreEl.addEventListener("click", (event) => {
  const el = clickable(event.target);
  const keep = event.ctrlKey || event.metaKey || event.shiftKey;
  let ids = keep ? selectedIds() : [];
  if (el) {
    ids = ids.includes(el.id) ? ids.filter((id) => id !== el.id) : [...ids, el.id];
  }
  select(ids);
});

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
  fit();
  reportViewport(false);
});

window.tiliaLoadScore = (text) => {
  try {
    if (!toolkit.loadData(text)) {
      send("onError", { message: "Verovio could not read the score." });
      return;
    }
    showSvg(toolkit.renderToSVG(1));
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
  if (q === null) return;
  const x = interpolate("q", "x", q);
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

window.tiliaSetColors = (colors) => {
  for (const [id, color] of Object.entries(colors)) {
    const el = document.getElementById(id);
    if (!el) continue;
    el.style.color = color || "";
    el.style.fill = color || "";
  }
};

window.tiliaSelect = (ids) => select(ids);

new QWebChannel(qt.webChannelTransport, (channel) => {
  bridge = channel.objects.tilia;
  onReady();
});

function startToolkit() {
  toolkit = new verovio.toolkit();
  toolkit.setOptions(OPTIONS);
  onReady();
}

// Under the page's CSP, the runtime is ready before this script runs.
if (verovio.module.calledRun) {
  startToolkit();
} else {
  verovio.module.onRuntimeInitialized = startToolkit;
}
