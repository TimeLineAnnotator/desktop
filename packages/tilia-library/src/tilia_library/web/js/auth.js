// The run's token, which the page sends as a header.
//
// It reaches the page once, in the fragment of the address the command opens,
// which browsers send to no server. The page keeps it in sessionStorage: per tab,
// so it survives a reload, and per origin, so unlike a cookie it stays out of
// reach of other servers on 127.0.0.1.
const KEY = "tilia-library.token";

let token = null;  // kept here too: sessionStorage may be refused

/** Take the token out of the address, if it is there. */
function takeFromAddress() {
  const found = /^#token=(.+)$/.exec(location.hash);
  if (!found) return false;
  history.replaceState(history.state, "", location.pathname + location.search);
  token = found[1];
  try { sessionStorage.setItem(KEY, token); } catch (e) { /* lasts until a reload */ }
  return true;
}

if (!takeFromAddress()) {
  try { token = sessionStorage.getItem(KEY); } catch (e) { /* no token, then */ }
}

// The entry address opened in a tab already on this page doesn't load the page.
addEventListener("hashchange", () => { if (takeFromAddress()) location.reload(); });

export const hasToken = () => token !== null;

export function sendToken(headers) {
  if (token !== null) headers.set("Authorization", `Bearer ${token}`);
}

/** The server refused the token: it belongs to an earlier run. */
export function forgetToken() {
  token = null;
  try { sessionStorage.removeItem(KEY); } catch (e) { /* gone at the tab's end */ }
}

/** Say how to open the library, in place of the page. */
export function showLocked() {
  const locked = document.getElementById("locked");
  locked.hidden = false;
  document.body.replaceChildren(locked);
}
