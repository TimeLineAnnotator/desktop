// Boot watchdog. A classic script, deliberately outside the module graph so
// that nothing it reports on can also break it.
//
// When one module fails to instantiate, the browser abandons the whole graph.
// The page still renders — the markup is static — but not a single listener is
// attached: buttons do nothing, chips never load, queries never run, and
// nothing on screen says why. That reads as the app being broken rather than as
// the page never having started, which is the worst way to lose an hour. The
// usual cause is a half-stale cache after the source changed under an open tab,
// which one hard reload fixes.
//
// The page's entry module sets `window.__bootOk` as its last statement; module
// scripts run before `load`, so an unset flag by then means the graph died.
(function () {
  var err = "";
  addEventListener("error", function (e) {
    if (!err) err = (e && e.message) || String((e && e.error) || "");
  }, true);
  addEventListener("load", function () {
    if (window.__bootOk) return;
    var b = document.createElement("div");
    b.style.cssText = "padding:10px 14px;background:#fff5f5;color:#8a1f1f;" +
      "border-bottom:2px solid #c62828;font:13px/1.45 ui-sans-serif,system-ui," +
      "sans-serif;position:sticky;top:0;z-index:9999";
    b.textContent = "This page never started — its scripts failed to load, so " +
      "nothing on it responds. Reload with ⌘⇧R (Ctrl+Shift+R): a stale " +
      "cache is the usual cause." + (err ? "  —  " + err : "");
    document.body.insertBefore(b, document.body.firstChild);
  });
})();
