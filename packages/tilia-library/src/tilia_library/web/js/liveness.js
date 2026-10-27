import { CORPUS } from './corpus.js';
import { q, qa } from './lib/dom.js';
import { setStatus } from './util.js';

const POLL_MS = 2000;
export const RESCANNING = "Rescanning…";  // the status while a requested rescan runs

const noted = new Map();     // panel -> the generation of the data it shows
const reruns = new Map();    // panel -> what "Re-run" does for it
let latest = null;           // the generation of the last successful poll
let lastScan = null;         // the last_scan of the last successful poll
let scanning = false;        // whether the last successful poll saw a scan running
let polling = false;

/** The generation of the data a panel now shows (null when it shows none). */
export function noteGeneration(panel, generation) {
  noted.set(panel, generation);
  refresh();
}

/** What "Re-run" does for a panel. */
export function onRerun(panel, fn) {
  reruns.set(panel, fn);
}

function activePanel() {
  const section = Array.from(qa(document, "section.panel")).find(s => !s.hidden);
  return section ? section.dataset.panel : null;
}

function refresh() {
  const shown = noted.get(activePanel());
  const changed = shown != null && typeof latest === "number" && latest !== shown;
  q(document, "#changed").hidden = !changed;
}

async function poll() {
  if (!CORPUS || document.visibilityState !== "visible" || polling) return;
  polling = true;
  try {
    const r = await fetch("/api/state");
    if (!r.ok) return;
    const data = await r.json();
    latest = data.generation;
    // A scan ended: one was running and is not, or last_scan moved on.
    const ended = (scanning && !data.scanning) || (lastScan != null && data.last_scan !== lastScan);
    scanning = Boolean(data.scanning);
    lastScan = data.last_scan;
    if (ended && q(document, "#status").textContent === RESCANNING) setStatus("", "");
    refresh();
  } catch (e) {
    // a failed poll changes nothing
  } finally {
    polling = false;
  }
}

async function rerun() {
  const fn = reruns.get(activePanel());
  if (fn) {
    try {
      await fn();
    } catch (e) {
      // The panel still shows the old data, so the notice stays with the error.
      setStatus(String(e), "error");
      return;
    }
  }
  q(document, "#changed").hidden = true;
}

/** Poll the active corpus's state while the page is visible. */
export function startPolling() {
  if (!CORPUS) return;
  q(document, "#changed-rerun").addEventListener("click", rerun);
  for (const tab of qa(document, "#tabs button")) tab.addEventListener("click", refresh);
  document.addEventListener("visibilitychange", poll);
  setInterval(poll, POLL_MS);
  poll();
}
