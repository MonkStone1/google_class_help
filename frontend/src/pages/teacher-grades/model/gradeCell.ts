/**
 * What one graded cell of the all-students matrix says, in the format the
 * teacher picked in Settings (ADR-0043).
 *
 * A pure function on purpose: the matrix is the only consumer today, so the rule
 * lives beside the page that draws it rather than in `shared/lib`, which must not
 * know what points and percentages are (ADR-0042). It is a function and not JSX
 * so all three formats are checked without a renderer.
 */

import type {
  SubmissionCell,
  TeacherGradeDisplay,
} from "../../../shared/types/index.ts";

/**
 * The text of a graded cell.
 *
 * - `points` — the raw mark alone (`12`). The maximum is deliberately left out:
 *   every column has its own task, so "12" next to a 100-point work means
 *   something different from "12" next to a 12-point one, and a teacher who
 *   wants the mark reads the column header.
 * - `ratio` — the mark out of the task (`12 / 12`), without the percentage: the
 *   journal's own notation, where the maximum travels with the mark.
 * - `percent` — the share alone (`100%`).
 * - `both` — the format the matrix has always had (`12 / 12 · 100%`).
 *
 * A cell whose percentage Classroom could not compute (no maximum on the task)
 * falls back to the raw mark rather than to an empty cell: the grade exists, and
 * hiding it would turn "no percentage" into "no grade" (ADR-0008).
 */
export function gradeCellText(
  cell: SubmissionCell,
  display: TeacherGradeDisplay,
): string {
  const points = cell.points ?? 0;
  if (display === "points") {
    return `${points}`;
  }
  const mark = `${points} / ${cell.max_points ?? "?"}`;
  if (display === "ratio") {
    return mark;
  }
  if (display === "percent") {
    return cell.percent === null ? `${points}` : `${cell.percent}%`;
  }
  return cell.percent === null ? mark : `${mark} · ${cell.percent}%`;
}