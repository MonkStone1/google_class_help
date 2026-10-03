import { afterEach, describe, expect, it } from "vitest";

import {
  clearPresets,
  getPreset,
  isPresetId,
  listPresets,
  registerPreset,
} from "./registry.ts";
import { makeSource, testPreset } from "./testFixture.ts";

describe("preset registry", () => {
  afterEach(() => {
    clearPresets();
  });

  it("returns the preset that was registered under its id", () => {
    registerPreset(testPreset);

    expect(getPreset(testPreset.id)).toBe(testPreset);
  });

  it("lists what was registered, and nothing else", () => {
    registerPreset(testPreset);

    expect(listPresets().map((preset) => preset.id)).toEqual([
      testPreset.id,
    ]);
  });

  it("throws on an unknown id instead of falling back to some other format", () => {
    registerPreset(testPreset);

    // The failure this prevents is the worst one available: exporting one
    // format under the name of another, which only shows up at the importer.
    expect(() => getPreset("нет-такого")).toThrow(/нет-такого/);
  });

  it("reports an unknown id as unknown rather than throwing", () => {
    registerPreset(testPreset);

    expect(isPresetId(testPreset.id)).toBe(true);
    expect(isPresetId("нет-такого")).toBe(false);
    expect(listPresets()).not.toContain("нет-такого");
  });

  it("lets a preset be replaced without duplicating its entry", () => {
    registerPreset(testPreset);
    const renamed = { ...testPreset, worksheetName: "Renamed" };
    registerPreset(renamed);

    expect(listPresets()).toHaveLength(1);
    expect(getPreset(testPreset.id).worksheetName).toBe("Renamed");
  });

  it("keeps presets apart by id, so one cannot overwrite another", () => {
    registerPreset(testPreset);
    registerPreset({ ...testPreset, id: "other" });

    expect(getPreset(testPreset.id).worksheetName).toBe("Fixture");
    expect(getPreset("other").worksheetName).toBe("Fixture");
  });

  it("registers a preset declared at runtime, which is the extensibility claim", () => {
    // This is what "another preset without engine changes" means in practice:
    // no code in `engine/` names this preset at all.
    registerPreset({
      ...testPreset,
      id: "runtime_only",
      columns: [{ key: "seq", header: "№", kind: "number", width: 7 }],
    });

    expect(getPreset("runtime_only").columns.map((c) => c.header)).toEqual([
      "№",
    ]);
    expect(makeSource().title).toBe("Title");
  });
});