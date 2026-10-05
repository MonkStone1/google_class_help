import { beforeEach, describe, expect, it, vi } from "vitest";

import { readDateMemory, writeDateMemory } from "./dateMemory.ts";

const STORAGE_KEY = "gc-export-dates";

function stored(): unknown {
  const raw = localStorage.getItem(STORAGE_KEY);
  return raw === null ? null : JSON.parse(raw);
}

describe("the date memory", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("is empty for a course nobody has edited yet", () => {
    expect(readDateMemory("c1", "ukranian_dictionary_nz")).toEqual({});
  });

  it("gives back what was written, per assignment", () => {
    writeDateMemory(
      "c1",
      "ukranian_dictionary_nz",
      { w1: "2026-10-05", w2: "2026-10-07" },
      ["w1", "w2"],
    );

    expect(readDateMemory("c1", "ukranian_dictionary_nz")).toEqual({
      w1: "2026-10-05",
      w2: "2026-10-07",
    });
  });

  it("keeps ONE slot per course and preset, and never mixes them", () => {
    writeDateMemory("c1", "ukranian_dictionary_nz", { w1: "2026-10-05" }, ["w1"]);
    writeDateMemory("c2", "ukranian_dictionary_nz", { w1: "2026-11-01" }, ["w1"]);
    writeDateMemory("c1", "russian_variant", { w1: "2026-12-01" }, ["w1"]);

    expect(readDateMemory("c1", "ukranian_dictionary_nz")).toEqual({
      w1: "2026-10-05",
    });
    expect(readDateMemory("c2", "ukranian_dictionary_nz")).toEqual({
      w1: "2026-11-01",
    });
    expect(readDateMemory("c1", "russian_variant")).toEqual({ w1: "2026-12-01" });
  });

  it("OVERWRITES the slot on every write, so there is no history", () => {
    // The requirement: one memory cell, replaced rather than appended. A second
    // change must leave no trace of the first.
    writeDateMemory("c1", "p", { w1: "2026-10-05" }, ["w1"]);
    writeDateMemory("c1", "p", { w1: "2026-10-06" }, ["w1"]);

    expect(readDateMemory("c1", "p")).toEqual({ w1: "2026-10-06" });
    expect(JSON.stringify(stored())).not.toContain("2026-10-05");
  });

  it("forgets a row the teacher cleared, so the assignment date comes back", () => {
    // Clearing the input in the preview is how a teacher says "use the date from
    // the assignment again" — an empty value is therefore not remembered.
    writeDateMemory("c1", "p", { w1: "2026-10-05", w2: "2026-10-07" }, [
      "w1",
      "w2",
    ]);
    writeDateMemory("c1", "p", { w1: "2026-10-05", w2: "" }, ["w1", "w2"]);

    expect(readDateMemory("c1", "p")).toEqual({ w1: "2026-10-05" });
  });

  it("drops rows for coursework the course no longer has", () => {
    // Pruning on write is what keeps one slot from growing forever.
    writeDateMemory("c1", "p", { w1: "2026-10-05", gone: "2026-10-06" }, [
      "w1",
      "gone",
    ]);
    writeDateMemory("c1", "p", { w1: "2026-10-05", gone: "2026-10-06" }, ["w1"]);

    expect(readDateMemory("c1", "p")).toEqual({ w1: "2026-10-05" });
  });

  it("refuses to remember a value that is not a real day", () => {
    writeDateMemory(
      "c1",
      "p",
      {
        good: "2026-10-05",
        notADate: "05.10.2026",
        impossible: "2026-02-31",
        empty: "",
        wrongType: 42 as unknown as string,
      },
      ["good", "notADate", "impossible", "empty", "wrongType"],
    );

    expect(readDateMemory("c1", "p")).toEqual({ good: "2026-10-05" });
  });
});

describe("the date memory survives a corrupted store", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("ignores storage that is not JSON at all", () => {
    localStorage.setItem(STORAGE_KEY, "{не json");

    expect(readDateMemory("c1", "p")).toEqual({});
  });

  it("ignores JSON of the wrong shape", () => {
    // Hand-edited in devtools, or written by a build that changed its format.
    localStorage.setItem(STORAGE_KEY, JSON.stringify(["w1", "w2"]));
    expect(readDateMemory("c1", "p")).toEqual({});

    localStorage.setItem(STORAGE_KEY, JSON.stringify({ "c1:p": "2026-10-05" }));
    expect(readDateMemory("c1", "p")).toEqual({});
  });

  it("keeps the good slots when only one of them is damaged", () => {
    writeDateMemory("c1", "p", { w1: "2026-10-05" }, ["w1"]);
    const store = stored() as Record<string, unknown>;
    store["c2:p"] = { w1: 12345 };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));

    expect(readDateMemory("c1", "p")).toEqual({ w1: "2026-10-05" });
    expect(readDateMemory("c2", "p")).toEqual({});
  });

  it("still exports when storage refuses to be written", () => {
    // Private mode and a full quota both throw. The teacher must still get the
    // file; only the memory is lost.
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });

    expect(() =>
      writeDateMemory("c1", "p", { w1: "2026-10-05" }, ["w1"]),
    ).not.toThrow();

    setItem.mockRestore();
  });
});
