import type { Cell, Worksheet } from "exceljs";

import type { ExportPreset, ExportRow } from "./types.ts";

/**
 * The ExcelJS workbook (ADR-0041).
 *
 * The generator knows no column: it asks the preset for the sheet name, the
 * columns, their widths and their fills, and writes `rows` in the order it was
 * given.
 *
 * The `import type` above is erased at compile time — it costs nothing in the
 * bundle. The LIBRARY itself is imported dynamically inside `exceljs()`, which
 * is what keeps ~900 KB gzip out of the initial chunk: the course page loads the
 * button, not the library, and the writer is fetched on the first export.
 */

/** The library as this module uses it; the dynamic import resolves to it. */
type ExcelModule = typeof import("exceljs");

let cached: Promise<ExcelModule> | null = null;

/** `exceljs` once per page, however many times the teacher exports. */
function exceljs(): Promise<ExcelModule> {
  cached ??= import("exceljs");
  return cached;
}

/**
 * Header styling, applied ONLY when the preset asks for it.
 *
 * A preset that declares no `headerFill` gets no bold, no shading and no
 * alignment of our own: its header is written like any other cell, in the
 * workbook's default type, so the whole file comes out one size and weight
 * (ADR-0041). Styling the header unconditionally would make that impossible to
 * ask for, and the importer's expected file is plain.
 */
function styleHeader(cell: Cell, preset: ExportPreset): void {
  if (!preset.headerFill) return;
  cell.font = { ...(preset.headerFill.font ?? {}) };
  cell.fill = {
    type: "pattern",
    pattern: "solid",
    fgColor: preset.headerFill.fg,
  };
  cell.alignment = { vertical: "middle" };
}

/**
 * Writes `rows` into a worksheet shaped by `preset`.
 *
 * Split out from `buildWorkbookBuffer` so the styling rules can be asserted on
 * a worksheet without paying for the ZIP round-trip in every assertion.
 */
export function fillWorksheet(
  sheet: Worksheet,
  preset: ExportPreset,
  rows: readonly ExportRow[],
): void {
  preset.columns.forEach((column, index) => {
    // Width and number format come from the preset; the engine never guesses.
    sheet.getColumn(index + 1).width = column.width;
    sheet.getColumn(index + 1).numFmt = preset.numberFormat[column.kind];
  });

  const header = sheet.getRow(1);
  preset.columns.forEach((column, index) => {
    const cell = header.getCell(index + 1);
    cell.value = column.header;
    styleHeader(cell, preset);
  });
  header.commit();

  rows.forEach((row, rowIndex) => {
    // Row 1 is the header, so the first data row is 2 — the one-based Excel
    // numbering, which is why the row array index is offset by one.
    const line = sheet.getRow(rowIndex + 2);
    preset.columns.forEach((column, columnIndex) => {
      const cell = line.getCell(columnIndex + 1);
      const value = row.values[column.key];
      // A real `Date` for a date column and a NUMBER for a number column: the
      // importer reads both back as values, and neither survives as text.
      cell.value = value ?? null;
      if (column.wrap) {
        cell.alignment = { wrapText: true, vertical: "top" };
      }
    });
    line.commit();
  });
}

/** Builds the `.xlsx` bytes for `preset` + `rows`. */
export async function buildWorkbookBuffer(
  preset: ExportPreset,
  rows: readonly ExportRow[],
): Promise<ArrayBuffer> {
  const ExcelJS = await exceljs();
  const workbook = new ExcelJS.Workbook();
  fillWorksheet(workbook.addWorksheet(preset.worksheetName), preset, rows);
  // ExcelJS declares `writeBuffer()` as returning a Node `Buffer`, which in
  // the browser build IS an `ArrayBuffer`; `saveBuffer` wants the same bytes.
  return (await workbook.xlsx.writeBuffer()) as unknown as ArrayBuffer;
}