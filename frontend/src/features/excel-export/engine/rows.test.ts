import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { buildRows, formatDayInput, parseDayInput } from "./rows.ts";
import { makeSource, testPreset } from "./testFixture.ts";

const ENGINE_DIR = import.meta.dirname;

/** Engine modules, tests and the test fixture excluded. */
function engineModules(): string[] {
  return readdirSync(ENGINE_DIR).filter(
    (name) =>
      name.endsWith(".ts") &&
      !name.endsWith(".test.ts") &&
      name !== "testFixture.ts",
  );
}

describe("buildRows: ordering and numbering", () => {
  it("sorts by the creation stamp, oldest first", () => {
    const rows = buildRows(testPreset, [
      makeSource({ id: "c", created_at: "2026-09-22T09:00:00" }),
      makeSource({ id: "a", created_at: "2026-09-20T09:00:00" }),
      makeSource({ id: "b", created_at: "2026-09-21T09:00:00" }),
    ]);

    expect(rows.map((row) => row.assignmentId)).toEqual(["a", "b", "c"]);
  });

  it("breaks identical stamps by id, so the same input always exports the same way", () => {
    const sameStamp = "2026-09-20T09:00:00";
    const input = [
      makeSource({ id: "z", created_at: sameStamp }),
      makeSource({ id: "a", created_at: sameStamp }),
      makeSource({ id: "m", created_at: sameStamp }),
    ];

    // Deterministic means: sorting a reversed copy gives the same answer.
    expect(buildRows(testPreset, input).map((r) => r.assignmentId)).toEqual([
      "a",
      "m",
      "z",
    ]);
    expect(
      buildRows(testPreset, [...input].reverse()).map((r) => r.assignmentId),
    ).toEqual(["a", "m", "z"]);
  });

  it("numbers rows 1..N with no gaps", () => {
    const rows = buildRows(
      testPreset,
      [1, 2, 3, 4, 5].map((n) =>
        makeSource({ id: `w${n}`, created_at: `2026-09-2${n}T09:00:00` }),
      ),
    );

    expect(rows.map((row) => row.values.seq)).toEqual([1, 2, 3, 4, 5]);
  });

  it("numbers in EXPORT order, which is the order the teacher sees", () => {
    const rows = buildRows(testPreset, [
      makeSource({ id: "late", created_at: "2026-09-25T09:00:00" }),
      makeSource({ id: "early", created_at: "2026-09-01T09:00:00" }),
    ]);

    // `late` arrived first and is numbered 2 — numbering follows the sort.
    expect(rows.map((row) => row.values.seq)).toEqual([1, 2]);
  });
});

describe("buildRows: dates", () => {
  it("defaults the date cell to the preset's date", () => {
    const [row] = buildRows(testPreset, [
      makeSource({ created_at: "2026-09-20T10:00:00" }),
    ]);

    const date = row.values.when as Date;
    expect(date).toBeInstanceOf(Date);
    expect(formatDayInput(date)).toBe("2026-09-20");
  });

  it("lets an override win over the default, and only in its own row", () => {
    const rows = buildRows(
      testPreset,
      [
        makeSource({ id: "a", created_at: "2026-09-20T10:00:00" }),
        makeSource({ id: "b", created_at: "2026-09-21T10:00:00" }),
      ],
      { b: "2026-10-01" },
    );

    expect(formatDayInput(rows[0].values.when as Date)).toBe("2026-09-20");
    expect(formatDayInput(rows[1].values.when as Date)).toBe("2026-10-01");
  });

  it("does not re-sort when a date is edited", () => {
    // The regression: an override that moves a row would renumber the diary.
    const input = [
      makeSource({ id: "a", created_at: "2026-09-20T10:00:00" }),
      makeSource({ id: "b", created_at: "2026-09-21T10:00:00" }),
    ];

    const rows = buildRows(testPreset, input, { a: "2026-12-31" });

    expect(rows.map((row) => row.assignmentId)).toEqual(["a", "b"]);
    expect(rows.map((row) => row.values.seq)).toEqual([1, 2]);
  });

  it("leaves the date empty when there is no stamp and no override", () => {
    const [row] = buildRows(testPreset, [makeSource({ created_at: null })]);

    // Not `Invalid Date`: an unusable cell the teacher can still fill in.
    expect(row.values.when).toBeNull();
  });

describe("buildRows: text columns", () => {
  it("asks the COLUMN for its value, so the engine needs no key names", () => {
    const [row] = buildRows(testPreset, [
      makeSource({ title: "Алгоритми", description: "Прочитати" }),
    ]);

    expect(row.values.body).toBe("АЛГОРИТМИ");
    expect(row.values.note).toBe("Прочитати");
  });

  it("writes an empty cell, never the string 'null', for a missing description", () => {
    const [row] = buildRows(testPreset, [makeSource({ description: null })]);

    expect(row.values.note).toBe("");
  });
});

describe("buildRows: the source is not mutated", () => {
  it("leaves the input array and its objects exactly as they were", () => {
    const input = [
      makeSource({ id: "b", title: "B", created_at: "2026-09-21T09:00:00" }),
      makeSource({ id: "a", title: "A", created_at: "2026-09-20T09:00:00" }),
    ];
    const snapshot = structuredClone(input);

    buildRows(testPreset, input, { a: "2026-10-01" });

    // `sort` is in-place, so a reordered array here would mean the page's own
    // coursework list was reordered by opening a dialog.
    expect(input).toEqual(snapshot);
    expect(input.map((a) => a.id)).toEqual(["b", "a"]);
  });
});

describe("day input parsing", () => {
  it("reads an <input type=date> value as LOCAL midnight", () => {
    // Local midnight, not `new Date("2026-09-20")` (UTC midnight): ExcelJS
    // converts a Date to a serial by UTC, so the naive form renders as
    // 19.09.2026 east of UTC (ADR-0041).
    const date = parseDayInput("2026-09-20") as Date;

    expect(date.getFullYear()).toBe(2026);
    expect(date.getMonth()).toBe(8);
    expect(date.getDate()).toBe(20);
    expect(date.getHours()).toBe(0);
  });

  it("rejects a day that does not exist rather than rolling it over", () => {
    expect(parseDayInput("2026-02-31")).toBeNull();
    expect(parseDayInput("2026-13-01")).toBeNull();
  });

  it("rejects anything that is not a plain YYYY-MM-DD", () => {
    expect(parseDayInput("")).toBeNull();
    expect(parseDayInput("20.09.2026")).toBeNull();
    expect(parseDayInput("2026-09-20T10:00")).toBeNull();
  });

  it("round-trips a date through the input format", () => {
    expect(formatDayInput(parseDayInput("2026-09-20"))).toBe("2026-09-20");
    expect(formatDayInput(null)).toBe("");
  });
});

describe("the engine does not know the shipped format", () => {
  it("keeps the Ukrainian column headers and the preset id out of engine/", () => {
    // A string naming the content header or the preset id inside the engine
    // would mean it had started to know WHICH format it was writing — the very
    // thing the preset split exists to prevent.
    const offenders: string[] = [];
    for (const name of engineModules()) {
      const text = readFileSync(join(ENGINE_DIR, name), "utf-8");
      for (const marker of ["Зміст", "Номер", "ukranian_dictionary_nz"]) {
        if (text.includes(marker)) offenders.push(`${name}: ${marker}`);
      }
    }

    expect(offenders).toEqual([]);
  });

  it("never imports the presets folder from engine/", () => {
    // The other half of the same rule: presets are registered by the FEATURE,
    // so an engine that imported one would be a preset-specific engine.
    const offenders: string[] = [];
    for (const name of engineModules()) {
      const text = readFileSync(join(ENGINE_DIR, name), "utf-8");
      for (const match of text.matchAll(/from\s+"([^"]+)"/g)) {
        if (match[1].includes("preset")) offenders.push(`${name}: ${match[1]}`);
      }
    }

    expect(offenders).toEqual([]);
  });
});
  it("falls back to the default when the teacher clears the override", () => {
    const [row] = buildRows(
      testPreset,
      [makeSource({ created_at: "2026-09-20T10:00:00" })],
      { w1: "" },
    );

    expect(formatDayInput(row.values.when as Date)).toBe("2026-09-20");
  });
});