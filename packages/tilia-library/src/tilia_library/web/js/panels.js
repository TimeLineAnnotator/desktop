import { q, qa } from './lib/dom.js';

export const PANELS = ["files", "query", "categories", "statistics", "edit-log"];

/** Show one panel, mark its tab, and keep it in the URL. */
export function showPanel(name) {
  if (!PANELS.includes(name)) name = "files";
  for (const section of qa(document, "section.panel")) section.hidden = section.dataset.panel !== name;
  for (const tab of qa(document, "#tabs button")) tab.classList.toggle("active", tab.dataset.panel === name);
  const url = new URL(location.href);
  if (name === "files") url.searchParams.delete("panel");
  else url.searchParams.set("panel", name);
  history.replaceState(null, "", url);
}

/** The panel named in the URL, or files. */
export function urlPanel() {
  const name = new URLSearchParams(location.search).get("panel");
  return PANELS.includes(name) ? name : "files";
}

export function panelSection(name) {
  return q(document, `section.panel[data-panel="${name}"]`);
}

/** Fill a panel with the message that its data isn't there yet. */
export function notAvailable(section, needs) {
  section.innerHTML = "";
  const head = document.createElement("p");
  head.textContent = "Not available yet";
  const why = document.createElement("p");
  why.className = "muted";
  why.textContent = `This needs ${needs}.`;
  section.append(head, why);
}
