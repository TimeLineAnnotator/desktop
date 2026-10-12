// Drives web/js/liveness.js under node with a stand-in DOM and prints what the
// page would show, as JSON, for tests/test_liveness_js.py.
//
//     node liveness_harness.mjs /path/to/web/js

import { pathToFileURL } from "node:url";

const results = {};

function element(props = {}) {
  const listeners = {};
  return {
    hidden: false,
    textContent: "",
    className: "",
    innerHTML: "",
    dataset: {},
    addEventListener(type, fn) { (listeners[type] ??= []).push(fn); },
    async fire(type) { for (const fn of listeners[type] ?? []) await fn(); },
    ...props,
  };
}

const changed = element({ hidden: true });
const rerunButton = element();
const status = element();
const filesPanel = element({ dataset: { panel: "files" } });
const known = { "#changed": changed, "#changed-rerun": rerunButton, "#status": status };
const others = new Map();
const documentListeners = {};

globalThis.document = {
  visibilityState: "visible",
  querySelector(sel) {
    if (sel in known) return known[sel];
    if (!others.has(sel)) others.set(sel, element());
    return others.get(sel);
  },
  querySelectorAll(sel) { return sel === "section.panel" ? [filesPanel] : []; },
  getElementById(id) { return id === "status" ? status : element(); },
  addEventListener(type, fn) { (documentListeners[type] ??= []).push(fn); },
};
globalThis.window = globalThis;
globalThis.location = { href: "http://127.0.0.1:1/", search: "" };
globalThis.setInterval = () => 0;

let stateReply = { generation: 1, scanning: false, last_scan: null };
const library = {
  corpora: [{ id: "c-1", name: "Corpus", path: "/corpus", available: true }],
  last_corpus: "c-1",
  notices: [],
};
globalThis.fetch = async url => ({
  ok: true,
  json: async () => (url.endsWith("/api/library") ? library : stateReply),
});

const js = pathToFileURL(process.argv[2].replace(/\/?$/, "/"));
const corpus = await import(new URL("corpus.js", js));
const liveness = await import(new URL("liveness.js", js));

await corpus.bootLibrary();
liveness.startPolling();
const poll = async () => { for (const fn of documentListeners.visibilitychange ?? []) await fn(); };
await poll();

// 1. The notice shows when the generation moved on.
liveness.noteGeneration("files", 1);
stateReply = { generation: 2, scanning: false, last_scan: "t1" };
await poll();
results.notice_after_change = !changed.hidden;

// 2. A failed re-run keeps the notice and shows the error.
liveness.onRerun("files", async () => { throw new Error("reload failed"); });
await rerunButton.fire("click");
results.notice_after_failed_rerun = !changed.hidden;
results.status_after_failed_rerun = status.textContent;
results.status_class_after_failed_rerun = status.className;

// 3. A re-run that works hides it.
liveness.onRerun("files", async () => { liveness.noteGeneration("files", 2); });
await rerunButton.fire("click");
results.notice_after_good_rerun = !changed.hidden;

// 4. "Rescanning…" clears once a scan has ended (seen running, then not).
status.textContent = liveness.RESCANNING;
status.className = "";
stateReply = { generation: 2, scanning: true, last_scan: "t1" };
await poll();
results.status_while_scanning = status.textContent;
stateReply = { generation: 2, scanning: false, last_scan: "t1" };
await poll();
results.status_after_scan_seen_ending = status.textContent;

// 5. ... or when last_scan moved on between two polls, even if the scan itself
//    was too quick to be seen running.
status.textContent = liveness.RESCANNING;
await poll();
results.status_without_a_scan = status.textContent;
stateReply = { generation: 2, scanning: false, last_scan: "t2" };
await poll();
results.status_after_last_scan_moved = status.textContent;

// 6. Another message in the status bar is left alone.
status.textContent = "something else";
stateReply = { generation: 2, scanning: false, last_scan: "t3" };
await poll();
results.other_status_kept = status.textContent;

process.stdout.write(JSON.stringify(results));
