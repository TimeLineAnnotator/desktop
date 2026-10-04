import { CORPUS, bootLibrary } from './corpus.js';
import { loadFiles } from './files.js';
import { startPolling } from './liveness.js';
import { qa } from './lib/dom.js';
import { notAvailable, panelSection, showPanel, urlPanel } from './panels.js';
import { loadQuery } from './query.js';
import { loadStatistics } from './statistics.js';
import { errMsg, setStatus } from './util.js';

function openPanel(name) {
  showPanel(name);
  if (name === "files") loadFiles().catch(e => setStatus(String(e), "error"));
  if (name === "query") loadQuery();
  if (name === "statistics") loadStatistics();
}

for (const tab of qa(document, "#tabs button")) {
  tab.addEventListener("click", () => openPanel(tab.dataset.panel));
}
for (const name of ["categories", "edit-log"]) {
  notAvailable(panelSection(name), "a later version of TiLiA Library");
}

bootLibrary().then(() => {
  if (CORPUS) {
    openPanel(urlPanel());
    startPolling();
  }
}).catch(e => setStatus(errMsg(0, { error: String(e) }), "error"));

window.__bootOk = true;
