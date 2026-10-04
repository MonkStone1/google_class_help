import { describe, expect, it } from "vitest";

import {
  CHART_WIDTH,
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
import {
  bandCenter,
  bandWidth,
  formatTick,
  labelStride,
  scaleTicks,
  tickStep,
  yScale,
} from "./scales.ts";

/** The two scales Settings offers (ADR-0042). */
const SCALES = [12, 100] as const;

describe("the score axis", () => {
  it("labels the scale from 0 to its top, with round steps", () => {
    for (const scale of SCALES) {
      const ticks = scaleTicks(scale);
      // It starts at zero: a line pinned to the bottom would claim every work
      // scored nothing.
      expect(ticks[0].value).toBe(0);
      // And it REACHES the top. An axis stopping short of its own maximum makes
      // the best possible score look like it falls off the chart.
      expect(ticks[ticks.length - 1].value).toBe(scale);
      // The labels must be countable, never 16.7.
      for (const tick of ticks) {
        expect(Number.isInteger(tick.value)).toBe(true);
        expect(tick.value % tickStep(scale)).toBe(0);
      }
      expect(ticks.length).toBeLessThanOrEqual(MAX_TICKS + 1);
    }
  });

  it("steps by 2 on a 12-point scale and by 20 on a 100-point one", () => {
    expect(tickStep(12)).toBe(2);
    expect(tickStep(100)).toBe(20);
    expect(scaleTicks(12).map((tick) => tick.value)).toEqual([
      0, 2, 4, 6, 8, 10, 12,
    ]);
    expect(scaleTicks(100).map((tick) => tick.value)).toEqual([
      0, 20, 40, 60, 80, 100,
    ]);
  });

  it("only ever steps by a number the axis can be counted by", () => {
    // Every step divides at least one real scale, so no axis ever prints 16.7.
    for (const step of TICK_STEPS) {
      expect(12 % step === 0 || 100 % step === 0).toBe(true);
    }
    // And a scale neither divides still gets a sane axis rather than a loop of
    // hundreds of labels.
    expect(tickStep(7)).toBeGreaterThanOrEqual(1);
    expect(scaleTicks(7).length).toBeLessThanOrEqual(MAX_TICKS + 1);
  });

  it("puts the top of the scale at the top of the plot and 0 at the bottom", () => {
    // SVG grows downward, so an inverted scale would draw a rising score as a
    // falling one — the classic silent chart bug.
    expect(yScale(12, 12)).toBe(PLOT_TOP);
    expect(yScale(0, 12)).toBe(PLOT_BOTTOM);
    expect(yScale(100, 100)).toBe(PLOT_TOP);
    expect(yScale(0, 100)).toBe(PLOT_BOTTOM);
    // Halfway up is halfway up, on both scales.
    expect(yScale(6, 12)).toBeCloseTo((PLOT_TOP + PLOT_BOTTOM) / 2, 6);
    expect(yScale(50, 100)).toBeCloseTo((PLOT_TOP + PLOT_BOTTOM) / 2, 6);
  });

  it("spaces the ticks evenly", () => {
    for (const scale of SCALES) {
      const ys = scaleTicks(scale).map((tick) => tick.y);
      const steps = ys.slice(1).map((y, index) => ys[index] - y);
      for (const step of steps) {
        expect(step).toBeCloseTo(steps[0], 6);
      }
      // A higher score is higher on the screen than a lower one.
      expect(steps[0]).toBeGreaterThan(0);
    }
  });

  it("scales a score by its own scale, so 11 is at the same height on both", () => {
    // The regression this guards, in its purest form: a full 11 out of 11 and a
    // near-full 11 out of 12 are the SAME 11 points, and the chart must place
    // them at the same height. Deriving a mark from a percentage used to cap it
    // at each task's own maximum, which put 11/11 BELOW 11/12.
    expect(yScale(11, 12)).toBe(yScale(11, 12));
    // And the same points on a 100-point axis sit proportionally lower, because
    // the scale is four times taller — which is the honest reading.
    expect(yScale(11, 12)).not.toBe(yScale(11, 100));
  });

  it("pins a score outside the scale to the nearest end", () => {
    // A 100-point course on a 12-point axis (the setting is wrong) must not draw
    // outside the plot, and a negative score must not hang below it.
    expect(yScale(100, 12)).toBe(PLOT_TOP);
    expect(yScale(-5, 12)).toBe(PLOT_BOTTOM);
  });

  it("survives a scale of zero without dividing by zero", () => {
    expect(yScale(5, 0)).toBe(PLOT_BOTTOM);
    expect(scaleTicks(0)).toHaveLength(1);
  });

  it("prints whole numbers on the axis", () => {
    for (const tick of scaleTicks(12)) {
      expect(formatTick(tick.value)).toBe(String(tick.value));
    }
  });
});

describe("the X scale", () => {
  it("keeps the first and last points fully inside the frame, however many there are", () => {
    // The regression this guards: on a long course the band is narrow, so a point
    // centred half a band in from the FRAME sat ~7 units from the axis and its
    // hit circle hung outside the picture — the first point looked sliced.
    for (const count of [2, 5, 12, 40, 60, 200]) {
      const first = bandCenter(0, count);
      const last = bandCenter(count - 1, count);
      // The hit circle must clear the axis line, the border and the top/bottom.
      expect(first - HIT_RADIUS).toBeGreaterThanOrEqual(PLOT_LEFT);
      expect(last + HIT_RADIUS).toBeLessThanOrEqual(PLOT_RIGHT);
      expect(first - HIT_RADIUS).toBeGreaterThan(0);
      expect(last + HIT_RADIUS).toBeLessThan(CHART_WIDTH);
      // And they must stay in order — a fix that moved them would be no fix.
      expect(first).toBeLessThan(last);
    }
  });

  it("spaces the points evenly between the two ends", () => {
    const count = 6;
    const xs = Array.from({ length: count }, (_u, i) => bandCenter(i, count));
    const steps = xs.slice(1).map((x, i) => x - xs[i]);
    for (const step of steps) {
      expect(step).toBeCloseTo(steps[0], 6);
    }
    // Symmetric: the first step from the left axis mirrors the last one.
    expect(xs[0] - PLOT_LEFT).toBeCloseTo(PLOT_RIGHT - xs[count - 1], 6);
  });

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