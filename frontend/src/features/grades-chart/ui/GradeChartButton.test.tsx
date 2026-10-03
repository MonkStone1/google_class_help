import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GradeChartButton } from "./GradeChartButton.tsx";
import { SettingsProvider } from "../../../shared/settings/index.ts";
import type { GradeItem } from "../../../shared/types/index.ts";

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

const TWO: GradeItem[] = [
  item({ assignment_id: "a1", title: "HW 1" }),
  item({
    assignment_id: "a2",
    title: "HW 2",
    points: 70,
    percent: 70,
    due_at: "2026-02-02T12:00:00",
  }),
];

/** English is pinned: the assertions read the English labels. */
function pinEnglish(): void {
  localStorage.setItem(
    "gc-settings",
    JSON.stringify({ language: "en", theme: "light" }),
  );
}

function renderButton(items: GradeItem[] = TWO) {
  pinEnglish();
  return render(
    <SettingsProvider>
      <GradeChartButton
        courseId="c1"
        courseName="Algebra"
        average={80}
        items={items}
      />
    </SettingsProvider>,
  );
}

function openButton() {
  fireEvent.click(screen.getByRole("button", { name: "Chart" }));
}

describe("the chart button on the grades page", () => {
  it("is an icon button with a name a screen reader can read", () => {
    const { container } = renderButton();

    const button = screen.getByRole("button", { name: "Chart" });
    expect(button).toBeEnabled();
    // The icon alone says nothing, and the `aria-label` is what replaces it —
    // the sparkline's "Grade history" was the only English string on a
    // three-language screen.
    expect(button.querySelector("svg")).toBeTruthy();
    expect(container.querySelector(".grade-chart-button")).toBeTruthy();
  });

  it("opens a modal labelled as a dialog", () => {
    renderButton();
    expect(screen.queryByRole("dialog")).toBeNull();

    openButton();

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName("Grade trend");
    expect(screen.getByRole("img", { name: "Grade trend for Algebra" })).toBeInTheDocument();
  });

  it("cannot be pressed at all when the course has one graded work", () => {
    // Not a button that opens onto "not enough data": a disabled button is the
    // only state a click cannot reach.
    renderButton([item()]);

    expect(screen.getByRole("button", { name: "Chart" })).toBeDisabled();
  });

  it("opens exactly one modal however many times it is pressed", () => {
    renderButton();
    // Two courses on one page means two buttons; clicking one must not stack
    // dialogs, or the page would end up with a modal behind a modal.
    openButton();
    fireEvent.click(screen.getByRole("button", { name: "Chart" }));

    expect(screen.getAllByRole("dialog")).toHaveLength(1);
  });
});