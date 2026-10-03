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

/** One plotted assignment: everything both axes and the tooltip need. */
export type ChartPoint = {
  /** `assignment_id` — the React key and the focus target. */
  key: string;
  /** Full title: the tooltip line and the hidden table's first column. */
  title: string;
  /** Category label under the X axis: a date, or `#{n}` without a deadline. */
  label: string;
  /** Parsed `due_at`, kept for the tooltip and for sorting. */
  due: Date | null;
  /** Earned points — the bar series, on the RIGHT axis. */
  points: number | null;
  /** Score in percent — the line series, on the LEFT axis. */
  percent: number | null;
};

/** What the page hands the feature: a course and the grades it already holds. */
export type ChartSource = {
  courseId: string;
  courseName: string;
  /** Course average; `null` means there is no dashed line to draw. */
  average: number | null;
  items: readonly GradeItem[];
};

/** A tick with its position already in `viewBox` units. */
export type AxisTick = {
  value: number;
  y: number;
};

/** Everything one render of the chart needs, computed once per data change. */
export type ChartSeries = {
  points: ChartPoint[];
  /** Percent axis, always 0…100. */
  leftTicks: AxisTick[];
  /** Points axis, always 0…niceMax. */
  rightTicks: AxisTick[];
  xLabels: Array<{ text: string; x: number }>;
  /** Dashed course-average line, or `null` when the course has no average. */
  averageY: number | null;
};