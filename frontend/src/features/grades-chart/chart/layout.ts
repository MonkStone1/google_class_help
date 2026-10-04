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
export const CHART_HEIGHT = 488;

/**
 * Space above the plot, and it holds THREE rows: the axis title, the topmost tick
 * label, AND the tallest tooltip.
 *
 * The tooltip is the reason this is generous. A tooltip hangs a fixed distance
 * above its dot, so over the top of the scale — the highest dot there is — it
 * would hang clear over the top edge of the frame. Sizing the inset for the
 * tallest tooltip is what lets the anchor stay simple ("above my own dot")
 * without a flip rule for the top of the chart.
 */
export const PAD_TOP = 82;
/** Space below it: the date labels AND the "Date" axis title under them. */
export const PAD_BOTTOM = 64;
/**
 * Left inset, sized for the tick NUMBERS only.
 *
 * The axis title no longer has to fit here: it sits in the column above the
 * numbers with breathing room, so the widest thing on the left is a two-digit
 * mark.
 *
 * It is deliberately LARGER than a two-digit number needs. The first point sits
 * at the centre of the first band, and a band shrinks with the number of
 * assignments: on a course with 60 graded works the band is 14 units wide, which
 * puts the point's 20-unit-wide hit circle across the axis line and past the
 * frame. The inset is sized so that the tightest realistic case — a long course —
 * still keeps the whole point inside the plot.
 */
export const PAD_LEFT = 96;
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

/**
 * How far a hover tooltip floats ABOVE its dot, in `viewBox` units.
 *
 * Mirrored by the `transform` on `.grade-chart-tooltip` in `pages/grades.css`.
 * It is a constant rather than a bare number in both places because the top of
 * the chart depends on it: {@link PAD_TOP} is sized to hold a tooltip standing
 * on the highest dot, and a change here has to be seen there.
 */
export const TOOLTIP_HOVER_OFFSET = 14;
/** Tallest a tooltip gets: three rows of text plus its own padding. */
export const TOOLTIP_HEIGHT = 56;

/** Plot area: the rectangle the axis and the line are drawn inside. */
export const PLOT_TOP = PAD_TOP;
export const PLOT_BOTTOM = CHART_HEIGHT - PAD_BOTTOM;
export const PLOT_LEFT = PAD_LEFT;
export const PLOT_RIGHT = CHART_WIDTH - PAD_RIGHT;
export const PLOT_HEIGHT = PLOT_BOTTOM - PLOT_TOP;
export const PLOT_WIDTH = PLOT_RIGHT - PLOT_LEFT;

/**
 * Below this the chart says nothing, so the button is disabled: one graded work
 * is a number, not a trend.
 */
export const MIN_CHART_POINTS = 2;
/** A course with 60 assignments would write 60 dates into 570px. */
export const MAX_X_LABELS = 10;
/**
 * How many intervals the score axis aims for. Seven is the ceiling: past that
 * the labels crowd each other on a narrow window and neither the count nor the
 * grid is readable any more.
 */
export const MAX_TICKS = 7;
/**
 * The steps an axis is allowed to use, coarsest last.
 *
 * Only whole numbers a reader can count by, and only steps that divide both
 * supported scales: 12 divides by 1 and 2, 100 by 1/2/4/5/10/20/25/50. Anything
 * else would print 16.7 on the axis — see `tickStep`.
 */
export const TICK_STEPS: readonly number[] = [1, 2, 4, 5, 10, 20, 25, 50];
/** Radius of a point on the line, and the half-width of its hit area. */
export const POINT_RADIUS = 3.5;
export const HIT_RADIUS = 10;