import { describe, expect, it } from "vitest";

import { buildSeries, type Translate } from "./series.ts";
import type { ChartSource } from "./types.ts";
import type { GradeItem } from "../../../shared/types/index.ts";

/**
 * English is not what is under test here ? the LABELS are ? so the fake
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

const TWELVE = 12;
describe("what one render of the chart is built from", () => {
  it("leaves the caller's items exactly as they were", () => {
    // The items belong to the cached courses state, which the dashboard and the
    // subject page read too; sorting them in place would reorder those views.
    const items = [
      item({ assignment_id: "a2", due_at: "2026-02-01T12:00:00" }),
      item({ assignment_id: "a1", due_at: "2026-01-12T12:00:00" }),
    ];
    const snapshot = JSON.stringify(items);

    buildSeries(source(items), t, TWELVE);

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
      TWELVE,
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
      TWELVE,
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
});
describe("what the line plots", () => {
  it("plots the points exactly as Classroom stored them", () => {
    // No percentage in the middle: what the teacher awarded is what the line
    // shows, and what the tooltip and the hidden table quote.
    const series = buildSeries(
      source([
        item({ assignment_id: "a", points: 9, max_points: 12 }),
        item({ assignment_id: "b", points: 11, max_points: 12 }),
      ]),
      t,
      TWELVE,
    );
    if (!series) throw new Error("two items must produce a series");

    expect(series.points.map((point) => point.score)).toEqual([9, 11]);
    expect(series.points.map((point) => point.maxPoints)).toEqual([12, 12]);
  });

  it("keeps a full 11/11 level with a near-full 11/12, as the bug report demanded", () => {
    // THE regression. Deriving a mark from a percentage capped it at each task's
    // own maximum, so 11/11 (every single point) was drawn BELOW 11/12 (one
    // short) and the line claimed the student got worse on the work they nailed.
    const series = buildSeries(
      source([
        item({
          assignment_id: "out-of-12",
          title: "First",
          points: 11,
          max_points: 12,
        }),
        item({
          assignment_id: "out-of-11",
          title: "Second",
          points: 11,
          max_points: 11,
        }),
      ]),
      t,
      TWELVE,
    );
    if (!series) throw new Error("two items must produce a series");

    // Both are 11 points, so both sit at the same height: equal scores, equal marks.
    expect(series.points.map((point) => point.score)).toEqual([11, 11]);
    // The maxima DIFFER and the scores do not — that is the whole point. They are
    // context for the reader now, never an input to the plotted value.
    expect(series.points.map((point) => point.maxPoints)).toEqual([12, 11]);
  });

  it("keeps a missing score missing instead of drawing it at zero", () => {
    const series = buildSeries(
      source([
        item({ assignment_id: "with", points: 8 }),
        item({
          assignment_id: "without",
          points: null,
          max_points: null,
          percent: null,
        }),
      ]),
      t,
      TWELVE,
    );
    if (!series) throw new Error("two items must produce a series");

    // No dot at all: a dot on the floor would be a claim the teacher never made.
    expect(series.points[1].score).toBeNull();
    // And the graded work is untouched by its ungraded neighbour.
    expect(series.points[0].score).toBe(8);
  });

  it("returns nothing at all for a course with fewer than two graded works", () => {
    // Not an empty chart: one mark is not a trend, and the caller turns `null`
    // into a disabled button.
    expect(buildSeries(source([]), t, TWELVE)).toBeNull();
    expect(buildSeries(source([item()]), t, TWELVE)).toBeNull();
  });

  it("labels the axis from 0 up to the scale the user chose", () => {
    const two = () => [
      item({ assignment_id: "a" }),
      item({ assignment_id: "b" }),
    ];
    const twelve = buildSeries(source(two()), t, TWELVE);
    const hundred = buildSeries(source(two()), t, 100);

    expect(twelve?.scale).toBe(12);
    expect(twelve?.ticks.map((tick) => tick.value)).toEqual([
      0, 2, 4, 6, 8, 10, 12,
    ]);
    expect(hundred?.scale).toBe(100);
    expect(hundred?.ticks.map((tick) => tick.value)).toEqual([
      0, 20, 40, 60, 80, 100,
    ]);
    // One axis, not two: the same fact on a second scale is a second thing to
    // misread, not a second fact.
    expect(twelve).not.toHaveProperty("rightTicks");
    expect(twelve).not.toHaveProperty("averageY");
  });
});
