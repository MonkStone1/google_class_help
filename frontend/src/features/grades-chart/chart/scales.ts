/**
 * Pure scales for the grade chart (ADR-0042).
 *
 * No React and no DOM: a scale that could only be checked by rendering is a
 * scale nobody checks, and the arithmetic here is exactly the part a chart
 * library would have got subtly wrong.
 *
 * The one rule with a real decision in it is {@link percentToGrade}: Google
 * Classroom speaks percentages (ADR-0008) and a school reads marks on a
 * 12-point scale, so the chart converts between them ONCE, here, and every
 * layer above works in marks.
 */

import {
  GRADE_MAX,
  GRADE_MIN,
  MAX_X_LABELS,
  PLOT_BOTTOM,
  PLOT_LEFT,
  PLOT_TOP,
  PLOT_WIDTH,
  TICK_COUNT,
} from "./layout.ts";

/**
 * Percentage → mark, on the 12-point scale used in Ukrainian schools.
 *
 * The table is thresholds, not arithmetic: `round(percent / 100 × 12)` would
 * make 89 % and 90 % the same mark, and those are 11 and 12. Each row is the
 * lowest percentage that earns that mark, walked from the top down.
 *
 * Below 20 % the answer is 1 rather than "nothing" — on this scale there is no
 * zero, and a chart showing 0 would be showing a mark no teacher gives.
 */
const GRADE_THRESHOLDS: ReadonlyArray<readonly [number, number]> = [
  [90, 12],
  [85, 11],
  [80, 10],
  [75, 9],
  [70, 8],
  [65, 7],
  [60, 6],
  [50, 5],
  [45, 4],
  [35, 3],
  [20, 2],
];

/**
 * The mark a percentage earns, never above what the task could award.
 *
 * `maxPoints` is the ceiling, not a detail: a task graded out of 11 points has
 * no way to earn a 12, so 11/11 is an 11 — capping the answer at the task's own
 * maximum is what keeps the line from claiming a mark that was unreachable.
 * `null`/`undefined` means the task declared no maximum, and then the scale's own
 * top applies.
 *
 * `null` percentage in, `null` out: an ungraded assignment has no mark, and
 * inventing one would draw a point the teacher never gave.
 */
export function percentToGrade(
  percent: number | null | undefined,
  maxPoints: number | null | undefined = null,
): number | null {
  if (percent === null || percent === undefined) {
    return null;
  }
  const value = Math.min(100, Math.max(0, percent));
  let mark = GRADE_MIN;
  for (const [threshold, grade] of GRADE_THRESHOLDS) {
    if (value >= threshold) {
      mark = grade;
      break;
    }
  }
  // A zero or negative maximum is not a ceiling, it is missing data, so it must
  // not collapse every mark to zero.
  if (maxPoints === null || maxPoints === undefined || maxPoints <= 0) {
    return mark;
  }
  return Math.min(mark, Math.floor(maxPoints));
}

/**
 * Vertical position of a mark on the 1…12 axis.
 *
 * Y grows downward in SVG, so mark 12 is at {@link PLOT_TOP} and mark 1 at
 * {@link PLOT_BOTTOM}. A mark outside 1…12 is pinned to the nearest end instead
 * of being drawn outside the plot.
 */
export function yScale(grade: number): number {
  const clamped = Math.min(GRADE_MAX, Math.max(GRADE_MIN, grade));
  const ratio = (clamped - GRADE_MIN) / (GRADE_MAX - GRADE_MIN);
  return PLOT_BOTTOM - ratio * (PLOT_BOTTOM - PLOT_TOP);
}

/** Width of one category band. Zero bands are impossible (see `bandCenter`). */
export function bandWidth(count: number): number {
  return count > 0 ? PLOT_WIDTH / count : PLOT_WIDTH;
}

/**
 * Centre of the band at `index` — the X position of a point.
 *
 * The single point case must not divide by zero: a course with one graded work
 * has no chart (the button is disabled), but `buildSeries` must not throw if it
 * is ever called with such data.
 */
export function bandCenter(index: number, count: number): number {
  return PLOT_LEFT + bandWidth(count) * (index + 0.5);
}

/** Every `stride`-th band keeps its label, so a long course stays readable. */
export function labelStride(count: number): number {
  return Math.max(1, Math.ceil(count / MAX_X_LABELS));
}

/** Ticks of the grade axis, from mark 1 at the bottom up to mark 12. */
export function gradeTicks(): Array<{ value: number; y: number }> {
  return Array.from({ length: TICK_COUNT }, (_unused, index) => {
    const value = GRADE_MIN + index;
    return { value, y: yScale(value) };
  });
}

/** Axis labels: the marks are whole numbers, so no rounding is involved. */
export function formatTick(value: number): string {
  return String(value);
}