import { describe, expect, it } from "vitest";

import {
  MAX_X_LABELS,
  PLOT_BOTTOM,
  PLOT_LEFT,
  PLOT_TOP,
  PLOT_WIDTH,
  TICK_COUNT,
} from "./layout.ts";
import {
  PERCENT_MAX,
  bandCenter,
  bandWidth,
  formatTick,
  labelStride,
  niceMax,
  ticksFor,
  yScale,
} from "./scales.ts";

describe("the upper bound of the points axis", () => {
  it("keeps a 100-point course readable as 0…100", () => {
    // The whole point of the double axis: a 100-point course makes both scales
    // read identically, so a bar and a dot at the same height mean the same.
    expect(niceMax(100)).toBe(100);
  });

  it("rounds every input UP to a multiple of 25, and never below 25", () => {
    // The multiple of 25 is not cosmetic: `ticksFor` divides the axis into four
    // intervals, so a bound of 87 would put ticks at 21.75 and no tick would
    // coincide with a gridline.
    for (const value of [0, 1, 12, 25, 26, 49, 50, 87, 100, 340, 1000]) {
      const bound = niceMax(value);
      expect(bound % 25).toBe(0);
      expect(bound).toBeGreaterThanOrEqual(value);
    }
    expect(niceMax(0)).toBe(25);
    expect(niceMax(null)).toBe(25);
    expect(niceMax(undefined)).toBe(25);
  });

  it("gives a course graded out of 12 a 0…25 axis, and out of 26 a 0…50 one", () => {
    expect(niceMax(12)).toBe(25);
    expect(niceMax(26)).toBe(50);
  });
});

describe("the ticks of the points axis", () => {
  it("lands every right-axis tick on a gridline of the shared grid", () => {
    // The grid is drawn from the PERCENT ticks; a right-axis tick that fell
    // between two of them would have no line to sit on. Equal step, equal Y.
    const step = niceMax(26) / (TICK_COUNT - 1);
    expect(step).toBe(12.5);

    const leftYs = ticksFor(PERCENT_MAX).map((tick) => tick.y);
    const rightYs = ticksFor(niceMax(26)).map((tick) => tick.y);
    expect(rightYs).toEqual(leftYs);
  });

  it("labels a fractional step without pretending it is a whole number", () => {
    expect(formatTick(6.25)).toBe("6.25");
    expect(formatTick(12.5)).toBe("12.5");
    expect(formatTick(100)).toBe("100");
    // 0.1 + 0.2 is 0.30000000000000004 in IEEE 754; an axis label is not the
    // place to show that off.
    expect(formatTick(0.1 + 0.2)).toBe("0.3");
  });
});

describe("the vertical scale", () => {
  it("puts the lower bound at the bottom of the plot and the upper at the top", () => {
    expect(yScale(0, 100)).toBe(PLOT_BOTTOM);
    expect(yScale(100, 100)).toBe(PLOT_TOP);
    expect(yScale(0, 0)).toBe(PLOT_BOTTOM);
  });

  it("puts the middle of the range in the middle of the plot", () => {
    // SVG grows downward, so the midpoint is the average of the two bounds and
    // nothing else — an inverted axis is the classic silent chart bug.
    expect(yScale(50, 100)).toBe((PLOT_TOP + PLOT_BOTTOM) / 2);
  });

  it("pins a value above the axis to the top instead of drawing outside it", () => {
    expect(yScale(140, 100)).toBe(PLOT_TOP);
    expect(yScale(-5, 100)).toBe(PLOT_BOTTOM);
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

  it("thins the X labels of a long course instead of overprinting them", () => {
    expect(labelStride(12)).toBe(1);
    expect(labelStride(13)).toBe(2);
    expect(labelStride(60)).toBe(5);
    // Whatever the count, no more than the readable maximum of labels.
    for (const count of [2, 7, 20, 60, 200]) {
      expect(Math.ceil(count / labelStride(count))).toBeLessThanOrEqual(
        MAX_X_LABELS,
      );
    }
  });
});