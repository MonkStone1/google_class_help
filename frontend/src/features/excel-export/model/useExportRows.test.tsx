import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ReactNode } from "react";

import { SettingsProvider } from "../../../shared/settings/index.ts";
import { formatDayInput } from "../engine/rows.ts";
import type { ExportSource } from "../engine/types.ts";
import { readDateMemory, writeDateMemory } from "./dateMemory.ts";
import { useExportRows } from "./useExportRows.ts";

const saveBuffer = vi.hoisted(() => vi.fn());
const buildWorkbookBuffer = vi.hoisted(() =>
  vi.fn(async () => new ArrayBuffer(8)),
);
vi.mock("../engine/download.ts", () => ({ saveBuffer, XLSX_MIME: "text/x" }));
vi.mock("../engine/workbook.ts", () => ({
  buildWorkbookBuffer,
  fillWorksheet: vi.fn(),
}));

function makeSource(overrides: Partial<ExportSource> = {}): ExportSource {
  return {
    id: "w1",
    title: "Урок 15. 20.09.2026 Алгоритми",
    description: null,
    created_at: "2026-09-20T10:00:00",
    course_name: "Математика",
    ...overrides,
  };
}

/** The real provider, so `t()` resolves the way it does in the app. */
function wrapper({ children }: { children: ReactNode }) {
  localStorage.setItem(
    "gc-settings",
    JSON.stringify({ language: "en", theme: "light" }),
  );
  return <SettingsProvider>{children}</SettingsProvider>;
}

function renderHookOver(assignments: ExportSource[], courseId = "c1") {
  return renderHook(() => useExportRows(assignments, "Математика", courseId), {
    wrapper,
  });
}

describe("useExportRows", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    buildWorkbookBuffer.mockImplementation(async () => new ArrayBuffer(8));
    // The date memory lives in localStorage, so one test's dates would otherwise
    // be the next test's starting point.
    localStorage.removeItem("gc-export-dates");
  });

  it("starts on the registered preset with its rows already built", () => {
    const { result } = renderHookOver([makeSource()]);

    expect(result.current.presetId).toBe("ukranian_dictionary_nz");
    expect(result.current.preset?.worksheetName).toBe("Щоденник");
    expect(result.current.rows).toHaveLength(1);
    expect(result.current.canExport).toBe(true);
  });

  it("rebuilds the rows when the preset changes", () => {
    const { result } = renderHookOver([makeSource()]);

    act(() => result.current.setPresetId("нет-такого"));

    // An unknown id leaves the dialog with nothing to show rather than
    // silently exporting some other format under that name.
    expect(result.current.preset).toBeNull();
    expect(result.current.rows).toEqual([]);
    expect(result.current.canExport).toBe(false);
  });

  it("refuses to export under an unknown preset, with a readable message", async () => {
    const { result } = renderHookOver([makeSource()]);

    act(() => result.current.setPresetId("нет-такого"));
    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.run();
    });

    expect(ok).toBe(false);
    expect(result.current.error).toBe("This export format is not available.");
    expect(buildWorkbookBuffer).not.toHaveBeenCalled();
  });

  it("counts the rows that have no date to show", () => {
    const { result } = renderHookOver([
      makeSource({ id: "a" }),
      makeSource({ id: "b", created_at: null }),
    ]);

    expect(result.current.missingDates).toBe(1);
  });

  it("clears a previous failure once the teacher edits a date", async () => {
    const { result } = renderHookOver([makeSource()]);
    await act(async () => {
      await result.current.run();
    });
    expect(result.current.error).toBeNull();

    buildWorkbookBuffer.mockRejectedValueOnce(new Error("boom"));
    await act(async () => {
      await result.current.run();
    });
    expect(result.current.error).toBe("The Excel file could not be generated.");

    act(() => result.current.setDateOverride("w1", "2026-10-05"));

    expect(result.current.error).toBeNull();
  });
});

describe("the date memory", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    buildWorkbookBuffer.mockImplementation(async () => new ArrayBuffer(8));
    localStorage.removeItem("gc-export-dates");
  });

  it("starts from the assignment date when nothing was ever decided", () => {
    const { result } = renderHookOver([
      makeSource({ created_at: "2026-09-20T10:00:00" }),
    ]);

    expect(result.current.overrides).toEqual({});
    expect(formatDayInput(result.current.rows[0].values.date as Date)).toBe(
      "2026-09-20",
    );
  });

  it("reuses the dates the teacher fixed, the next time the dialog opens", () => {
    // The whole point: fix once, never again.
    const first = renderHookOver([makeSource()]);
    act(() => first.result.current.setDateOverride("w1", "2026-10-05"));
    first.unmount();

    const second = renderHookOver([makeSource()]);

    expect(second.result.current.overrides).toEqual({ w1: "2026-10-05" });
    expect(formatDayInput(second.result.current.rows[0].values.date as Date)).toBe(
      "2026-10-05",
    );
  });

  it("leaves rows it has no decision about on the assignment date", () => {
    writeDateMemory("c1", "ukranian_dictionary_nz", { w1: "2026-10-05" }, [
      "w1",
      "w2",
    ]);

    const { result } = renderHookOver([
      makeSource({ id: "w1" }),
      makeSource({ id: "w2", created_at: "2026-09-21T10:00:00" }),
    ]);

    expect(formatDayInput(result.current.rows[0].values.date as Date)).toBe(
      "2026-10-05",
    );
    expect(formatDayInput(result.current.rows[1].values.date as Date)).toBe(
      "2026-09-21",
    );
  });

  it("keeps one course's dates out of another course's export", () => {
    const maths = renderHookOver([makeSource()], "c1");
    act(() => maths.result.current.setDateOverride("w1", "2026-10-05"));
    maths.unmount();

    const physics = renderHookOver([makeSource()], "c2");

    expect(physics.result.current.overrides).toEqual({});
  });

  it("forgets a row the teacher cleared, and the assignment date returns", () => {
    const { result } = renderHookOver([makeSource()]);
    act(() => result.current.setDateOverride("w1", "2026-10-05"));
    // Clearing the input means "use the date from the assignment".
    act(() => result.current.setDateOverride("w1", ""));

    expect(result.current.overrides).toEqual({ w1: "" });
    expect(formatDayInput(result.current.rows[0].values.date as Date)).toBe(
      "2026-09-20",
    );
    expect(readDateMemory("c1", "ukranian_dictionary_nz")).toEqual({});
  });

  it("overwrites its single slot on every change instead of accumulating", () => {
    const { result } = renderHookOver([makeSource()]);
    act(() => result.current.setDateOverride("w1", "2026-10-05"));
    act(() => result.current.setDateOverride("w1", "2026-10-06"));

    expect(readDateMemory("c1", "ukranian_dictionary_nz")).toEqual({
      w1: "2026-10-06",
    });
  });

  it("writes nothing until the teacher actually edits something", () => {
    renderHookOver([makeSource()]);

    // Merely opening the dialog must not overwrite a memory it only read.
    expect(localStorage.getItem("gc-export-dates")).toBeNull();
  });
});