/**
 * The chart's legend — and it is not decoration (ADR-0042).
 *
 * A double axis without a legend is read wrong: the reader sees two scales and
 * has no way to tell which one the bars belong to. Three labels, each with the
 * mark it names, and the marks differ in SHAPE (a square, a line, a dashed
 * line) so the legend still works for a reader who cannot tell the colours
 * apart.
 */

import { useI18n } from "../../../shared/i18n/index.ts";

export function ChartLegend() {
  const { t } = useI18n();
  return (
    <ul className="grade-chart-legend">
      <li className="grade-chart-legend-item">
        <span className="grade-chart-legend-mark grade-chart-legend-bars" />
        {t("grades.chart.legend.points")}
      </li>
      <li className="grade-chart-legend-item">
        <span className="grade-chart-legend-mark grade-chart-legend-line" />
        {t("grades.chart.legend.percent")}
      </li>
      <li className="grade-chart-legend-item">
        <span className="grade-chart-legend-mark grade-chart-legend-average" />
        {t("grades.chart.legend.average")}
      </li>
    </ul>
  );
}