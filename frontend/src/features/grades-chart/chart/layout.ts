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

/**
 * `viewBox` width. Together with the height it gives a 2.3:1 plot, which is wide
 * enough for a course's dates to have air between them.
 *
 * The size is chosen to match the modal: the CSS gives the dialog a max-width of
 * 980px, which leaves ~936px of content, so a 960-unit `viewBox` renders at
 * roughly 1:1. A much narrower `viewBox` would be scaled UP and the tick labels
 * would grow with it; a much wider one would be scaled down and they would turn
 * to dust. Every padding below is therefore also a pixel margin on screen.
 */
export const CHART_WIDTH = 960;
/** `viewBox` height. */
export const CHART_HEIGHT = 420;

/** Space above the plot: the "Mark" axis title and the topmost tick label. */
export const PAD_TOP = 28;
/** Space below it: the date labels AND the "Date" axis title under them. */
export const PAD_BOTTOM = 64;
/**
 * Left inset — the only axis there is, and it carries two labels: a tick number
 * and the axis title above it. The widest of those is "Оцінка", so the inset is
 * sized for it rather than for the number.
 */
export const PAD_LEFT = 72;
/**
 * Right inset: the line stops here instead of at the frame edge, which is what
 * stops the last point from looking pinned to the border.
 */
export const PAD_RIGHT = 48;

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