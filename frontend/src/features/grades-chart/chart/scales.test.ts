import { describe, expect, it } from "vitest";

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
import {
  bandCenter,
  bandWidth,
  formatTick,
  gradeTicks,
  labelStride,
  percentToGrade,
  yScale,
} from "./scales.ts";

describe("the percentage-to-mark rule", () => {
  it("puts each mark at the lowest percentage that earns it", () => {
    // The Ukrainian 12-point scale. These boundaries are the whole rule: 89 % is
    // an 11 and 90 % is a 12, which is exactly the distinction a linear
    // `percent / 100 * 12` would have thrown away.
    expect(percentToGrade(100)).toBe(12);
    expect(percentToGrade(90)).toBe(12);
    expect(percentToGrade(89.9)).toBe(11);
    expect(percentToGrade(85)).toBe(11);
    expect(percentToGrade(80)).toBe(10);
    expect(percentToGrade(75)).toBe(9);
    expect(percentToGrade(70)).toBe(8);
    expect(percentToGrade(65)).toBe(7);
    expect(percentToGrade(60)).toBe(6);
    expect(percentToGrade(50)).toBe(5);
    expect(percentToGrade(45)).toBe(4);
    expect(percentToGrade(35)).toBe(3);
    expect(percentToGrade(20)).toBe(2);
  });

  it("never returns zero, and never returns null for a number", () => {
    // On this scale there is no zero, and below 20 % the answer is still a mark:
    // the teacher gave a low mark, not "no mark".
    expect(percentToGrade(19.9)).toBe(1);
    expect(percentToGrade(0)).toBe(1);
    expect(percentToGrade(-10)).toBe(1);
    // A bonus cannot push a mark above the top of the scale.
    expect(percentToGrade(140)).toBe(12);
    for (const percent of [0, 1, 49, 50, 99, 100]) {
      const grade = percentToGrade(percent);
      expect(grade).toBeGreaterThanOrEqual(GRADE_MIN);
      expect(grade).toBeLessThanOrEqual(GRADE_MAX);
    }
  });

  it("has no mark to give when there is no percentage", () => {
    // An ungraded assignment gets no point on the line: inventing the lowest
    // mark would draw a fall the teacher never recorded.
    expect(percentToGrade(null)).toBeNull();
    expect(percentToGrade(undefined)).toBeNull();
  });
});

describe("the grade axis", () => {
  it("labels every mark from 1 to 12, once each", () => {
    const ticks = gradeTicks();

    expect(ticks).toHaveLength(TICK_COUNT);
    expect(ticks.map((tick) => tick.value)).toEqual([
      1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
    ]);
    // Whole numbers, so no rounding is ever involved in a label.
    for (const tick of ticks) {
      expect(formatTick(tick.value)).toBe(String(tick.value));
    }
  });

  it("puts mark 12 at the top of the plot and mark 1 at the bottom", () => {
    // SVG grows downward, so an inverted scale would draw a rising mark as a
    // falling one — the classic silent chart bug.
    expect(yScale(GRADE_MAX)).toBe(PLOT_TOP);
    expect(yScale(GRADE_MIN)).toBe(PLOT_BOTTOM);
    // There is no mark in the middle of 1…12 — the scale has an even number of
    // steps, so its centre sits BETWEEN 6 and 7 and neither of them is on it.
    expect(yScale(6.5)).toBeCloseTo((PLOT_TOP + PLOT_BOTTOM) / 2, 6);
    expect(yScale(6)).toBeGreaterThan((PLOT_TOP + PLOT_BOTTOM) / 2);
    expect(yScale(7)).toBeLessThan((PLOT_TOP + PLOT_BOTTOM) / 2);
  });

  it("spaces the marks evenly", () => {
    const ys = gradeTicks().map((tick) => tick.y);
    const steps = ys.slice(1).map((y, index) => ys[index] - y);
    for (const step of steps) {
      expect(step).toBeCloseTo(steps[0], 6);
    }
    // And a mark is higher on the screen than the one below it.
    expect(steps[0]).toBeGreaterThan(0);
  });

  it("pins a mark outside the scale to the nearest end", () => {
    expect(yScale(99)).toBe(PLOT_TOP);
    expect(yScale(-5)).toBe(PLOT_BOTTOM);
  });
});

describe("the X scale", () => {
  it("places the first and the last band symmetrically around the centre", () => {
    const count = 6;
    const first = bandCenter(0, count);
    const last = bandCenter(count - 1, count);
    const centre = PLOT_LEFT + PLOT_WIDTH / 2;
    expect(first + last).toBeCloseTo(centre * 2, 6);
    expect(first).toBeGreaterThan(PLOT_LEFT);
    expect(last).toBeLessThan(PLOT_LEFT + PLOT_WIDTH);
  });

  it("survives a single band without dividing by zero", () => {
    // One graded work is a disabled button, not a crash: `buildSeries` may
    // still be handed such data.
    expect(bandWidth(1)).toBe(PLOT_WIDTH);
    expect(Number.isFinite(bandCenter(0, 1))).toBe(true);
    expect(Number.isFinite(bandCenter(0, 0))).toBe(true);
  });

  it("thins the date labels of a long course instead of overprinting them", () => {
    expect(labelStride(10)).toBe(1);
    expect(labelStride(11)).toBe(2);
    expect(labelStride(60)).toBe(6);
    for (const count of [2, 7, 20, 60, 200]) {
      expect(Math.ceil(count / labelStride(count))).toBeLessThanOrEqual(
        MAX_X_LABELS,
      );
    }
  });
});