/**
 * The chart: one line, one axis, dates underneath (ADR-0042).
 *
 * Hand-drawn on purpose. Four primitives (`line`, `polyline`, `circle`, `text`)
 * are cheaper than any charting library, and — the reason that decided it —
 * they render in jsdom, so every assertion about this file is about real markup
 * rather than about a mocked canvas or a mocked `ResizeObserver`.
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
  AXIS_TICK_GAP,
  AXIS_TITLE_GAP,
  CHART_HEIGHT,
  CHART_WIDTH,
  HIT_RADIUS,
  MAX_X_LABELS,
  PAD_TOP,
  PLOT_BOTTOM,
  PLOT_LEFT,
  PLOT_RIGHT,
  POINT_RADIUS,
} from "../chart/layout.ts";
import { bandCenter, formatTick, yScale } from "../chart/scales.ts";
import type { ChartSeries } from "../chart/types.ts";
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

  const { points, ticks, xLabels } = series;
  const count = points.length;
  const stride = Math.max(1, Math.ceil(count / MAX_X_LABELS));

  // The polyline joins only the points that HAVE a mark, so a gap is drawn as a
  // gap rather than bridged — a bridged gap would claim a trend the data does
  // not show.
  const linePath = points
    .map((point, index) =>
      point.grade === null
        ? null
        : `${bandCenter(index, count).toFixed(1)},${yScale(point.grade).toFixed(1)}`,
    )
    .filter((pair): pair is string => pair !== null)
    .join(" ");

  return (
    <div className="grade-chart">
      <div className="grade-chart-plot">
        <svg
          viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
          preserveAspectRatio="xMidYMid meet"
          className="grade-chart-svg"
          role="img"
          aria-label={t("grades.chart.ariaLabel", { course: courseName })}
        >
          {/* The grid IS the scale: one line per mark, 1 at the bottom up to 12. */}
          {ticks.map((tick) => (
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
            y1={PAD_TOP}
            y2={PLOT_BOTTOM}
          />
          <line
            className="grade-chart-axis"
            x1={PLOT_LEFT}
            x2={PLOT_RIGHT}
            y1={PLOT_BOTTOM}
            y2={PLOT_BOTTOM}
          />
          {ticks.map((tick) => (
            <text
              key={`tick-${tick.value}`}
              className="grade-chart-tick"
              x={PLOT_LEFT - AXIS_TICK_GAP}
              y={tick.y}
              textAnchor="end"
              dominantBaseline="middle"
            >
              {formatTick(tick.value)}
            </text>
          ))}
          {linePath ? (
            <polyline className="grade-chart-line" points={linePath} />
          ) : null}
{/* The dots — and, over each, the only focusable part of the picture. A 3.5px
              circle is not a keyboard target, so an invisible one the size of a
              fingertip sits on top of it. */}
          {points.map((point, index) =>
            point.grade === null ? null : (
              <g key={`dot-${point.key}`}>
                <circle
                  className="grade-chart-dot"
                  cx={bandCenter(index, count)}
                  cy={yScale(point.grade)}
                  r={POINT_RADIUS}
                />
                <circle
                  className="grade-chart-hit"
                  cx={bandCenter(index, count)}
                  cy={yScale(point.grade)}
                  r={HIT_RADIUS}
                  tabIndex={0}
                  role="button"
                  aria-label={`${point.title} — ${point.grade}`}
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
          {/* The two axis titles. The mark title sits on its OWN row well above the
              topmost tick: sharing a line with a number is what made it look
              stuck to the scale. `AXIS_TITLE_GAP` is the space between them. */}
          <text
            className="grade-chart-axis-title"
            x={PLOT_LEFT - AXIS_TICK_GAP}
            y={PAD_TOP - AXIS_TITLE_GAP}
            textAnchor="end"
          >
            {t("grades.chart.axis.grade")}
          </text>
          <text
            className="grade-chart-axis-title"
            x={(PLOT_LEFT + PLOT_RIGHT) / 2}
            y={CHART_HEIGHT - 12}
            textAnchor="middle"
          >
            {t("grades.chart.axis.date")}
          </text>
          {xLabels.map((label, index) =>
            index % stride === 0 || index === count - 1 ? (
              <text
                key={`x-${index}`}
                className="grade-chart-tick"
                x={label.x}
                y={PLOT_BOTTOM + 24}
                // The first and last dates are anchored INWARD, so a wide date
                // can never hang over the frame — which is the thing that makes
                // a chart look cramped even when nothing actually overlaps.
                textAnchor={
                  index === 0
                    ? "start"
                    : index === count - 1
                      ? "end"
                      : "middle"
                }
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
          <ChartTooltip point={points[active]} x={bandCenter(active, count)} />
        )}
      </div>

      {/* The exact numbers. A chart a screen reader walks through as anonymous
          SVG elements says nothing about the grades, and the line answers "how
          well" only to the nearest mark — so the table states it outright. */}
      <table className="sr-only">
        <caption>{t("grades.chart.table.caption")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("grades.chart.table.task")}</th>
            <th scope="col">{t("grades.chart.table.date")}</th>
            <th scope="col">{t("grades.chart.table.grade")}</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.key}>
              <th scope="row">{point.title}</th>
              <td>{point.label}</td>
              <td>
                {point.grade === null
                  ? "—"
                  : t("grades.chart.table.gradeValue", {
                      grade: point.grade,
                      points: point.points ?? "—",
                      max: point.maxPoints ?? "—",
                    })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}