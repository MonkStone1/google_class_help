import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GradeChartSvg } from "./GradeChartSvg.tsx";
import {
  AXIS_TICK_GAP,
  AXIS_TITLE_GAP,
  CHART_HEIGHT,
  CHART_WIDTH,
  PAD_BOTTOM,
  PAD_TOP,
  PLOT_LEFT,
  POINT_RADIUS,
  TOOLTIP_HEIGHT,
  TOOLTIP_HOVER_OFFSET,
} from "../chart/layout.ts";
import { yScale } from "../chart/scales.ts";
import { buildSeries, type Translate } from "../chart/series.ts";
import type { ChartSource } from "../chart/types.ts";
import { en } from "../../../shared/i18n/locales/en/index.ts";
import { formatDateTimeShort, parseDue } from "../../../shared/lib/index.ts";
import { SettingsProvider } from "../../../shared/settings/index.ts";
import type { GradeItem } from "../../../shared/types/index.ts";

/**
 * The REAL English dictionary, wrapped the way `useI18n` wraps it. A hand-written
 * fake would let a key go missing from all three dictionaries and still pass
 * these assertions, which is the one thing they exist to prevent.
 */
const t: Translate = (key, vars) => {
  // Annotated as `string`: without it `en[key]` keeps its literal union, and a
  // `reduce` over that union has no single accumulator type to infer.
  const raw: string = en[key] ?? key;
  if (!vars) return raw;
  return Object.entries(vars).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    raw,
  );
};

function item(overrides: Partial<GradeItem> = {}): GradeItem {
  return {
    assignment_id: "a1",
    title: "Homework 1",
    points: 11,
    max_points: 12,
    percent: 91.7,
    graded_at: null,
    due_at: "2026-01-12T12:00:00",
    ...overrides,
  };
}

/**
 * Three works out of TWELVE, matching the default axis. The fixtures used to be
 * percentages out of 100, which on a 12-point axis put every dot at the very top
 * � a test that passed while drawing a flat line pinned to the ceiling.
 */
const THREE: GradeItem[] = [
  item({ assignment_id: "a1", title: "HW 1", points: 9, percent: 75 }),
  item({
    assignment_id: "a2",
    title: "HW 2",
    points: 11,
    percent: 91.7,
    due_at: "2026-02-02T12:00:00",
  }),
  item({
    assignment_id: "a3",
    title: "HW 3",
    points: 7,
    percent: 58.3,
    due_at: "2026-03-05T12:00:00",
  }),
];

function source(overrides: Partial<ChartSource> = {}): ChartSource {
  return {
    courseId: "c1",
    courseName: "Algebra",
    average: 80,
    items: THREE,
    ...overrides,
  };
}

/** English is pinned: the assertions below read the English labels. */
function pinEnglish(): void {
  localStorage.setItem(
    "gc-settings",
    JSON.stringify({ language: "en", theme: "light" }),
  );
}

function draw(current: ChartSource) {
  const series = buildSeries(current, t, 12);
  if (!series) throw new Error("the fixture must produce a chart");
  return (
    <SettingsProvider>
      <GradeChartSvg series={series} courseName={current.courseName} />
    </SettingsProvider>
  );
}

function renderChart(overrides: Partial<ChartSource> = {}) {
  pinEnglish();
  return render(draw(source(overrides)));
}

/** Every `<text>` in the picture, which is all of the axis wording. */
function svgTexts(container: HTMLElement): Array<string | null> {
  return [...container.querySelectorAll("svg text")].map((node) => node.textContent);
}

describe("the chart picture", () => {
  it("labels ONE axis, from 0 up to the scale", () => {
    const { container } = renderChart();

    // The whole axis, start to finish: 12 is the top of the 12-point scale and 0
    // the floor, and nothing between them is skipped.
    const texts = svgTexts(container);
    for (const tick of [0, 2, 4, 6, 8, 10, 12]) {
      expect(texts.filter((text) => text === String(tick))).toHaveLength(1);
    }
    expect(texts).toContain("Points");
    expect(texts).toContain("Date");
    // No percentages anywhere on the picture: the axis counts the points
    // Classroom stores, and 87 % of what is not in the data.
    expect(texts).not.toContain("87%");
  });

  it("draws no bars at all, only the line and its dots", () => {
    const { container } = renderChart();

    // A `<rect>` per assignment would have been the same grades drawn a second
    // time on a second scale.
    expect(container.querySelector("rect")).toBeNull();
    expect(container.querySelectorAll("circle.grade-chart-dot")).toHaveLength(3);
    expect(container.querySelector("polyline.grade-chart-line")).toBeTruthy();
  });

  it("draws no average line and no legend", () => {
    const { container } = renderChart();

    expect(container.querySelector("line.grade-chart-average")).toBeNull();
    expect(container.querySelector(".grade-chart-legend")).toBeNull();
  });

  it("joins the line through exactly the points that have a mark", () => {
    const { container } = renderChart();

    const polyline = container.querySelector("polyline.grade-chart-line");
    expect(polyline).toBeTruthy();
    const pairs = (polyline?.getAttribute("points") ?? "").trim().split(/\s+/);
    expect(pairs).toHaveLength(3);
    // "x,y" PAIRS: a polyline given one number per vertex connects nothing.
    for (const pair of pairs) {
      expect(pair).toMatch(/^-?\d+(\.\d+)?,-?\d+(\.\d+)?$/);
    }
  });

  it("skips a point that has no score instead of dropping it to zero", () => {
    pinEnglish();
    const { container } = renderChart({
      items: [
        ...THREE,
        item({ assignment_id: "a4", points: null, percent: null }),
      ],
    });

    // Three dots for four assignments: an ungraded work has no score, and a dot
    // on the floor would claim the teacher awarded nothing.
    expect(container.querySelectorAll("circle.grade-chart-dot")).toHaveLength(3);
    const pairs = (
      container.querySelector("polyline.grade-chart-line")?.getAttribute("points") ??
      ""
    )
      .trim()
      .split(/\s+/);
    expect(pairs).toHaveLength(3);
  });

  it("names the picture for a screen reader", () => {
    renderChart();

    // Without this the SVG is walked through as a pile of anonymous shapes,
    // which is exactly what the sparkline it replaced did.
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe(
      "Grade trend for Algebra",
    );
  });

  it("writes a formatted date under every point", () => {
    pinEnglish();
    const { container } = renderChart();

    // Compared against the formatter itself rather than against a literal:
    // `formatDateTimeShort` drops the year for the current one, so a hard-coded
    // "Jan 2026" would break in January and pass in February.
    const texts = svgTexts(container);
    for (const date of ["2026-01-12", "2026-02-02", "2026-03-05"]) {
      expect(texts).toContain(
        formatDateTimeShort(parseDue(`${date}T12:00:00`)),
      );
    }
  });

  it("numbers a category that has no deadline instead of leaving it blank", () => {
    pinEnglish();
    const { container } = renderChart({
      average: null,
      items: [
        item({ assignment_id: "a1", due_at: null }),
        item({ assignment_id: "a2", due_at: null }),
      ],
    });

    const texts = svgTexts(container);
    expect(texts).toContain("#1");
    expect(texts).toContain("#2");
  });

  it("keeps the axis title on its own row, clear of the tick numbers", () => {
    const { container } = renderChart();

    // The bug this guards: "������" used to sit ~6 units above the "12" label,
    // so the two 11px texts read as one crowded line stuck to the scale.
    const title = container.querySelector("text.grade-chart-axis-title");
    const topTick = container.querySelector("text.grade-chart-tick");
    expect(title).toBeTruthy();
    expect(topTick).toBeTruthy();

    const titleY = Number(title?.getAttribute("y"));
    const tickY = Number(topTick?.getAttribute("y"));
    // A full line height plus a real margin between the two baselines.
    expect(tickY - titleY).toBeGreaterThanOrEqual(AXIS_TITLE_GAP);
    // And the title must stay INSIDE the frame, above the top of the plot.
    expect(titleY).toBeGreaterThan(0);
    expect(titleY).toBeLessThan(PAD_TOP);
  });

  it("hangs every tick number off the axis at the same distance", () => {
    const { container } = renderChart();

    // One column: the NUMBERS must line up with each other and with the title,
    // not drift toward and away from the line at different distances. The date
    // labels share the class but sit on their own X positions, so they are
    // picked out by the vertical gap � a tick is centred on a gridline, a date
    // is not.
    const axisLabels = [
      ...container.querySelectorAll("text.grade-chart-tick"),
    ].filter((node) => {
      const y = Number(node.getAttribute("y"));
      return y >= PAD_TOP && y <= PAD_TOP + (CHART_HEIGHT - PAD_TOP - PAD_BOTTOM);
    });
    // Seven ticks on a 12-point axis (0…12, stepping by 2). The count is not
    // hardcoded in the assertion on purpose: `scaleTicks` decides it, and this
    // test is about their ALIGNMENT, not about how many there are.
    expect(axisLabels.length).toBeGreaterThan(1);

    const titleX = container
      .querySelector("text.grade-chart-axis-title")
      ?.getAttribute("x");
    for (const node of axisLabels) {
      expect(node.getAttribute("x")).toBe(String(PLOT_LEFT - AXIS_TICK_GAP));
    }
    expect(titleX).toBe(String(PLOT_LEFT - AXIS_TICK_GAP));
  });

  it("anchors the first and last dates inward, so neither hangs over the frame", () => {
    pinEnglish();
    const { container } = renderChart();

    // A centred date at the very first band would stick out past the left edge,
    // and that is what makes a chart look cramped even with no real overlap.
    const dated = [...container.querySelectorAll("svg text.grade-chart-tick")].map(
      (node) => node.getAttribute("text-anchor"),
    );
    expect(dated).toContain("start");
    expect(dated).toContain("end");
  });

  it("puts the tooltip over ITS OWN dot, not at the top of the frame", () => {
    pinEnglish();
    const { container } = renderChart();

    const hits = container.querySelectorAll("circle.grade-chart-hit");
    const dots = container.querySelectorAll("circle.grade-chart-dot");

    // The bug this guards: the tooltip used to be pinned with `bottom: 100%`,
    // which parked it against the TOP of the plot whatever dot you were on.
    const tops: number[] = [];
    for (const index of [0, 1, 2]) {
      fireEvent.mouseEnter(hits[index]);
      tops.push(Number.parseFloat(screen.getByRole("status").style.top));
      fireEvent.mouseLeave(hits[index]);
    }

    // Every dot gets its OWN height � two identical percentages would mean the
    // tooltip is pinned to the frame rather than following the point.
    expect(new Set(tops).size).toBe(THREE.length);
    // And each one matches its dot's Y exactly.
    for (const index of [0, 1, 2]) {
      const cy = Number(dots[index].getAttribute("cy"));
      expect(tops[index]).toBeCloseTo((cy / CHART_HEIGHT) * 100, 6);
    }
  });

  it("leaves room above the plot for a tooltip over the highest mark", () => {
    // The tooltip hangs above its own dot, so over mark 12 it would hang over
    // the top edge unless PAD_TOP is sized for it. This is the check that keeps
    // the anchor simple: no flip rule, just enough headroom.
    const tallest = yScale(12, 12);
    // The VISIBLE dot is what the tooltip must clear, not the 10-unit hit circle
    // underneath it: the box floats just above the mark the reader can see.
    const tooltipTop = tallest - POINT_RADIUS - TOOLTIP_HOVER_OFFSET - TOOLTIP_HEIGHT;
    expect(tooltipTop).toBeGreaterThanOrEqual(0);
    // And the plot itself must not have shrunk to pay for it.
    expect(PAD_TOP).toBeGreaterThanOrEqual(TOOLTIP_HEIGHT);
});

it("keeps a tooltip at the frame edge inside the frame", () => {
    pinEnglish();
    const { container } = renderChart();

    const hits = container.querySelectorAll("circle.grade-chart-hit");
    // The first dot is the leftmost, so its tooltip is the one at risk of
    // hanging over the modal's edge.
    fireEvent.mouseEnter(hits[0]);

    const left = Number.parseFloat(screen.getByRole("status").style.left);
    const dotX = Number(hits[0].getAttribute("cx"));
    expect(Number.isFinite(left)).toBe(true);
    expect(left).toBeGreaterThanOrEqual(0);
    expect(left).toBeLessThanOrEqual(100);
    // A percentage of the FRAME, not of the plot area: these differ by exactly
    // the left padding, so getting it wrong shifts the tooltip off its dot.
    expect(left).toBeCloseTo((dotX / CHART_WIDTH) * 100, 6);
  });

  it("states every mark in a table a screen reader can walk", () => {
    renderChart();

    // The line answers "how well" only to the nearest pixel; the table gives the
    // exact score, and the maximum it was out of.
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(THREE.length + 1);
    expect(rows[2]).toHaveTextContent("HW 2");
    expect(rows[2]).toHaveTextContent("11 / 12");
  });

  it("shows a dot's numbers on hover AND on keyboard focus", () => {
    pinEnglish();
    const { container } = renderChart();

    const hits = container.querySelectorAll("circle.grade-chart-hit");
    expect(hits).toHaveLength(THREE.length);
    expect(screen.queryByRole("status")).toBeNull();

    // Keyboard FIRST: a tooltip reachable only by hovering is unreachable for
    // anyone driving the chart with Tab.
    fireEvent.focus(hits[1]);
    expect(screen.getByRole("status")).toHaveTextContent("HW 2");
    fireEvent.blur(hits[1]);
    expect(screen.queryByRole("status")).toBeNull();

    fireEvent.mouseEnter(hits[1]);
    expect(screen.getByRole("status")).toHaveTextContent("11 / 12");
    fireEvent.mouseLeave(hits[1]);
    expect(screen.queryByRole("status")).toBeNull();
  });
});