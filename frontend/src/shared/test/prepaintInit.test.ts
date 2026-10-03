import { afterEach, beforeEach, describe, expect, it } from "vitest";

// The pre-paint script is a plain browser IIFE loaded from <head>, so it is
// tested the way it runs: read the shipped file as text and execute it against
// the jsdom document. Importing it as a module instead would let the bundler
// mask a syntax error that only shows up in the browser (ADR-0034, ADR-0005:
// zero-FOUC).
//
// `?raw` (Vite, already typed via `vite-env.d.ts`) keeps this free of Node's
// `fs`, which would mean adding `@types/node` to a project that has no use for
// it.
import source from "../../../public/prepaint-init.js?raw";

/** Runs the file exactly as <script src="/prepaint-init.js"> would. */
function runPrePaint(): void {
  new Function(source)();
}

const originalLanguage = Object.getOwnPropertyDescriptor(
  globalThis.navigator,
  "language",
);
const originalLanguages = Object.getOwnPropertyDescriptor(
  globalThis.navigator,
  "languages",
);

function withLanguages(...tags: string[]): void {
  Object.defineProperty(globalThis.navigator, "language", {
    value: tags[0],
    configurable: true,
  });
  Object.defineProperty(globalThis.navigator, "languages", {
    value: tags,
    configurable: true,
  });
}

function store(value: unknown): void {
  localStorage.setItem("gc-settings", JSON.stringify(value));
}

describe("prepaint-init", () => {
  beforeEach(() => {
    // The static attribute index.html ships; the script must overwrite it.
    document.documentElement.lang = "en";
    delete document.documentElement.dataset.theme;
  });

  afterEach(() => {
    if (originalLanguage) {
      Object.defineProperty(globalThis.navigator, "language", originalLanguage);
    }
    if (originalLanguages) {
      Object.defineProperty(globalThis.navigator, "languages", originalLanguages);
    }
  });

  it("declares the stored language before the first paint", () => {
    store({ language: "uk" });

    runPrePaint();

    expect(document.documentElement.lang).toBe("uk");
  });

  it("falls back to the browser preference on a first visit", () => {
    withLanguages("ru-RU");

    runPrePaint();

    expect(document.documentElement.lang).toBe("ru");
  });

  it("walks the whole preference list, like detectLanguage()", () => {
    // A German UI with Ukrainian second is a better guess than English.
    withLanguages("de-DE", "uk-UA", "en-US");

    runPrePaint();

    expect(document.documentElement.lang).toBe("uk");
  });

  it("ignores a stored language the app has no dictionary for", () => {
    store({ language: "de" });
    withLanguages("en-GB");

    runPrePaint();

    expect(document.documentElement.lang).toBe("en");
  });

  it("still applies the theme, and survives corrupt settings", () => {
    store({ theme: "dark", language: "ru" });
    runPrePaint();
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.lang).toBe("ru");

    // Unparseable JSON must not leave the page unstyled or undeclared.
    localStorage.setItem("gc-settings", "{not json");
    withLanguages("uk-UA");
    runPrePaint();
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement.lang).toBe("uk");
  });
});