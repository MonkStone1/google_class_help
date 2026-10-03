/**
 * The chart itself: two axes, a grid, bars, a line and the numbers behind them
 * (ADR-0042).
 *
 * Hand-drawn on purpose. Six primitives (`rect`, `line`, `polyline`, `circle`,
 * `text`) are cheaper than any charting library, and — the reason that decided
 * it — they render in jsdom, so every assertion about this file is about real
 * markup rather than about a mocked canvas or a mocked `ResizeObserver`.
 *
 * Nothing here measures the DOM. The `viewBox` is fixed and the SVG scales to
 * its container, so the coordinates `buildSeries` computed are the coordinates
 * that get drawn, at any window width and in any test.
 *
 * Colour comes from CSS classes, never from attributes: `stroke="var(--accent)"`
 * in an attribute does not resolve, while a class does, and the dark theme then
 * switches by itself (ADR-0005).
 */

import { useState } from "react";

import { useI18n } from "../../../shared/i18n/index.ts";
import {
  BAR_WIDTH_RATIO,
  CHART_HEIGHT,
  CHART_WIDTH,
  HIT_RADIUS,
  MAX_X_LABELS,
  PAD_LEFT,
  PAD_RIGHT,
  PAD_TOP,
  PLOT_BOTTOM,
  PLOT_LEFT,
  PLOT_RIGHT,
  PLOT_TOP,
  POINT_RADIUS,
} from "../chart/layout.ts";
import {
  PERCENT_MAX,
  bandCenter,
  bandWidth,
  formatTick,
  yScale,
} from "../chart/scales.ts";
import type { ChartSeries } from "../chart/types.ts";
import { ChartLegend } from "./ChartLegend.tsx";
import { ChartTooltip } from "./ChartTooltip.tsx";

type Props = {
  series: ChartSeries;
  courseName: string;
};

export function GradeChartSvg({ series, courseName }: Props) {
  const { t } = useI18n();
  // Which dot the pointer or the keyboard is on. Local state, not a prop: the
  // page has no reason to know, and the modal owns nothing else either.
  const [active, setActive] = useState<number | null>(null);

  const { points, leftTicks, rightTicks, xLabels, averageY } = series;
  const count = points.length;
  const barWidth = bandWidth(count) * BAR_WIDTH_RATIO;
  const stride = Math.max(1, Math.ceil(count / MAX_X_LABELS));
  const rightMax = rightTicks[rightTicks.length - 1]?.value ?? 1;

  // The polyline joins only the points that HAVE a percent, so a gap is drawn
  // as a gap rather than bridged — a bridged gap would claim a trend the data
  // does not show.
  const linePath = points
    .map((point, index) =>
      point.percent === null
        ? null
        : `${bandCenter(index, count).toFixed(1)},${yScale(
            point.percent,
            PERCENT_MAX,
          ).toFixed(1)}`,
    )
    .filter((pair): pair is string => pair !== null)
    .join(" ");

  return (
    <div className="grade-chart">
      <ChartLegend />
      <div className="grade-chart-plot">
        <svg
          viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
          preserveAspectRatio="xMidYMid meet"
          className="grade-chart-svg"
          role="img"
          aria-label={t("grades.chart.ariaLabel", { course: courseName })}
        >
          {leftTicks.map((tick) => (
            <line
              key={`grid-${tick.value}`}
              className="grade-chart-grid"
              x1={PLOT_LEFT}
              x2={PLOT_RIGHT}
              y1={tick.y}
              y2={tick.y}
            />
          ))}
          <line
            className="grade-chart-axis"
            x1={PLOT_LEFT}
            x2={PLOT_LEFT}
            y1={PLOT_TOP}
            y2={PLOT_BOTTOM}
          />
          <line
            className="grade-chart-axis"
            x1={PLOT_RIGHT}
            x2={PLOT_RIGHT}
            y1={PLOT_TOP}
            y2={PLOT_BOTTOM}
          />
          {leftTicks.map((tick) => (
            <text
              key={`left-${tick.value}`}
              className="grade-chart-tick"
              x={PLOT_LEFT - 8}
              y={tick.y}
              textAnchor="end"
              dominantBaseline="middle"
            >
              {formatTick(tick.value)}
            </text>
          ))}
          {rightTicks.map((tick) => (
            <text
              key={`right-${tick.value}`}
              className="grade-chart-tick"
              x={PLOT_RIGHT + 8}
              y={tick.y}
              textAnchor="start"
              dominantBaseline="middle"
            >
              {formatTick(tick.value)}
            </text>
          ))}
        {/* The bars, on the RIGHT axis --------------------------------------- */}
          {points.map((point, index) =>
            point.points === null ? null : (
              <rect
                key={`bar-${point.key}`}
                className="grade-chart-bar"
                x={bandCenter(index, count) - barWidth / 2}
                y={yScale(point.points, rightMax)}
                width={barWidth}
                height={PLOT_BOTTOM - yScale(point.points, rightMax)}
              />
            ),
          )}

          {/* The course average, on the LEFT axis, dashed ---------------------- */}
          {averageY === null ? null : (
            <line
              className="grade-chart-average"
              x1={PLOT_LEFT}
              x2={PLOT_RIGHT}
              y1={averageY}
              y2={averageY}
              strokeDasharray="5 4"
            />
          )}

          {/* The score line, on the LEFT axis --------------------------------- */}
          {linePath ? (
            <polyline className="grade-chart-line" points={linePath} />
          ) : null}

          {/* The dots — and, over each, the only focusable part of the picture.
              A 3.5px circle is not a keyboard target, so an invisible one the
              size of a fingertip sits on top of it. */}
          {points.map((point, index) =>
            point.percent === null ? null : (
              <g key={`dot-${point.key}`}>
                <circle
                  className="grade-chart-dot"
                  cx={bandCenter(index, count)}
                  cy={yScale(point.percent, PERCENT_MAX)}
                  r={POINT_RADIUS}
                />
                <circle
                  className="grade-chart-hit"
                  cx={bandCenter(index, count)}
                  cy={yScale(point.percent, PERCENT_MAX)}
                  r={HIT_RADIUS}
                  tabIndex={0}
                  role="button"
                  aria-label={`${point.title} — ${point.percent}%`}
                  onMouseEnter={() => setActive(index)}
                  onMouseLeave={() => setActive(null)}
                  onFocus={() => setActive(index)}
                  onBlur={() => setActive(null)}
                >
                  <title>{point.title}</title>
                </circle>
              </g>
            ),
          )}

          {/* Axis titles and category labels ----------------------------------- */}
          <text
            className="grade-chart-axis-title"
            x={PAD_LEFT - 8}
            y={PAD_TOP - 6}
            textAnchor="end"
          >
            {t("grades.chart.axis.percent")}
          </text>
          <text
            className="grade-chart-axis-title"
            x={CHART_WIDTH - PAD_RIGHT + 8}
            y={PAD_TOP - 6}
            textAnchor="start"
          >
            {t("grades.chart.axis.points")}
          </text>
          <text
            className="grade-chart-axis-title"
            x={(PLOT_LEFT + PLOT_RIGHT) / 2}
            y={CHART_HEIGHT - 8}
            textAnchor="middle"
          >
            {t("grades.chart.axis.task")}
          </text>
          {xLabels.map((label, index) =>
            index % stride === 0 || index === count - 1 ? (
              <text
                key={`x-${index}`}
                className="grade-chart-tick"
                x={label.x}
                y={PLOT_BOTTOM + 20}
                textAnchor="middle"
              >
                {label.text}
              </text>
            ) : null,
          )}
        </svg>

        {/* The tooltip is HTML next to the SVG, not inside it: an HTML element
            inside SVG is a `foreignObject`, which jsdom does not lay out and a
            screen reader treats inconsistently. */}
        {active === null ? null : (
          <ChartTooltip
            point={points[active]}
            x={bandCenter(active, count)}
          />
        )}
      </div>

      {/* The exact numbers. A chart a screen reader walks through as anonymous
          SVG elements says nothing about the grades, and the bars answer "how
          much" only approximately — so the table states it outright. */}
      <table className="sr-only">
        <caption>{t("grades.chart.table.caption")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("grades.chart.table.task")}</th>
            <th scope="col">{t("grades.chart.table.points")}</th>
            <th scope="col">{t("grades.chart.table.percent")}</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.key}>
              <th scope="row">{point.title}</th>
              <td>
                {point.points === null ? "—" : point.points} /{" "}
                {point.maxPoints === null ? "—" : point.maxPoints}
              </td>
              <td>{point.percent === null ? "—" : `${point.percent}%`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}