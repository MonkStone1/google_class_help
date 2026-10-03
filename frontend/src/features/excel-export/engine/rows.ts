import { createdTime } from "../../../shared/lib/index.ts";
import type {
  DateOverrides,
  ExportCellValue,
  ExportPreset,
  ExportRow,
  ExportSource,
} from "./types.ts";

/**
 * Rows: sort, number, fill — and nothing else (ADR-0041).
 *
 * The engine deliberately knows no column headers and no format. It reads the
 * preset's `columns` in order, asks each column's kind for a value, and hands
 * the result to the workbook builder. That is what makes the second preset a
 * new file rather than a new branch in here.
 *
 * TWO RULES ARE ENFORCED, NOT ASSUMED:
 *
 * 1. **Nothing is mutated.** `assignments` is copied before it is sorted
 *    (`Array.prototype.sort` sorts in place), and every row is a fresh object.
 *    The teacher's page keeps handing these same coursework objects to the
 *    assignment cards; a reordered or rewritten array would change the screen
 *    under the dialog.
 * 2. **The order is decided by the ORIGINAL creation stamp.** A date edited in
 *    the preview lives in `overrides` and is applied when the cell is filled,
 *    after the sort — so re-dating a lesson never renumbers the diary.
 */

/** `"YYYY-MM-DD"` -> local midnight, or null when the string is not a date. */
export function parseDayInput(value: string | undefined): Date | null {
  if (!value) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
  if (!match) return null;
  const [, year, month, day] = match;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  // `new Date(2026, 1, 31)` rolls over into March, so a round-trip check is
  // what rejects "2026-02-31" instead of silently writing 03.03.
  if (
    date.getFullYear() !== Number(year) ||
    date.getMonth() !== Number(month) - 1 ||
    date.getDate() !== Number(day)
  ) {
    return null;
  }
  return date;
}

/** Local midnight -> `"YYYY-MM-DD"`, the value an `<input type="date">` takes. */
export function formatDayInput(date: Date | null): string {
  if (!date) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** The date cell of one row: the teacher's override, else the preset default. */
function dateValue(
  source: ExportSource,
  preset: ExportPreset,
  overrides: DateOverrides,
): ExportCellValue {
  // `overrides[id] ?? defaultDate(...)`: a teacher who CLEARS the input falls
  // back to the preset default rather than to nothing, which is what an empty
  // override string would otherwise mean.
  return (
    parseDayInput(overrides[source.id]) ?? preset.defaultDate(source.created_at)
  );
}

/**
 * Builds the export rows for `preset`.
 *
 * `assignments` is read-only here — it is copied, sorted on the copy, and every
 * value the preset returns is copied into a new row object.
 */
export function buildRows(
  preset: ExportPreset,
  assignments: readonly ExportSource[],
  overrides: DateOverrides = {},
): ExportRow[] {
  // The copy is the whole of "do not mutate the source"; the rest of this
  // function only ever READS from `sorted`.
  const sorted = [...assignments].sort(
    (a, b) =>
      createdTime(a.created_at) - createdTime(b.created_at) ||
      a.id.localeCompare(b.id),
  );

  return sorted.map((source, index) => {
    const values: Record<string, ExportCellValue> = {};
    for (const column of preset.columns) {
      values[column.key] =
        column.kind === "number"
          ? index + 1
          : column.kind === "date"
            ? dateValue(source, preset, overrides)
            : // A `text` column without a reader is a preset bug, and an EMPTY
              // CELL is the honest answer: the workbook then has a blank column
              // instead of a wrong one.
              (column.text?.(source) ?? "");
    }
    return { assignmentId: source.id, values };
  });
}