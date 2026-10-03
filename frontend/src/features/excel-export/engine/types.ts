import type { Assignment } from "../../../shared/types/index.ts";

/**
 * The contract between the export ENGINE and a PRESET (ADR-0041).
 *
 * Nothing in `engine/` knows which format it is writing: it reads `columns`,
 * walks them in order and asks each column for its value. A second preset
 * therefore needs no engine change at all — that is the whole claim, and
 * `engine/rows.test.ts` plus `engine/workbook.test.ts` check it by building
 * rows and a workbook from a preset declared inside the test.
 */

/** What a column holds; the engine dispatches on it to fill a cell. */
export type ExportColumnKind = "number" | "date" | "text";

export type ExportColumn = {
  /** Stable key of the value inside an `ExportRow`, e.g. "content". */
  key: string;
  /**
   * The header as written INTO THE FILE.
   *
   * Deliberately NOT localized: this is the format an external importer reads,
   * not something the teacher reads. What the UI shows is `preset.labelKey`
   * plus these same strings in the preview (ADR-0041).
   */
  header: string;
  kind: ExportColumnKind;
  /** Column width in Excel characters. */
  width: number;
  /** Wrap long text instead of letting it run into the next column. */
  wrap?: boolean;
  /**
   * How a `text` column reads its source row.
   *
   * This is what keeps the engine free of format knowledge: the preset says
   * "this column is the cleaned title" or "this one is the homework with URLs
   * replaced", and the engine never learns which is which. `number` and `date`
   * columns are filled by the engine and must NOT declare this.
   */
  text?: (source: ExportSource) => string;
};

/** A fill + font for the header row, in ExcelJS' own vocabulary. */
export type ExportHeaderFill = {
  fg: { argb: string };
  font?: { bold: boolean };
};

/** One exportable course assignment, reduced to the fields the engine reads. */
export type ExportSource = Pick<
  Assignment,
  "id" | "title" | "description" | "created_at" | "course_name"
>;

/** A cell the engine may write: a number, a real `Date`, text, or nothing. */
export type ExportCellValue = number | Date | string | null;

export type ExportRow = {
  /** The coursework id, so the UI can key date overrides by assignment. */
  assignmentId: string;
  values: Record<string, ExportCellValue>;
};

/** `YYYY-MM-DD` overrides the teacher typed into the preview, by assignment id. */
export type DateOverrides = Record<string, string>;

export type ExportPreset = {
  /** The registry key, and the value the preset selector carries. */
  id: string;
  /** Localized name for the preset selector — unlike `columns[].header`. */
  labelKey: string;
  worksheetName: string;
  /** ORDER MATTERS: the array order is the column order in the file. */
  columns: ExportColumn[];
  /** Excel number formats by kind; the date one is "dd.mm.yyyy". */
  numberFormat: Record<ExportColumnKind, string>;
  headerFill?: ExportHeaderFill;
  /**
   * How the rows are ordered. `createdAt` is the assignment creation stamp,
   * `id` the deterministic tiebreak for identical stamps.
   */
  sort: { primary: "createdAt"; tiebreak: "id" };
  /** Appended to the sanitized course name, e.g. "_електронний_щоденник". */
  filenameSuffix: string;
  /**
   * The default date cell, built as LOCAL midnight.
   *
   * ExcelJS converts a `Date` to an Excel serial by UTC
   * (`25569 + ms / 86_400_000`), so a naive `new Date("2026-09-20")` would
   * render as `19.09.2026` east of UTC (ADR-0041).
   */
  defaultDate: (createdAt: string | null | undefined) => Date | null;
};

/** Registry key type; an id is whatever a preset declares, checked at use. */
export type PresetId = string;