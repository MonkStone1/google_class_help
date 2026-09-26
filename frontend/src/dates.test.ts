import { afterEach, describe, expect, it } from "vitest";

import {
  createdTime,
  detectLanguage,
  formatTime,
  parseDue,
  relativeDayLabel,
  toLocalDate,
} from "./dates.ts";

/**
 * jsdom's `navigator.language` is read-only, so the preference list is
 * redefined per test. Only these two properties are touched; everything else
 * on the real navigator (matchMedia, languages) is left alone by restoring
 * the original descriptors in afterEach.
 */
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

afterEach(() => {
  if (originalLanguage) {
    Object.defineProperty(globalThis.navigator, "language", originalLanguage);
  }
  if (originalLanguages) {
    Object.defineProperty(globalThis.navigator, "languages", originalLanguages);
  }
});

describe("detectLanguage", () => {
  it("maps a regional tag to its dictionary", () => {
    withLanguages("uk-UA");
    expect(detectLanguage()).toBe("uk");

    withLanguages("ru-RU");
    expect(detectLanguage()).toBe("ru");

    withLanguages("en-GB");
    expect(detectLanguage()).toBe("en");
  });

  it("walks the whole preference list instead of only the first tag", () => {
    // A German UI with Ukrainian second is a better guess than English.
    withLanguages("de-DE", "uk-UA", "en-US");
    expect(detectLanguage()).toBe("uk");

    withLanguages("fr-FR", "pl-PL", "ru-RU");
    expect(detectLanguage()).toBe("ru");
  });

  it("falls back to English when nothing in the list is supported", () => {
    withLanguages("de-DE", "fr-FR", "pl-PL");
    expect(detectLanguage()).toBe("en");
  });

  it("falls back to English when the list is empty", () => {
    Object.defineProperty(globalThis.navigator, "languages", {
      value: [],
      configurable: true,
    });
    expect(detectLanguage()).toBe("en");
  });
});

describe("parseDue", () => {
  it("parses naive FastAPI datetimes as local time", () => {
    const parsed = parseDue("2026-03-04T09:05:00");
    expect(parsed).not.toBeNull();
    expect(parsed?.getFullYear()).toBe(2026);
    expect(parsed?.getMonth()).toBe(2);
    expect(parsed?.getDate()).toBe(4);
    expect(parsed?.getHours()).toBe(9);
  });

  it("returns null for missing or unparseable values", () => {
    expect(parseDue(null)).toBeNull();
    expect(parseDue("tomorrow")).toBeNull();
  });
});

describe("createdTime", () => {
  it("returns 0 for missing or invalid values, never NaN", () => {
    expect(createdTime(null)).toBe(0);
    expect(createdTime(undefined)).toBe(0);
    expect(createdTime("not-a-date")).toBe(0);
  });

  it("returns epoch ms for valid timestamps", () => {
    expect(createdTime("1970-01-01T00:00:01Z")).toBe(1000);
  });
});

describe("toLocalDate", () => {
  it("reads naive backend timestamps as UTC, not local time", () => {
    const parsed = toLocalDate("2026-09-19T00:00:00");
    expect(parsed).not.toBeNull();
    expect(parsed?.toISOString()).toBe("2026-09-19T00:00:00.000Z");
  });

  it("keeps values that already carry an offset", () => {
    expect(toLocalDate("2026-09-19T00:00:00Z")?.toISOString()).toBe(
      "2026-09-19T00:00:00.000Z",
    );
    expect(toLocalDate("2026-09-19T03:00:00+03:00")?.toISOString()).toBe(
      "2026-09-19T00:00:00.000Z",
    );
  });

  it("returns null for missing or invalid values", () => {
    expect(toLocalDate(null)).toBeNull();
    expect(toLocalDate("tomorrow")).toBeNull();
  });
});

describe("formatTime", () => {
  it("hides the backend's 23:59 date-only sentinel", () => {
    expect(formatTime(new Date(2026, 0, 1, 23, 59))).toBe("");
  });
});

describe("relativeDayLabel", () => {
  it("labels today, tomorrow and overdue days", () => {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 9);
    expect(relativeDayLabel(today)).toEqual({ key: "date.today", count: 0 });

    const tomorrow = new Date(today.getTime() + 24 * 60 * 60 * 1000);
    expect(relativeDayLabel(tomorrow)).toEqual({
      key: "date.tomorrow",
      count: 0,
    });

    const threeDaysAgo = new Date(today.getTime() - 3 * 24 * 60 * 60 * 1000);
    expect(relativeDayLabel(threeDaysAgo)).toEqual({
      key: "date.daysOverdue",
      count: 3,
    });
  });

  it("returns null without a date", () => {
    expect(relativeDayLabel(null)).toBeNull();
  });
});