// Apply the stored (or system) theme before first paint to avoid flicker.
// Kept OUT of index.html as an external file so the hosted Content Security
// Policy can stay `script-src 'self'` without hashes or 'unsafe-inline'
// (migration stage 8, §48). Runs synchronously from <head>, before the
// body is painted.
(function () {
  try {
    var s = JSON.parse(localStorage.getItem("gc-settings") || "{}");
    var mode = s.theme || "system";
    var dark =
      mode === "dark" ||
      (mode === "system" &&
        window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  } catch (e) {
    document.documentElement.dataset.theme = "light";
  }
})();