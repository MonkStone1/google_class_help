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
});