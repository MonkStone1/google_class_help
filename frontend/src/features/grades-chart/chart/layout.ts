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
/** `viewBox` height. Grown with {@link PAD_TOP} so the plot itself stays tall. */
export const CHART_HEIGHT = 436;

/**
 * Space above the plot, and it holds TWO rows: the axis title and, under it,
 * the topmost tick label. It has to fit both plus a real gap, because stacking
 * an 11px word directly on top of an 11px number is what makes a chart read as
 * crowded even when nothing technically overlaps.
 */
export const PAD_TOP = 44;
/** Space below it: the date labels AND the "Date" axis title under them. */
export const PAD_BOTTOM = 64;
/**
 * Left inset, sized for the tick NUMBERS only.
 *
 * The axis title no longer has to fit here: it sits in the column above the
 * numbers with breathing room, so the widest thing on the left is a two-digit
 * mark, and the inset can go back to what that actually needs.
 */
export const PAD_LEFT = 64;
/**
 * Right inset: the line stops here instead of at the frame edge, which is what
 * stops the last point from looking pinned to the border.
 */
export const PAD_RIGHT = 48;

/**
 * Gap between a tick NUMBER and the axis it belongs to.
 *
 * Every tick label hangs off this one distance, so the axis reads as a column
 * rather than as numbers floating at different distances from the line.
 */
export const AXIS_TICK_GAP = 12;
/**
 * Vertical distance from the plot's top edge up to the axis TITLE.
 *
 * This is the gap that fixes "Оценка" looking welded to the scale: the title
 * needs roughly its own line height PLUS this much space before the first tick
 * label, otherwise the two 11px texts stack into one crowded line.
 */
export const AXIS_TITLE_GAP = 30;

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