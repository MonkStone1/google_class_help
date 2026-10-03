import { describe, expect, it } from "vitest";

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

  it("turns each percentage into the mark the line will show", () => {
    // The percentage is converted ONCE, here: 87 % is an 11 and 87 itself is
    // never plotted, because the axis is a 12-point scale.
    const series = buildSeries(
      source([
        item({ assignment_id: "a", percent: 87 }),
        item({ assignment_id: "b", percent: 100 }),
      ]),
      t,
    );
    if (!series) throw new Error("two items must produce a series");

    expect(series.points.map((point) => point.grade)).toEqual([11, 12]);
    // The percentage itself survives for the tooltip, just not for the axis.
    expect(series.points.map((point) => point.percent)).toEqual([87, 100]);
  });

  it("caps each mark at the maximum its own task was worth", () => {
    // The end-to-end version of the rule: a task out of 11 points cannot be
    // worth a 12, however well it was answered.
    const series = buildSeries(
      source([
        item({
          assignment_id: "out-of-11",
          title: "Essay",
          points: 11,
          max_points: 11,
          percent: 100,
        }),
        item({
          assignment_id: "out-of-12",
          title: "Exam",
          points: 12,
          max_points: 12,
          percent: 100,
        }),
      ]),
      t,
    );
    if (!series) throw new Error("two items must produce a series");

    expect(series.points.map((point) => point.grade)).toEqual([11, 12]);
  });

  it("keeps a missing score missing instead of drawing the lowest mark", () => {
    const series = buildSeries(
      source([
        item({ assignment_id: "with", points: 80, percent: 80 }),
        item({
          assignment_id: "without",
          points: null,
          max_points: null,
          percent: null,
        }),
      ]),
      t,
    );
    if (!series) throw new Error("two items must produce a series");

    // No mark at all: a dot at the bottom of a 1…12 scale would be a claim the
    // teacher never made.
    expect(series.points[1].grade).toBeNull();
    // And the graded work is untouched by its ungraded neighbour.
    expect(series.points[0].grade).toBe(10);
  });

  it("returns nothing at all for a course with fewer than two graded works", () => {
    // Not an empty chart: one mark is not a trend, and the caller turns `null`
    // into a disabled button.
    expect(buildSeries(source([]), t)).toBeNull();
    expect(buildSeries(source([item()]), t)).toBeNull();
  });

  it("labels the axis with the twelve marks and nothing else", () => {
    const series = buildSeries(
      source([item({ assignment_id: "a" }), item({ assignment_id: "b" })]),
      t,
    );

    expect(series?.ticks.map((tick) => tick.value)).toEqual([
      1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
    ]);
    // One axis, not two: the same fact on a second scale is a second thing to
    // misread, not a second fact.
    expect(series).not.toHaveProperty("rightTicks");
    expect(series).not.toHaveProperty("averageY");
  });
});