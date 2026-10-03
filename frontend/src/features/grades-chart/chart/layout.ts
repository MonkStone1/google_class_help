/**
 * The chart's geometry, in one file (ADR-0042).
 *
 * Every number the drawing depends on is here, so "why is this 44" has one
 * answer instead of one per component. The values are `viewBox` units, not
 * pixels: the SVG scales to whatever width the modal gives it, which is what
 * keeps the feature free of DOM measurement.
 *
 * There is ONE axis and it is the grade axis: the chart is a trend of marks on
 * a 12-point scale, so a second scale for raw points would have been a second
 * claim about the same series, not a second fact.
 */

/** `viewBox` width. Together with the height it gives a 2:1 plot. */
export const CHART_WIDTH = 640;
/** `viewBox` height. */
export const CHART_HEIGHT = 320;

/** Space above the plot area for the topmost tick label. */
export const PAD_TOP = 16;
/** Space below it: enough for the date labels. */
export const PAD_BOTTOM = 48;
/** Left inset — the only axis there is, and it is labelled. */
export const PAD_LEFT = 44;
/** Right inset: the line ends inside the plot, this is breathing room. */
export const PAD_RIGHT = 24;

/** Plot area: the rectangle the axis and the line are drawn inside. */
export const PLOT_TOP = PAD_TOP;
export const PLOT_BOTTOM = CHART_HEIGHT - PAD_BOTTOM;
export const PLOT_LEFT = PAD_LEFT;
export const PLOT_RIGHT = CHART_WIDTH - PAD_RIGHT;
export const PLOT_HEIGHT = PLOT_BOTTOM - PLOT_TOP;
export const PLOT_WIDTH = PLOT_RIGHT - PLOT_LEFT;

/**
 * The scale, in marks: 1 is the lowest mark a teacher gives and 12 the highest.
 * Both ends are real grades, so the axis starts at 1 and not at 0 — a line
 * pinned to zero would be read as "somebody scored nothing", which on a 12-point
 * scale is not what 0 means.
 */
export const GRADE_MIN = 1;
export const GRADE_MAX = 12;
/** One label and one gridline per mark, because the reader counts in marks. */
export const TICK_COUNT = GRADE_MAX - GRADE_MIN + 1;
/** Below this the chart says nothing, so the button is disabled. */
export const MIN_CHART_POINTS = 2;
/** A course with 60 assignments would write 60 dates into 570px. */
export const MAX_X_LABELS = 10;
/** Radius of a point on the line, and the half-width of its hit area. */
export const POINT_RADIUS = 3.5;
export const HIT_RADIUS = 10;