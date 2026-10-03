import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GradeChartDialog } from "./GradeChartDialog.tsx";
import { buildSeries, type Translate } from "../chart/series.ts";
import type { ChartSource } from "../chart/types.ts";
import { en } from "../../../shared/i18n/locales/en/index.ts";
import { SettingsProvider } from "../../../shared/settings/index.ts";
import type { GradeItem } from "../../../shared/types/index.ts";

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
    points: 87,
    max_points: 100,
    percent: 87,
    graded_at: null,
    due_at: "2026-01-12T12:00:00",
    ...overrides,
  };
}

function renderDialog(
  overrides: { open?: boolean; items?: GradeItem[]; average?: number | null } = {},
) {
  localStorage.setItem(
    "gc-settings",
    JSON.stringify({ language: "en", theme: "light" }),
  );
  const source: ChartSource = {
    courseId: "c1",
    courseName: "Algebra",
    average: overrides.average ?? 80,
    items: overrides.items ?? [
      item(),
      item({ assignment_id: "a2", due_at: "2026-02-02T12:00:00" }),
    ],
  };
  const onClose = vi.fn();
  return {
    onClose,
    ...render(
      <SettingsProvider>
        <GradeChartDialog
          open={overrides.open ?? true}
          source={source}
          series={buildSeries(source, t)}
          onClose={onClose}
        />
      </SettingsProvider>,
    ),
  };
}

describe("the chart modal", () => {
  it("closes on Escape", () => {
    // The listener is on `document`, so the keypress has to be fired there too:
    // a modal that only closes when the SVG itself has focus is a modal a
    // keyboard user cannot leave.
    const { onClose } = renderDialog();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes on the backdrop but not on the modal itself", () => {
    const { onClose, container } = renderDialog();

    fireEvent.click(container.querySelector(".modal-backdrop") as Element);
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(container.querySelector(".modal") as Element);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes on the cross, which has a name of its own", () => {
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("renders nothing at all while closed", () => {
    renderDialog({ open: false });

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.querySelector(".modal-backdrop")).toBeNull();
  });

  it("states the empty case instead of an empty picture", () => {
    renderDialog({ items: [item()] });

    expect(
      screen.getByText("Not enough graded work for a chart"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("img")).toBeNull();
  });
});