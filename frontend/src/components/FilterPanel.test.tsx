import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FilterPanel } from "./FilterPanel.tsx";
import { SettingsProvider } from "../context/SettingsContext.tsx";
import type { AssignmentDueFilter, AssignmentFilterStatus, Course } from "../types.ts";
import { DEFAULT_SETTINGS } from "../types.ts";

function makeCourse(overrides: Partial<Course> = {}): Course {
 return {
  id: "c1",
  name: "Math",
  description: null,
  section: null,
  room: null,
  course_state: "ACTIVE",
  teachers: [],
  role: "STUDENT",
  student_count: 0,
  total_assignments: 3,
  todo_count: 0,
  overdue_count: 0,
  graded_count: 0,
  average_grade: null,
  ...overrides,
 };
}

type Handlers = {
 onToggleStatus: ReturnType<typeof vi.fn>;
 onToggleDue: ReturnType<typeof vi.fn>;
 onSelectAllDue: ReturnType<typeof vi.fn>;
 onClearAllDue: ReturnType<typeof vi.fn>;
};

function renderPanel(props: Partial<Parameters<typeof FilterPanel>[0]> = {}) {
 const handlers: Handlers = {
  onToggleStatus: vi.fn(),
  onToggleDue: vi.fn(),
  onSelectAllDue: vi.fn(),
  onClearAllDue: vi.fn(),
 };
 localStorage.setItem(
  "gc-settings",
  JSON.stringify({ ...DEFAULT_SETTINGS, language: "en" }),
 );
 render(
  <SettingsProvider>
   <FilterPanel
    open
    onClose={vi.fn()}
    courses={[makeCourse()]}
    statuses={null}
    due={null}
    selectedCourses={null}
    statusCounts={{ todo: 2, overdue: 1, completed: 1, graded: 1 }}
    dueCounts={{ has_due: 2, no_due: 1 }}
    onToggleStatus={handlers.onToggleStatus}
    onSelectAllStatuses={vi.fn()}
    onClearAllStatuses={vi.fn()}
    onToggleDue={handlers.onToggleDue}
    onSelectAllDue={handlers.onSelectAllDue}
    onClearAllDue={handlers.onClearAllDue}
    onToggleCourse={vi.fn()}
    onSelectAllCourses={vi.fn()}
    onClearAllCourses={vi.fn()}
    onReset={vi.fn()}
    {...props}
   />
  </SettingsProvider>,
 );
 return handlers;
}

describe("FilterPanel", () => {
 beforeEach(() => {
  localStorage.clear();
 });

 it("renders a separate due-date section with its own values", () => {
  renderPanel();

  expect(screen.getByText("By status")).toBeInTheDocument();
  expect(screen.getByText("By due date")).toBeInTheDocument();
  // The wrapping <label> gives each checkbox its label as the accessible name.
  expect(
   screen.getByRole("checkbox", { name: "Has due date" }),
  ).toBeInTheDocument();
  expect(
   screen.getByRole("checkbox", { name: "No due date" }),
  ).toBeInTheDocument();
 });

 it("explains how the sections are combined", () => {
  renderPanel();

  expect(
   screen.getByText(/separate sections are combined with/),
  ).toBeInTheDocument();
 });

 it("shows the result count next to every value", () => {
  renderPanel();

  // Status counts come from the props, due counts from their own record.
  const statusRow = screen.getByRole("checkbox", { name: "To do" })
   .closest("label");
  expect(statusRow).toHaveTextContent("2");
  const dueRow = screen.getByRole("checkbox", { name: "No due date" })
   .closest("label");
  expect(dueRow).toHaveTextContent("1");
 });

 it("toggling a due value reports that value, not a status", () => {
  const handlers = renderPanel();

  fireEvent.click(screen.getByRole("checkbox", { name: "No due date" }));

  expect(handlers.onToggleDue).toHaveBeenCalledWith("no_due");
  expect(handlers.onToggleStatus).not.toHaveBeenCalled();
 });

 it("the due section has its own select-all and clear-all actions", () => {
  const handlers = renderPanel();

  // Two sections x two round buttons; click the ones in the due section.
  const clearButtons = screen.getAllByLabelText("Clear all");
  fireEvent.click(clearButtons[1]);
  expect(handlers.onClearAllDue).toHaveBeenCalled();

  const selectButtons = screen.getAllByLabelText("Select all");
  fireEvent.click(selectButtons[1]);
  expect(handlers.onSelectAllDue).toHaveBeenCalled();
 });

 it("a selected due value is reflected in the checkbox", () => {
  renderPanel({ due: ["no_due"] as AssignmentDueFilter[] });

  expect(screen.getByRole("checkbox", { name: "No due date" })).toBeChecked();
  expect(
   screen.getByRole("checkbox", { name: "Has due date" }),
  ).not.toBeChecked();
 });

 it("a null due facet leaves both values checked", () => {
  renderPanel();

  expect(screen.getByRole("checkbox", { name: "No due date" })).toBeChecked();
  expect(
   screen.getByRole("checkbox", { name: "Has due date" }),
  ).toBeChecked();
 });

 it("renders only the courses it is given", () => {
  renderPanel({
   courses: [
    makeCourse({ id: "c1", name: "Math" }),
    makeCourse({ id: "c2", name: "History" }),
   ],
  });

  expect(screen.getByText("Math")).toBeInTheDocument();
  expect(screen.getByText("History")).toBeInTheDocument();
 });

 it("marks a status as selected only when it is in the list", () => {
  renderPanel({ statuses: ["overdue"] as AssignmentFilterStatus[] });

  expect(screen.getByRole("checkbox", { name: "Overdue" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "To do" })).not.toBeChecked();
 });
});