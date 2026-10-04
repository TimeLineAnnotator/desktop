import { CORPUS } from './corpus.js';
import { q, qa } from './lib/dom.js';
import { setStatus } from './util.js';

const POLL_MS = 2000;

const noted = new Map();     // panel -> the generation of the data it shows
const reruns = new Map();    // panel -> what "Re-run" does for it
let latest = null;           // the generation of the last successful poll
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
      setStatus(String(e), "error");
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
