import { CORPUS } from './corpus.js';
import { closest, q } from './lib/dom.js';
import { errMsg, escapeHtml, mmss, setStatus } from './util.js';

const YOUTUBE_ID = /^[A-Za-z0-9_-]{11}$/;
// the page's only outside addresses, allowed by tests/test_web.py (FR-072)
const EMBED = "https://www.youtube-nocookie.com/embed/";
const WATCH = "https://www.youtube.com/watch";

let bar = null;
let loadedFile = null;   // the file whose media the audio element holds
let stopAt = null;       // pause the audio at this time; null plays on
let token = 0;           // a newer play() makes older, slower ones give up

const enc = encodeURIComponent;
const audio = () => /** @type {HTMLAudioElement} */ (q(bar, "#player-audio"));

function buildBar() {
  bar = document.createElement("div");
  bar.id = "player";
  bar.hidden = true;
  bar.innerHTML =
    '<div class="player-row"><span id="player-what"></span>' +
    '<button id="player-toggle" type="button">Pause</button>' +
    '<button id="player-stop" type="button">Stop</button></div>' +
    '<audio id="player-audio"></audio><div id="player-yt"></div>';
  document.body.appendChild(bar);
  const el = audio();
  el.addEventListener("timeupdate", () => {
    if (stopAt !== null && el.currentTime >= stopAt) { stopAt = null; el.pause(); }
  });
  for (const name of ["play", "pause", "ended"]) el.addEventListener(name, syncToggle);
  el.addEventListener("error", () => {
    if (el.getAttribute("src")) { loadedFile = null; say(`Couldn't play the media of ${el.dataset.name}.`); }
  });
  q(bar, "#player-toggle").addEventListener("click", () => {
    if (!el.paused) { el.pause(); return; }
    if (stopAt !== null && el.currentTime >= stopAt) stopAt = null;   // resumed after the end: play on
    el.play().catch(() => {});
  });
  q(bar, "#player-stop").addEventListener("click", stop);
}

function say(text) {
  q(bar, "#player-what").innerHTML = escapeHtml(text);
  bar.hidden = false;
  document.body.classList.add("player-on");
  document.body.style.setProperty("--player-h", `${bar.offsetHeight}px`);
}

function syncToggle() {
  q(bar, "#player-toggle").textContent = audio().paused ? "Play" : "Pause";
}

function clearYoutube() {
  q(bar, "#player-yt").innerHTML = "";
}

function stop() {
  token++;
  const el = audio();
  el.pause();
  stopAt = null;
  clearYoutube();
  bar.hidden = true;
  document.body.classList.remove("player-on");
}

const span = (name, start, end) =>
  `${name} · ${mmss(start)}${Number.isFinite(end) ? `–${mmss(end)}` : ""}`;

function playLocal(fileId, name, start, end, mine) {
  const el = audio();
  const src = `/api/${enc(CORPUS)}/media/${enc(fileId)}/stream`;
  if (loadedFile !== fileId || el.getAttribute("src") !== src) {
    el.src = src;
    loadedFile = fileId;
  }
  el.dataset.name = name;
  const go = () => {
    if (mine !== token) return;
    try { el.currentTime = start; } catch (e) { /* not seekable */ }
    stopAt = Number.isFinite(end) && end > start ? end : null;
    el.play().catch(() => {});
  };
  if (el.readyState >= 1) go(); else el.addEventListener("loadedmetadata", go, { once: true });
  syncToggle();
}

function playYoutube(id, start, end) {
  const from = Math.floor(start);
  const until = Number.isFinite(end) && end > start ? `&end=${Math.ceil(end)}` : "";
  q(bar, "#player-yt").innerHTML =
    `<iframe width="320" height="180" src="${EMBED}${id}?start=${from}${until}&autoplay=1&rel=0" ` +
    'allow="autoplay; encrypted-media" referrerpolicy="strict-origin-when-cross-origin" title="YouTube player"></iframe>' +
    `<a id="player-yt-link" href="${WATCH}?v=${id}&t=${from}s" target="_blank" rel="noopener noreferrer">` +
    `Open on YouTube at ${mmss(start)}</a>`;
}

/** Play a stretch of a file's media, from `start` to `end` seconds. */
export async function play(fileId, name, start, end) {
  if (!bar) buildBar();
  const mine = ++token;
  let info = null;
  try {
    const r = await fetch(`/api/media/${enc(fileId)}`);
    info = r.ok ? await r.json() : null;
  } catch (e) { /* said below */ }
  if (mine !== token) return;
  const el = audio();
  if (!info) { el.pause(); clearYoutube(); say(`Couldn't play the media of ${name}.`); return; }
  if (info.kind === "local") {
    clearYoutube();
    say(span(name, start, end));
    playLocal(fileId, name, start, end, mine);
  } else if (info.kind === "youtube" && YOUTUBE_ID.test(String(info.youtube_id))) {
    el.pause();
    stopAt = null;
    say(span(name, start, end));
    playYoutube(info.youtube_id, start, end);
    syncToggle();
  } else {
    el.pause();
    stopAt = null;
    clearYoutube();
    say(`No media for ${name}: ${info.reason || "the file names none"}.`);
  }
  q(bar, "#player-toggle").hidden = info.kind !== "local";
}

/** Ask the server to open a file in TiLiA, and say what came of it. */
export async function openInTilia(fileId, name) {
  let r;
  try {
    r = await fetch(`/api/files/${enc(fileId)}/open`, { method: "POST", body: "{}" });
  } catch (e) {
    setStatus(errMsg(0, { error: `could not reach the server (${e})` }), "error");
    return;
  }
  const data = await r.json().catch(() => null);
  if (r.status === 202) setStatus(`Opening ${name} in TiLiA…`);
  else if (r.status === 503) setStatus("TiLiA wasn't found. Install TiLiA, or open the file from TiLiA.", "error");
  else setStatus(errMsg(r.status, data), "error");
}

/** A double-click on a button or box does nothing extra. */
export const onControl = target => !!closest(target, "input, button, a, select, textarea");
