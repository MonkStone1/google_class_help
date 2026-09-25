import "@testing-library/jest-dom/vitest";
import { beforeEach } from "vitest";

// jsdom does not implement `matchMedia`, which SettingsProvider uses to follow
// the OS theme. It is stubbed once here so tests can mount real providers
// instead of mocking the settings context.
if (!window.matchMedia) {
 window.matchMedia = ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener: () => undefined,
  removeEventListener: () => undefined,
  addListener: () => undefined,
  removeListener: () => undefined,
  dispatchEvent: () => false,
 })) as unknown as typeof window.matchMedia;
}

// Settings are persisted in localStorage (ADR-0006); a leaked value would make
// the next test depend on the previous one.
beforeEach(() => {
 localStorage.clear();
});
