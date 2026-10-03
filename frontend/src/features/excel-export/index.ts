/**
 * The public API of `features/excel-export` — a teacher-side action that
 * turns the coursework a page already holds into a `.xlsx` (ADR-0041).
 *
 * The split below is the whole design, and it is enforced rather than
 * documented:
 *
 * - `engine/` turns ROWS into a workbook and knows no export format. It must
 *   not learn one: `engine/rows.test.ts` fails if a format string or a preset
 *   import appears there.
 * - `presets/` owns everything format-specific. A second preset is a new file
 *   plus one `registerPreset` call — the engine, the tests and the page do not
 *   change.
 * - `model/` is the React state, `ui/` is the markup, and this barrel is the
 *   only way out of the slice (guardrail #10).
 *
 * `exceljs` is NOT re-exported and NOT imported anywhere above this line: it is
 * loaded dynamically inside `engine/workbook.ts` on the first export, so the
 * course page ships the button and not the library.
 */

export { ExcelExportButton } from "./ui/ExcelExportButton.tsx";
export { ExcelExportDialog } from "./ui/ExcelExportDialog.tsx";
export { ExportPreviewTable } from "./ui/ExportPreviewTable.tsx";
export { DEFAULT_PRESET_ID, useExportRows } from "./model/useExportRows.ts";
export type { ExportRowsState } from "./model/useExportRows.ts";
export { buildFilename, sanitizeFilename } from "./engine/filename.ts";
export { buildRows } from "./engine/rows.ts";
export { buildWorkbookBuffer } from "./engine/workbook.ts";
export { saveBuffer } from "./engine/download.ts";
export {
  getPreset,
  isPresetId,
  listPresets,
  registerPreset,
} from "./engine/registry.ts";
export { ukranianDictionaryNzPreset } from "./presets/ukranianDictionaryNz.ts";
export type {
  DateOverrides,
  ExportColumn,
  ExportColumnKind,
  ExportPreset,
  ExportRow,
  ExportSource,
  PresetId,
} from "./engine/types.ts";