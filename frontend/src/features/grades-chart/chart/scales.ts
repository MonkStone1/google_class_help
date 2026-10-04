/**
 * Pure scales for the grade chart (ADR-0042).
 *
 * No React and no DOM: a scale that could only be checked by rendering is a
 * scale nobody checks.
 *
 * There is NO percentage-to-mark table here, and that is the point. The chart
 * plots the points Classroom stores, unchanged. An earlier version converted
 * `percent` into a mark on the 1…12 scale through a table of thresholds, and it
 * was wrong in a way that read as a feature: a task worth 11 points capped the
 * answer at 11, so 11/11 (a full score) sat BELOW 11/12 (one point short of
 * full). Raw points cannot do that — 11 is 11 whatever the task was worth, and
 * the order of the marks is the order of the work.
 *
 * What the top of the axis means is the user's to say, in Settings: a Ukrainian
 * school marks out of 12, a percentage-style course out of 100 (ADR-0042).
 */

import {
  HIT_RADIUS,
  MAX_TICKS,
  MAX_X_LABELS,
  PLOT_BOTTOM,
  PLOT_LEFT,
  PLOT_RIGHT,
  PLOT_TOP,
  PLOT_WIDTH,
  TICK_STEPS,
} from "./layout.ts";

/**
 * Vertical position of a score on the 0…`scale` axis.
 *
 * Y grows downward in SVG, so the top of the scale is at {@link PLOT_TOP} and
 * zero at {@link PLOT_BOTTOM}. A score outside the scale is pinned to the
 * nearest end rather than drawn outside the plot — which is what a 100-point
 * course looks like on a 12-point axis until the setting is changed.
 */
export function yScale(score: number, scale: number): number {
  if (scale <= 0) return PLOT_BOTTOM;
  const clamped = Math.min(scale, Math.max(0, score));
  return PLOT_BOTTOM - (clamped / scale) * (PLOT_BOTTOM - PLOT_TOP);
}

/** Width of one category band. Zero bands are impossible (see `bandCenter`). */
export function bandWidth(count: number): number {
  return count > 0 ? PLOT_WIDTH / count : PLOT_WIDTH;
}

/**
 * X position of the point at `index`.
 *
 * The bands are anchored at the AXES and grow INWARDS, rather than splitting the
 * plot in half a band at each end. `bandCenter(0)` sits one half-band from the
 * left axis and `bandCenter(n - 1)` one half-band from the right axis, with the
 * rest evenly spaced between them.
 *
 * That is the whole difference between a point fully inside the frame and one
 * touching it. On a course with 60 graded works a band is 14 units wide, so a
 * point centred half a band in from the FRAME edge sits 7 units from the axis —
 * and its 20-unit hit circle then hangs across the axis line and out of the
 * picture, which is what sliced the first point in half. Measuring from the axes
 * keeps the extreme points clear of both the line and the border whatever the
 * count, because the inset is itself sized to hold them.
 *
 * The single point case must not divide by zero: a course with one graded work
 * has no chart (the button is disabled), but `buildSeries` must not throw if it
 * is ever called with such data.
 */
export function bandCenter(index: number, count: number): number {
  if (count <= 0) {
    return PLOT_LEFT + PLOT_WIDTH / 2;
  }
  const width = bandWidth(count);
  const half = width / 2;
  // A band narrower than the hit circle would otherwise put the first and last
  // points on top of each other, and both of them under the axis line.
  const inset = Math.max(half, HIT_RADIUS + 2);
  if (index === 0) {
    return PLOT_LEFT + inset;
  }
  if (index === count - 1) {
    return PLOT_RIGHT - inset;
  }
  return PLOT_LEFT + half + (PLOT_WIDTH - 2 * inset) * (index / (count - 1));
}

/** Every `stride`-th band keeps its label, so a long course stays readable. */
export function labelStride(count: number): number {
  return Math.max(1, Math.ceil(count / MAX_X_LABELS));
}

/**
 * Distance between neighbouring ticks on a 0…`scale` axis.
 *
 * Chosen from a fixed ladder of round steps so the labels stay countable: 2 on
 * a 12-point scale gives 0/2/4/6/8/10/12, and 20 on a 100-point one gives
 * 0/20/40/60/80/100. A step outside the ladder would print 16.7 on the axis, and
 * an axis nobody can count along is worse than a coarse one.
 */
export function tickStep(scale: number): number {
  const usable = TICK_STEPS.filter((step) => scale % step === 0);
  // The finest step that still keeps the labels from crowding: 12 steps by 2
  // rather than 1 (twelve labels is a wall) and 100 steps by 20 rather than 10.
  // Going coarser than this would leave a nearly empty axis, which reads as
  // "there is nothing between 0 and 12".
  for (const step of usable) {
    if (scale / step <= MAX_TICKS) {
      return step;
    }
  }
  // A scale no ladder step divides (a future one, say) still gets a usable
  // axis: fall back to the largest step that fits inside MAX_TICKS intervals.
  return Math.max(1, Math.floor(scale / MAX_TICKS));
}

/**
 * Ticks of the score axis, from 0 at the bottom up to `scale`.
 *
 * The TOP of the scale is always a tick: an axis that stopped short of its own
 * maximum would make the highest possible mark look like it falls off the chart.
 */
export function scaleTicks(scale: number): Array<{ value: number; y: number }> {
  if (scale <= 0) {
    return [{ value: 0, y: yScale(0, scale) }];
  }
  const step = tickStep(scale);
  const ticks: Array<{ value: number; y: number }> = [];
  for (let value = 0; value < scale; value += step) {
    ticks.push({ value, y: yScale(value, scale) });
  }
  ticks.push({ value: scale, y: yScale(scale, scale) });
  return ticks;
}

/** Axis labels: the points are whole numbers, so no rounding is involved. */
export function formatTick(value: number): string {
  return String(value);
}