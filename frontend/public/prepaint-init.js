// Apply the stored (or system) theme AND declare the stored interface
// language on <html> before the first paint, so neither the colours nor the
// document language flash in the wrong state.
//
// `<html lang>` matters beyond accessibility: the static value in index.html
// is `en`, and a page that renders Ukrainian while the document still claims
// English is a page Google Translate offers to "translate" into the reader's
// own language — on a page that is already in it (ADR-0034). The whole
// preference list is walked here, not just `navigator.language`, exactly like
// `detectLanguage()` in src/dates.ts.
//
// Kept OUT of index.html as an external file so the hosted Content Security
// Policy can stay `script-src 'self'` without hashes or 'unsafe-inline'
// (migration stage 8, §48). Runs synchronously from <head>, before the
// body is painted. SettingsContext re-applies both values on every change
// (ADR-0006, ADR-0034).
(function () {
  var SUPPORTED = { en: 1, uk: 1, ru: 1 };

  function detectLanguage() {
    var preferred =
      navigator.languages && navigator.languages.length > 0
        ? navigator.languages
        : [navigator.language];
    for (var i = 0; i < preferred.length; i++) {
      var tag = String(preferred[i] || "").toLowerCase();
      if (tag.indexOf("uk") === 0) {
        return "uk";
      }
      if (tag.indexOf("ru") === 0) {
        return "ru";
      }
      if (tag.indexOf("en") === 0) {
        return "en";
      }
    }
    return "en";
  }

  try {
    var stored = JSON.parse(localStorage.getItem("gc-settings") || "{}") || {};
    var mode = stored.theme || "system";
    // A saved value we do not ship a dictionary for is ignored, the same way
    // `normalizeLanguage()` in SettingsContext ignores it.
    var language = SUPPORTED[stored.language]
      ? stored.language
      : detectLanguage();
    var dark =
      mode === "dark" ||
      (mode === "system" &&
        window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    document.documentElement.lang = language;
  } catch (e) {
    document.documentElement.dataset.theme = "light";
    document.documentElement.lang = detectLanguage();
  }
})();