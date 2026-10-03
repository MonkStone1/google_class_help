import type { ExportPreset, ExportSource } from "./types.ts";

/**
 * A preset that has nothing to do with the shipped one.
 *
 * The engine tests use this instead of the real `ukranian_dictionary_nz` on
 * purpose: if they passed against the shipped preset, "the engine is generic"
 * would be an untested claim that happens to hold today. A second, deliberately
 * different preset (other columns, other sheet, other widths) makes the claim
 * testable — build a workbook from this and the engine has proved it (ADR-0041).
 */
const upper = (title: string): string => title.toUpperCase();
const orEmpty = (description: string | null | undefined): string => description ?? "";

export const testPreset: ExportPreset = {
  id: "test_fixture",
  labelKey: "export.preset.test_fixture",
  worksheetName: "Fixture",
  columns: [
    { key: "seq", header: "SEQ", kind: "number", width: 5 },
    { key: "when", header: "WHEN", kind: "date", width: 11 },
    { key: "body", header: "BODY", kind: "text", width: 30, wrap: true, text: (s) => upper(s.title) },
    { key: "note", header: "NOTE", kind: "text", width: 20, text: (s) => orEmpty(s.description) },
  ],
  numberFormat: { number: "0", date: "dd.mm.yyyy", text: "General" },
  headerFill: { fg: { argb: "FFE0E0E0" }, font: { bold: true } },
  sort: { primary: "createdAt", tiebreak: "id" },
  filenameSuffix: "_fixture",
  defaultDate: (createdAt) => {
    if (!createdAt) return null;
    const date = new Date(createdAt);
    return Number.isNaN(date.getTime())
      ? null
      : new Date(date.getFullYear(), date.getMonth(), date.getDate());
  },
};

/** A minimal `ExportSource`, with only the fields the engine reads. */
export function makeSource(
  overrides: Partial<ExportSource> = {},
): ExportSource {
  return {
    id: "w1",
    title: "Title",
    description: null,
    created_at: "2026-09-20T10:00:00",
    course_name: "Math",
    ...overrides,
  };
}