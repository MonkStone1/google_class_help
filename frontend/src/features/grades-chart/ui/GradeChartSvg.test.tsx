import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GradeChartSvg } from "./GradeChartSvg.tsx";
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
  const raw = en[key] ?? key;
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
    points: 87,
    max_points: 100,
    percent: 87,
    graded_at: null,
    due_at: "2026-01-12T12:00:00",
    ...overrides,
  };
}

const THREE: GradeItem[] = [
  item({ assignment_id: "a1", title: "HW 1", points: 70, percent: 70 }),
  item({
    assignment_id: "a2",
    title: "HW 2",
    points: 87,
    percent: 87,
    due_at: "2026-02-02T12:00:00",
  }),
  item({
    assignment_id: "a3",
    title: "HW 3",
    points: 54,
    percent: 54,
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
  const series = buildSeries(current, t);
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
  it("labels BOTH axes with five values each", () => {
    const { container } = renderChart();

    // Five on the left and five on the right: an axis with no numbers is
    // decoration, and the two sets must be told apart by their position rather
    // than by colour.
    const texts = svgTexts(container);
    for (const value of ["0", "25", "50", "75", "100"]) {
      expect(texts.filter((text) => text === value)).toHaveLength(2);
    }
    expect(texts).toContain("Score, %");
    expect(texts).toContain("Points");
    expect(texts).toContain("Assignment");
  });

  it("draws one bar per point that has points, and none for the rest", () => {
    pinEnglish();
    const { container, rerender } = renderChart();
    expect(container.querySelectorAll("rect.grade-chart-bar")).toHaveLength(3);

    // A work with no score is a GAP, not a zero-height bar: a bar of height
    // zero claims the student scored nothing, which is a different statement.
    rerender(
      draw(
        source({
          items: [
            ...THREE,
            item({ assignment_id: "a4", points: null, percent: null }),
          ],
        }),
      ),
    );
    expect(container.querySelectorAll("rect.grade-chart-bar")).toHaveLength(3);
  });

  it("joins the score line through exactly the points that have a percent", () => {
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

  it("dashes the average line, and draws none when there is no average", () => {
    pinEnglish();
    const { container, rerender } = renderChart();

    const average = container.querySelector("line.grade-chart-average");
    expect(average?.getAttribute("stroke-dasharray")).toBeTruthy();

    rerender(draw(source({ average: null })));
    expect(container.querySelector("line.grade-chart-average")).toBeNull();
  });

  it("names the picture for a screen reader", () => {
    renderChart();

    // Without this the SVG is walked through as a pile of anonymous shapes,
    // which is exactly what the sparkline it replaced did.
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe(
      "Grade trend for Algebra",
    );
  });

  it("writes a formatted date under each category", () => {
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

  it("names all three series in the legend", () => {
    pinEnglish();
    const { container } = renderChart();

    // Not decoration: on a double axis a reader who cannot tell which scale the
    // bars belong to reads the whole chart wrong.
    expect(container.querySelectorAll(".grade-chart-legend li")).toHaveLength(3);
    expect(screen.getByText("Points earned")).toBeInTheDocument();
    expect(screen.getByText("Course average")).toBeInTheDocument();
    expect(screen.getAllByText("Score, %").length).toBeGreaterThan(0);
  });

  it("states every number in a table a screen reader can walk", () => {
    renderChart();

    // The bars answer "how much" only approximately; the table says it exactly.
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(THREE.length + 1);
    expect(rows[2]).toHaveTextContent("HW 2");
    expect(rows[2]).toHaveTextContent("87 / 100");
    expect(rows[2]).toHaveTextContent("87%");
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
    expect(screen.getByRole("status")).toHaveTextContent("87 / 100");
    fireEvent.mouseLeave(hits[1]);
    expect(screen.queryByRole("status")).toBeNull();
  });
});