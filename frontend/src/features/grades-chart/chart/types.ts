/**
 * Contracts of the grade-trend chart (ADR-0042).
 *
 * The geometry lives in `viewBox` units, never in pixels: an SVG that scales to
 * its container means nothing here has to be measured, and `getBBox` /
 * `ResizeObserver` do not exist in jsdom, so a chart built on them could only be
 * tested by mocking what it draws.
 *
 * `ChartSource` is deliberately the same shape the grades page already holds
 * (`CourseGrades`), which is why the feature needs no request of its own.
 */

import type { GradeItem } from "../../../shared/types/index.ts";

/** One plotted assignment: everything the line, the tooltip and the table need. */
export type ChartPoint = {
  /** `assignment_id` — the React key and the focus target. */
  key: string;
  /** Full title: the tooltip line and the hidden table's first column. */
  title: string;
  /** Date label under the X axis, or `#{n}` without a deadline. */
  label: string;
  /** Parsed `due_at`, kept for the tooltip and for sorting. */
  due: Date | null;
  /**
   * The points Classroom stored for the work, plotted unchanged, or `null` when
   * the work carries no score. This is the ONLY value on the axis — see
   * {@link ChartSeries}. There is no percentage in the middle: deriving one
   * (see the history in `scales.ts`) is what made the line contradict itself.
   */
  score: number | null;
  /** The denominator behind `score`, shown in the tooltip and the table. */
  maxPoints: number | null;
};

/** What the page hands the feature: a course and the grades it already holds. */
export type ChartSource = {
  courseId: string;
  courseName: string;
  /** Course average; kept for the header, not drawn on the chart. */
  average: number | null;
  items: readonly GradeItem[];
};

/** A tick with its position already in `viewBox` units. */
export type AxisTick = {
  value: number;
  y: number;
};

/**
 * Everything one render of the chart needs.
 *
 * One series, one axis. There is no `rightTicks` and no `averageY`: a bar of
 * raw points beside a line of marks would have been the same fact drawn twice
 * on two scales, and a second scale is a second thing to misread.
 */
export type ChartSeries = {
  /**
   * The top of the axis, in points. The user's choice from Settings (ADR-0042):
   * the app cannot tell whether a course is marked out of 12 or out of 100, and
   * guessing wrong puts every point at the wrong height.
   */
  scale: number;
  points: ChartPoint[];
  /** The score axis, from 0 at the bottom up to `scale`. */
  ticks: AxisTick[];
  /** Date labels under the plot, one per point. */
  xLabels: Array<{ text: string; x: number }>;
};