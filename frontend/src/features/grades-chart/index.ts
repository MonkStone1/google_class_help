/**
 * The public API of `features/grades-chart` — the grade-trend chart the grades
 * page opens in a modal (ADR-0042).
 *
 * The split below is the whole design:
 *
 * - `chart/` is the maths: what counts as a point, where it goes, which ticks
 *   exist. Pure functions, no React, tested without a DOM.
 * - `ui/` is the markup: a button, a modal, an SVG, a legend and a tooltip.
 *
 * `buildSeries` is re-exported on purpose. It is the one place that decides what
 * a chart point IS, so a test on the page can check what the chart will say
 * without mounting anything.
 *
 * The feature owns its `open` flag, so the page passes data and gets a button.
 * It makes NO network request: the grades are already in memory on the page
 * (the same rule ADR-0041 set for the export).
 */

export { GradeChartButton } from "./ui/GradeChartButton.tsx";
export { buildSeries } from "./chart/series.ts";
export type { Translate } from "./chart/series.ts";
export type {
  AxisTick,
  ChartPoint,
  ChartSeries,
  ChartSource,
} from "./chart/types.ts";