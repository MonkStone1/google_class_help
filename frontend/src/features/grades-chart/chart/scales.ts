/**
 * Pure scales for the grade chart (ADR-0042).
 *
 * No React and no DOM: a scale that could only be checked by rendering is a
 * scale nobody checks, and the arithmetic here is exactly the part a chart
 * library would have got subtly wrong. `niceMax` in particular is the rule that
 * keeps the right axis ON the grid — a nice-looking axis whose ticks do not
 * coincide with the horizontal lines is worse than no right axis at all.
 */

import {
  MAX_X_LABELS,
  PLOT_BOTTOM,
  PLOT_LEFT,
  PLOT_TOP,
  PLOT_WIDTH,
  TICK_COUNT,
  TICK_STEP,
} from "./layout.ts";

/** The percent axis has a fixed domain: a score above 100 % is not a score. */
export const PERCENT_MAX = 100;

/**
 * Upper bound of the points axis: `25`, or the largest multiple of 25 that
 * covers `max`, whichever is larger.
 *
 * A course graded out of 10 therefore gets `0…25` rather than `0…10`, and one
 * graded out of 100 gets `0…100`, so both axes read the same way. The multiple
 * of 25 is what makes `niceMax / 4` land on a gridline; `ceil(10 / 25) * 25`
 * gives 25 for a course of 10 points and 100 for a course of 87.
 */
export function niceMax(max: number | null | undefined): number {
  const value = max ?? 0;
  const rounded = Math.ceil(value / TICK_STEP) * TICK_STEP;
  return Math.max(TICK_STEP, rounded);
}

/**
 * Vertical position of `value` on an axis running 0…`max`.
 *
 * Y grows downward in SVG, so the top of the range is {@link PLOT_TOP} and the
 * bottom is {@link PLOT_BOTTOM}; a value above `max` is pinned to the top
 * rather than drawn outside the plot.
 */
export function yScale(value: number, max: number): number {
  if (max <= 0) {
    return PLOT_BOTTOM;
  }
  const clamped = Math.min(Math.max(value, 0), max);
  const ratio = clamped / max;
  return PLOT_TOP + (1 - ratio) * (PLOT_BOTTOM - PLOT_TOP);
}

/** Width of one category band. Zero bands are impossible (see `bandCenter`). */
export function bandWidth(count: number): number {
  return count > 0 ? PLOT_WIDTH / count : PLOT_WIDTH;
}

/**
 * Centre of the band at `index` — the X position of a bar or a point.
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

/** Ticks of an axis running 0…`max`, from the bottom up. */
export function ticksFor(max: number): Array<{ value: number; y: number }> {
  return Array.from({ length: TICK_COUNT }, (_unused, index) => {
    const value = (max / (TICK_COUNT - 1)) * index;
    return { value, y: yScale(value, max) };
  });
}

/**
 * Tick labels without floating-point noise: `100`, `6.25`, `12.5`, `0`.
 *
 * A course graded out of 25 gives a 6.25 step, so the labels cannot be rounded
 * to integers without lying about the axis — they are only rounded to two
 * decimals, which is where the division stops being meaningful anyway.
 */
export function formatTick(value: number): string {
  return String(Math.round(value * 100) / 100);
}