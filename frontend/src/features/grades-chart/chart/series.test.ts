import { describe, expect, it } from "vitest";

import { PLOT_BOTTOM, PLOT_TOP, TICK_COUNT } from "./layout.ts";
import { PERCENT_MAX, yScale } from "./scales.ts";
import { buildSeries, type Translate } from "./series.ts";
import type { ChartSource } from "./types.ts";
import type { GradeItem } from "../../../shared/types/index.ts";

/**
 * English is not what is under test here — the LABELS are — so the fake
 * dictionary returns the key itself. That makes an untranslated label fail
 * loudly instead of quietly reading as a date.
 */
const t: Translate = (key, vars) =>
  vars ? `${key}:${JSON.stringify(vars)}` : key;

function item(overrides: Partial<GradeItem> = {}): GradeItem {
  return {
    assignment_id: "a1",
    title: "Homework 1",
    points: 80,
    max_points: 100,
    percent: 80,
    graded_at: null,
    due_at: "2026-01-12T12:00:00",
    ...overrides,
  };
}

function source(items: GradeItem[], overrides: Partial<ChartSource> = {}) {
  return {
    courseId: "c1",
    courseName: "Algebra",
    average: 87,
    items,
    ...overrides,
  };
}

describe("what one render of the chart is built from", () => {
  it("leaves the caller's items exactly as they were", () => {
    // The items belong to the cached courses state, which the dashboard and the
    // subject page read too; sorting them in place would reorder those views.
    const items = [
      item({ assignment_id: "a2", due_at: "2026-02-01T12:00:00" }),
      item({ assignment_id: "a1", due_at: "2026-01-12T12:00:00" }),
    ];
    const snapshot = JSON.stringify(items);

    buildSeries(source(items), t);

    expect(JSON.stringify(items)).toBe(snapshot);
    expect(items[0].assignment_id).toBe("a2");
  });

  it("orders the points by deadline, so the X axis is a timeline", () => {
    const series = buildSeries(
      source([
        item({ assignment_id: "third", due_at: "2026-03-01T12:00:00" }),
        item({ assignment_id: "first", due_at: "2026-01-12T12:00:00" }),
        item({ assignment_id: "second", due_at: "2026-02-01T12:00:00" }),
      ]),
      t,
    );

    expect(series?.points.map((point) => point.key)).toEqual([
      "first",
      "second",
      "third",
    ]);
  });

  it("sends assignments without a deadline to the end, keeping their order", () => {
    const series = buildSeries(
      source([
        item({ assignment_id: "noDue-1", due_at: null }),
        item({ assignment_id: "dated", due_at: "2026-01-12T12:00:00" }),
        item({ assignment_id: "noDue-2", due_at: null }),
      ]),
      t,
    );

    expect(series?.points.map((point) => point.key)).toEqual([
      "dated",
      "noDue-1",
      "noDue-2",
    ]);
    // And the ones without a deadline are labelled by their position, because
    // there is no date to put under them. The number is the ONE-BASED position
    // in the sorted series, which is what the reader is counting.
    expect(series?.xLabels[1].text).toBe('grades.chart.noAxisTask:{"n":2}');
    expect(series?.xLabels[2].text).toBe('grades.chart.noAxisTask:{"n":3}');
  });

  it("carries the percent through without recomputing it", () => {
    // The page already rounds to 0.1 %; recomputing here would show 79.999… on
    // one screen and 80 on another.
    const series = buildSeries(
      source([
        item({ assignment_id: "a", percent: 79.9 }),
        item({ assignment_id: "b", percent: 100 }),
      ]),
      t,
    );

    expect(series?.points.map((point) => point.percent)).toEqual([79.9, 100]);
  });

  it("keeps a missing score missing instead of drawing a zero bar", () => {
    const series = buildSeries(
      source([
        item({ assignment_id: "with", points: 80, percent: 80 }),
        item({ assignment_id: "without", points: null, max_points: null, percent: null }),
      ]),
      t,
    );

    const missing = series?.points[1];
    expect(missing?.points).toBeNull();
    expect(missing?.percent).toBeNull();
    // The other point is untouched: one gapless bar must not shift the rest.
    expect(series?.points[0].points).toBe(80);
  });

  it("draws no average line for a course that has no average", () => {
    const series = buildSeries(
      source([item({ assignment_id: "a" }), item({ assignment_id: "b" })], {
        average: null,
      }),
      t,
    );

    expect(series?.averageY).toBeNull();
  });

  it("places the average line on the percent axis at its own value", () => {
    const series = buildSeries(
      source([item({ assignment_id: "a" }), item({ assignment_id: "b" })]),
      t,
    );
    if (!series) throw new Error("two items must produce a series");

    expect(series.averageY).toBe(yScale(87, PERCENT_MAX));
    // 87 % is 13 % of the way down from the top, and above the midpoint: a
    // reader must be able to see the average sits high on the percent axis.
    expect(series.averageY).toBeGreaterThan(PLOT_TOP);
    expect(series.averageY).toBeLessThan((PLOT_TOP + PLOT_BOTTOM) / 2);
  });

  it("returns nothing at all for a course with fewer than two graded works", () => {
    // Not an empty chart: one bar is not a trend, and the caller turns `null`
    // into a disabled button.
    expect(buildSeries(source([]), t)).toBeNull();
    expect(buildSeries(source([item()]), t)).toBeNull();
  });

  it("gives both axes five ticks that share their Y positions", () => {
    const series = buildSeries(
      source([item({ assignment_id: "a" }), item({ assignment_id: "b" })]),
      t,
    );

    expect(series?.leftTicks).toHaveLength(TICK_COUNT);
    expect(series?.rightTicks).toHaveLength(TICK_COUNT);
    expect(series?.rightTicks.map((tick) => tick.y)).toEqual(
      series?.leftTicks.map((tick) => tick.y),
    );
  });
});