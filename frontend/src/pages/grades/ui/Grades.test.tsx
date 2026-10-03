import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Grades } from "./Grades.tsx";
import type { Assignment, Course } from "../../../shared/types/index.ts";
import { DEFAULT_SETTINGS } from "../../../shared/types/index.ts";

const useCourses = vi.fn();
const useSync = vi.fn();
const useSettings = vi.fn();

vi.mock("../../../features/sync/index.ts", async () => {
  const actual = await vi.importActual<typeof import("../../../features/sync/index.ts")>(
    "../../../features/sync/index.ts",
  );
  return {
    ...actual,
   useSync: () => useSync(),
  };
});
vi.mock("../../../entities/course/index.ts", async () => {
  const actual = await vi.importActual<typeof import("../../../entities/course/index.ts")>(
    "../../../entities/course/index.ts",
  );
  return {
    ...actual,
   useCourses: () => useCourses(),
  };
});

vi.mock("../../../shared/settings/index.ts", async () => {
  const actual = await vi.importActual<typeof import("../../../shared/settings/index.ts")>(
    "../../../shared/settings/index.ts",
  );
  return {
    ...actual,
   useSettings: () => useSettings(),
  };
});

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
  total_assignments: 0,
  todo_count: 0,
  overdue_count: 0,
  graded_count: 0,
  average_grade: 90,
  ...overrides,
 };
}

function makeAssignment(overrides: Partial<Assignment> = {}): Assignment {
 return {
  id: "a1",
  course_id: "c1",
  course_name: "Math",
  title: "HW",
  description: null,
  due_at: "2026-01-01T12:00:00",
  max_points: 100,
  work_type: null,
  state: "PUBLISHED",
  alternate_link: null,
  materials: [],
  created_at: null,
  updated_at: null,
  submission_state: "RETURNED",
  submitted: true,
  graded: true,
  points: 90,
  late: false,
  is_overdue: false,
  priority: "low",
  role: "STUDENT",
  student_count: 0,
  submission_count: 0,
  graded_count: 0,
  average_percent: null,
  ...overrides,
 };
}

function renderPage() {
 return render(<Grades />);
}

describe("Grades collapsible groups", () => {
 beforeEach(() => {
  useCourses.mockReset();
  useSync.mockReset();
  useSettings.mockReset();
  useSync.mockReturnValue({
   loading: false,
   status: { average_grade: 90 },
  });
  useCourses.mockReturnValue({
   courses: [makeCourse()],
   assignments: [makeAssignment()],
  });
 });

 it("a group starts expanded when the course is not in the collapsed list", () => {
  useSettings.mockReturnValue({
   ...DEFAULT_SETTINGS,
   collapsedGradeCourses: [],
   update: vi.fn(),
  });

  renderPage();

  const toggle = screen.getByRole("button", { name: /Math/ });
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText("HW")).toBeInTheDocument();
 });

 it("a collapsed group hides its rows but keeps the course name and average", () => {
  useSettings.mockReturnValue({
   ...DEFAULT_SETTINGS,
   collapsedGradeCourses: ["c1"],
   update: vi.fn(),
  });

  renderPage();

  const toggle = screen.getByRole("button", { name: /Math/ });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByText("HW")).not.toBeInTheDocument();
  // The header keeps working as a summary, so the course stays identifiable.
  expect(screen.getByText("Math")).toBeInTheDocument();
  expect(screen.getByText(/Average: 90%/)).toBeInTheDocument();
 });

 it("clicking a group writes the new state into the settings store", () => {
  const update = vi.fn();
  useSettings.mockReturnValue({
   ...DEFAULT_SETTINGS,
   collapsedGradeCourses: [],
   update,
  });

  renderPage();
  fireEvent.click(screen.getByRole("button", { name: /Math/ }));

  expect(update).toHaveBeenCalledWith({ collapsedGradeCourses: ["c1"] });
 });

 it("expanding a collapsed group removes the course from the list", () => {
  const update = vi.fn();
  useSettings.mockReturnValue({
   ...DEFAULT_SETTINGS,
   collapsedGradeCourses: ["c1"],
   update,
  });

  renderPage();
  fireEvent.click(screen.getByRole("button", { name: /Math/ }));

  expect(update).toHaveBeenCalledWith({ collapsedGradeCourses: [] });
 });

 it("the toggle points at the body it controls", () => {
  useSettings.mockReturnValue({
   ...DEFAULT_SETTINGS,
   collapsedGradeCourses: [],
   update: vi.fn(),
  });

  renderPage();

  const toggle = screen.getByRole("button", { name: /Math/ });
  const controls = toggle.getAttribute("aria-controls");
  expect(controls).toBeTruthy();
  expect(document.getElementById(controls as string)).toBeInTheDocument();
 });
describe("the grade-trend chart on the grades page", () => {
  beforeEach(() => {
    useSync.mockReturnValue({
      loading: false,
      status: { average_grade: 90 },
    });
    useSettings.mockReturnValue({
      ...DEFAULT_SETTINGS,
      collapsedGradeCourses: [],
      update: vi.fn(),
    });
  });

  it("no longer draws the sparkline, and offers the chart instead", () => {
    // The sparkline was a second, worse way to see the same grades. Removing it
    // is what makes the button the ONLY way to open the chart.
    useCourses.mockReturnValue({
      courses: [makeCourse()],
      assignments: [
        makeAssignment({ id: "a1", due_at: "2026-01-12T12:00:00" }),
        makeAssignment({ id: "a2", due_at: "2026-02-02T12:00:00" }),
      ],
    });

    const { container } = renderPage();

    expect(container.querySelector(".grade-sparkline")).toBeNull();
    expect(container.querySelector(".grade-history")).toBeNull();
    expect(screen.getByRole("button", { name: "Chart" })).toBeInTheDocument();
  });

  it("gives every course group a named chart button", () => {
    useCourses.mockReturnValue({
      courses: [
        makeCourse({ id: "c1", name: "Math" }),
        makeCourse({ id: "c2", name: "Physics" }),
      ],
      assignments: [
        makeAssignment({ id: "a1", course_id: "c1" }),
        makeAssignment({ id: "a2", course_id: "c2" }),
      ],
    });

    renderPage();

    // Two courses, two buttons — each in its own header, next to its average.
    const buttons = screen.getAllByRole("button", { name: "Chart" });
    expect(buttons).toHaveLength(2);
    for (const button of buttons) {
      expect(button.getAttribute("aria-label")).toBeTruthy();
    }
  });

  it("keeps the chart button on a COLLAPSED group, where the summary is", () => {
    useSettings.mockReturnValue({
      ...DEFAULT_SETTINGS,
      collapsedGradeCourses: ["c1"],
      update: vi.fn(),
    });
    useCourses.mockReturnValue({
      courses: [makeCourse()],
      assignments: [makeAssignment()],
    });

    renderPage();

    // A collapsed row still says the course name and the average; hiding the
    // only way to open the chart would hide the question that row raises.
    expect(screen.queryByText("HW")).toBeNull();
    expect(screen.getByRole("button", { name: "Chart" })).toBeInTheDocument();
  });
});
});