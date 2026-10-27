import { CORPUS } from './corpus.js';
import { downloadCsv, toCsv } from './csv.js';
import { closest, evTarget, q, qInput } from './lib/dom.js';
import { noteGeneration, onRerun } from './liveness.js';
import { notAvailable, panelSection } from './panels.js';
import { TABLEAU } from './palette.js';
import { query } from './state.js';
import { errMsg, escapeHtml, setStatus } from './util.js';

const ROW_CAP = 1000;     // table rows drawn
const SERIES_CAP = 12;    // datasets in a chart; the smallest series are summed as "other"
const CHART_JS = "/web/vendor/chart.js/chart.umd.js";
const OTHER = "other";
const OTHER_COLOR = "#9c9c9c";
const KEYS = ["label", "category", "file", "timeline"];

const section = () => panelSection("statistics");

let charts = [];          // the Chart instances on the page now
let answer = null;        // the last successful answer
let seq = 0;              // the newest request; an older answer is dropped
let chartJs = null;       // promise of window.Chart, once asked for

// ---- the query to show statistics of --------------------------------------- //

/** The query panel's text: its box when it is built, else what it remembered. */
function queryText() {
  const box = document.querySelector("#ql-box");
  if (box) return /** @type {HTMLTextAreaElement} */ (box).value;
  try { return localStorage.getItem(`tilia-library.query.${CORPUS}`) || ""; } catch (e) { return ""; }
}

function showQuery() {
  const root = section();
  const text = queryText();
  const empty = !text.trim();
  q(root, "#stats-query").textContent = empty ? "Write a query in the Query tab first." : text;
  qInput(root, "#stats-run").disabled = empty;
}

// ---- Chart.js ------------------------------------------------------------- //

/** Chart.js, added as a script the first time a chart is wanted. */
function loadChartJs() {
  if (!chartJs) {
    chartJs = new Promise((resolve, reject) => {
      if (window.Chart) { resolve(window.Chart); return; }
      const script = document.createElement("script");
      script.src = CHART_JS;
      script.onload = () => resolve(window.Chart);
      script.onerror = () => { chartJs = null; reject(new Error("Chart.js did not load")); };
      document.head.append(script);
    });
  }
  return chartJs;
}

function destroyCharts() {
  for (const chart of charts) chart.destroy();
  charts = [];
}

/** The datasets of a bar chart: [labels, [{label, data}]]. */
function chartData(table, chart) {
  const x = table.columns.indexOf(chart.x), y = table.columns.indexOf(chart.y);
  const s = chart.series ? table.columns.indexOf(chart.series) : -1;
  const labels = [];
  for (const row of table.rows) {
    const label = String(row[x]);
    if (!labels.includes(label)) labels.push(label);
  }
  const value = row => (typeof row[y] === "number" ? row[y] : 0);
  if (s < 0) {
    const data = labels.map(() => 0);
    for (const row of table.rows) data[labels.indexOf(String(row[x]))] += value(row);
    return [labels, [{ label: chart.y, data }]];
  }
  const totals = new Map();
  for (const row of table.rows) totals.set(String(row[s]), (totals.get(String(row[s])) || 0) + value(row));
  const ranked = Array.from(totals.keys()).sort((a, b) => totals.get(b) - totals.get(a));
  const kept = ranked.length > SERIES_CAP ? ranked.slice(0, SERIES_CAP - 1) : ranked;
  const sets = new Map(kept.map(name => [name, labels.map(() => 0)]));
  if (kept.length < ranked.length) sets.set(OTHER, labels.map(() => 0));
  for (const row of table.rows) {
    const name = String(row[s]);
    const data = sets.get(name) || sets.get(OTHER);
    data[labels.indexOf(String(row[x]))] += value(row);
  }
  return [labels, Array.from(sets, ([label, data]) => ({ label, data }))];
}

function drawChart(Chart, canvas, table) {
  const chart = table.chart;
  const [labels, sets] = chartData(table, chart);
  const stacked = Boolean(chart.series);
  const datasets = sets.map((set, i) => ({
    ...set,
    backgroundColor: set.label === OTHER && stacked ? OTHER_COLOR : TABLEAU[i % TABLEAU.length],
  }));
  charts.push(new Chart(canvas, {
    type: "bar",
    data: { labels, datasets },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: stacked } },
      scales: {
        x: { stacked, title: { display: true, text: chart.x } },
        y: { stacked, beginAtZero: true, title: { display: true, text: chart.y } },
      },
    },
  }));
}

// ---- the answer ----------------------------------------------------------- //

function cellHtml(value) {
  if (value === null || value === undefined) return '<td dir="auto"></td>';
  const num = typeof value === "number" ? ' class="num"' : "";
  return `<td dir="auto"${num}>${escapeHtml(value)}</td>`;
}

function tableHtml(table) {
  const head = table.columns.map(c => `<th dir="auto">${escapeHtml(c)}</th>`).join("");
  const body = table.rows.slice(0, ROW_CAP).map(row => `<tr>${row.map(cellHtml).join("")}</tr>`).join("");
  const more = table.rows.length > ROW_CAP
    ? `<p class="muted">Showing the first ${ROW_CAP.toLocaleString("en")} of ${table.rows.length.toLocaleString("en")} rows; the CSV has all of them.</p>`
    : "";
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>${more}`;
}

function tableSection(table) {
  const name = escapeHtml(table.name);
  const chart = table.chart ? '<div class="stats-chart"><canvas></canvas></div>' : "";
  return `<section class="stats-table" data-table="${name}"><h3 dir="auto">${escapeHtml(table.title)}</h3>` +
    `${chart}${tableHtml(table)}<button type="button" class="stats-csv" data-table="${name}">CSV</button></section>`;
}

function exportCsv(name) {
  const table = answer && answer.tables.find(t => t.name === name);
  if (!table) return;
  const rows = table.rows.map(row => Object.fromEntries(table.columns.map((c, i) => [c, row[i]])));
  downloadCsv(`${CORPUS}-${name}.csv`, toCsv(table.columns, rows));
}

async function render(data) {
  const root = section();
  destroyCharts();
  const warnings = q(root, "#stats-warnings");
  warnings.innerHTML = data.warnings.map(w => `<li>${escapeHtml(w)}</li>`).join("");
  warnings.hidden = !data.warnings.length;
  q(root, "#stats-tables").innerHTML = data.tables.map(tableSection).join("");
  if (!data.tables.some(t => t.chart)) return;
  try {
    const Chart = await loadChartJs();
    if (answer !== data) return;    // a newer answer has replaced this one
    Chart.defaults.font.family = '-apple-system, "Segoe UI", system-ui, sans-serif';
    Chart.defaults.font.size = 12;
    for (const table of data.tables) {
      if (!table.chart) continue;
      const canvas = q(root, `.stats-table[data-table="${table.name}"] canvas`);
      if (canvas) drawChart(Chart, canvas, table);
    }
  } catch (e) {
    setStatus(String(e), "error");
  }
}

// ---- running -------------------------------------------------------------- //

function keys() {
  const root = section();
  const field = qInput(root, "#stats-field").value.trim();
  const first = field || qInput(root, "#stats-by").value;
  const second = qInput(root, "#stats-by2").value;
  return second ? [first, second] : [first];
}

function showError(message) {
  const el = q(section(), "#stats-error");
  el.textContent = message;
  el.hidden = !message;
}

async function run() {
  const root = section();
  const text = queryText();
  if (!text.trim()) { showQuery(); return; }
  const mine = ++seq;
  showError("");
  const r = await fetch("/api/statistics", {
    method: "POST",
    body: JSON.stringify({ query: text, by: keys(), fold: qInput(root, "#stats-fold").checked, tab: query.tab }),
  });
  const data = await r.json().catch(() => null);
  if (mine !== seq) return;
  if (r.status === 501) {
    destroyCharts();
    answer = null;
    notAvailable(root, data.needs);
    return;
  }
  if (!r.ok) { showError(errMsg(r.status, data)); return; }
  answer = data;
  await render(data);
  noteGeneration("statistics", data.generation);
}

function buildShell() {
  const root = section();
  const options = list => list.map(k => `<option value="${k}">${k}</option>`).join("");
  root.innerHTML = '<div class="bar stats-bar"><span>Statistics of the query in the Query tab:</span> <span id="stats-query" class="stats-query" dir="auto"></span></div>' +
    '<div class="bar stats-bar"><label>By <select id="stats-by">' + options(KEYS) + "</select></label>" +
    '<label>and <select id="stats-by2"><option value="">(none)</option>' + options(KEYS) + "</select></label>" +
    '<input id="stats-field" type="search" placeholder="or a field, e.g. file.composer" aria-label="Field">' +
    '<label><input id="stats-fold" type="checkbox"> Fold subtypes</label>' +
    '<button id="stats-run" type="button">Show statistics</button></div>' +
    '<div id="stats-error" class="stats-error" role="alert" hidden></div>' +
    '<ul id="stats-warnings" class="stats-warnings" hidden></ul><div id="stats-tables"></div>';
  q(root, "#stats-run").addEventListener("click", () => {
    run().catch(e => setStatus(String(e), "error"));
  });
  q(root, "#stats-tables").addEventListener("click", e => {
    const button = closest(evTarget(e), "button.stats-csv");
    if (button) exportCsv(button.dataset.table);
  });
}

/** Called each time the panel is shown. */
export function loadStatistics() {
  if (!section().querySelector("#stats-run")) buildShell();
  showQuery();
}

onRerun("statistics", run);
