/**
 * What one point is worth, shown next to the dot the reader is on (ADR-0042).
 *
 * HTML rather than SVG text: it can be styled and read normally, and it does not
 * need a `foreignObject` — which jsdom does not lay out and screen readers
 * treat inconsistently.
 *
 * The position is COMPUTED, not measured. `x` arrives as a `viewBox` coordinate
 * and is converted to a percentage of the plot, so the tooltip sits over the
 * dot at any window width without the feature ever reading the DOM.
 */

import { useI18n } from "../../../shared/i18n/index.ts";
import { PLOT_LEFT, PLOT_RIGHT } from "../chart/layout.ts";
import type { ChartPoint } from "../chart/types.ts";

type Props = {
  point: ChartPoint;
  /** Centre of the point's band, in `viewBox` units. */
  x: number;
};

export function ChartTooltip({ point, x }: Props) {
  const { t } = useI18n();
  // Clamped to the plot: at the first and the last band a tooltip centred on
  // the dot would hang off the edge of the modal.
  const left = Math.min(
    100,
    Math.max(0, ((x - PLOT_LEFT) / (PLOT_RIGHT - PLOT_LEFT)) * 100),
  );

  return (
    <div
      className="grade-chart-tooltip"
      style={{ left: `${left}%` }}
      role="status"
    >
      <span className="grade-chart-tooltip-title">{point.title}</span>
      <span className="grade-chart-tooltip-row">
        {t("grades.chart.tooltip.grade", {
          points: point.points ?? "—",
          max: point.maxPoints ?? "—",
        })}
        {point.percent === null ? "" : ` · ${point.percent}%`}
      </span>
      <span className="grade-chart-tooltip-row">
        {point.due === null
          ? t("grades.chart.tooltip.noDue")
          : t("grades.chart.tooltip.due", { date: point.label })}
      </span>
    </div>
  );
}