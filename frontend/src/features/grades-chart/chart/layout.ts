/**
 * The chart's geometry, in one file (ADR-0042).
 *
 * Every number the drawing depends on is here, so "why is this 52" has one
 * answer instead of one per component. The values are `viewBox` units, not
 * pixels: the SVG scales to whatever width the modal gives it, which is what
 * keeps the feature free of DOM measurement.
 */

/** `viewBox` width. Together with the height it gives a 2.25:1 plot. */
export const CHART_WIDTH = 720;
/** `viewBox` height — tall enough for five ticks and an X axis to breathe. */
export const CHART_HEIGHT = 320;

/** Space above the plot area for the highest tick label. */
export const PAD_TOP = 16;
/** Space below it: enough for the X category labels and the axis title. */
export const PAD_BOTTOM = 56;
/** Left inset — the percent axis is labelled, so it needs room. */
export const PAD_LEFT = 52;
/** Right inset, symmetric with the left one, because both axes are labelled. */
export const PAD_RIGHT = 52;

/** Plot area: the rectangle both axes and the grid are drawn inside. */
export const PLOT_TOP = PAD_TOP;
export const PLOT_BOTTOM = CHART_HEIGHT - PAD_BOTTOM;
export const PLOT_LEFT = PAD_LEFT;
export const PLOT_RIGHT = CHART_WIDTH - PAD_RIGHT;
export const PLOT_HEIGHT = PLOT_BOTTOM - PLOT_TOP;
export const PLOT_WIDTH = PLOT_RIGHT - PLOT_LEFT;

/** Five ticks means four intervals, which both axes share so the grid matches. */
export const TICK_COUNT = 5;
/** 100 / 4 — the percent step, and the granularity the points axis rounds to. */
export const TICK_STEP = 25;
/** Bar width as a fraction of the band it sits in; the rest is the gap. */
export const BAR_WIDTH_RATIO = 0.55;
/** Below this the chart says nothing, so the button is disabled. */
export const MIN_CHART_POINTS = 2;
/** A course with 60 assignments would write 60 dates into 600px. */
export const MAX_X_LABELS = 12;
/** Radius of a point on the line, and the half-width of its invisible hit area. */
export const POINT_RADIUS = 3.5;
export const HIT_RADIUS = 10;