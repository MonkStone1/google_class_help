import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ReactNode } from "react";

import { SettingsProvider } from "../../../shared/settings/index.ts";
import type { ExportSource } from "../engine/types.ts";
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

function renderHookOver(assignments: ExportSource[]) {
  return renderHook(() => useExportRows(assignments, "Математика"), {
    wrapper,
  });
}

describe("useExportRows", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    buildWorkbookBuffer.mockImplementation(async () => new ArrayBuffer(8));
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