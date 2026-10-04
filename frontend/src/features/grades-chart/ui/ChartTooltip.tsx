/**
 * What one point is worth, shown right above the dot the reader is on (ADR-0042).
 *
 * HTML rather than SVG text: it can be styled and read normally, and it does not
 * need a `foreignObject` — which jsdom does not lay out and screen readers treat
 * inconsistently.
 *
 * The position is COMPUTED, not measured: `x` and `y` arrive as `viewBox`
 * coordinates and become percentages of the WHOLE frame, so the tooltip sits
 * over its own dot at any window width without the feature ever reading the DOM.
 *
 * Both percentages are of `CHART_WIDTH` / `CHART_HEIGHT` and not of the plot
 * area: the element is positioned inside `.grade-chart-plot`, which spans the
 * whole SVG including its padding, so a percentage of the plot area would land
 * short of the dot by exactly the padding.
 */

import { useI18n } from "../../../shared/i18n/index.ts";
import { CHART_HEIGHT, CHART_WIDTH } from "../chart/layout.ts";
import type { ChartPoint } from "../chart/types.ts";

type Props = {
  point: ChartPoint;
  /** Centre of the point's band, in `viewBox` units. */
  x: number;
  /** The dot's height, in `viewBox` units. */
  y: number;
};

export function ChartTooltip({ point, x, y }: Props) {
  const { t } = useI18n();

  // Clamped to the FRAME, not to the plot: a dot near the first or the last
  // band sits inside the padding, and a tooltip centred on it would otherwise
  // hang over the edge of the modal. The clamp keeps it on screen while leaving
  // it as close to its own dot as that allows.
  const left = Math.min(CHART_WIDTH, Math.max(0, (x / CHART_WIDTH) * 100));
  const top = Math.min(CHART_HEIGHT, Math.max(0, (y / CHART_HEIGHT) * 100));

  return (
    <div
      className="grade-chart-tooltip"
      style={{ left: `${left}%`, top: `${top}%` }}
      role="status"
    >
      <span className="grade-chart-tooltip-title">{point.title}</span>
      <span className="grade-chart-tooltip-row">
        {t("grades.chart.tooltip.score", { score: point.score ?? "—" })}
      </span>
      {point.maxPoints === null ? null : (
        <span className="grade-chart-tooltip-row">
          {t("grades.chart.tooltip.points", {
            points: point.score ?? "—",
            max: point.maxPoints,
          })}
        </span>
      )}
      <span className="grade-chart-tooltip-row">
        {point.due === null
          ? t("grades.chart.tooltip.noDue")
          : t("grades.chart.tooltip.due", { date: point.label })}
      </span>
    </div>
  );
}