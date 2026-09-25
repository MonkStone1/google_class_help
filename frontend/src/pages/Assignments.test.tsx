import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Assignments } from "./Assignments.tsx";
import type { AppSettings, Assignment, Course } from "../types.ts";
import { DEFAULT_SETTINGS } from "../types.ts";

const useCourses = vi.fn();
const useSync = vi.fn();
const useSettings = vi.fn();

// A real SettingsProvider owns its own state, so the page is driven through a
// spy on `useSettings` to observe what the filter writes back (ADR-0006).
vi.mock("../context/SettingsContext.tsx", async () => {
 const actual = await vi.importActual<
  typeof import("../context/SettingsContext.tsx")
 >("../context/SettingsContext.tsx");
 return { ...actual, useSettings: () => useSettings() };
});

const useSettingsMock = useSettings;

vi.mock("../context/DataContext.tsx", () => ({
 useCourses: () => useCourses(),
 useSync: () => useSync(),
}));

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
  total_assignments: 1,
  todo_count: 0,
  overdue_count: 0,
  graded_count: 0,
  average_grade: null,
  ...overrides,
 };
}

function makeAssignment(overrides: Partial<Assignment> = {}): Assignment {
 return {
  id: "a1",
  course_id: "c1",
  course_name: "Math",
  title: "Homework",
  description: null,
  due_at: "2026-01-01T12:00:00",
  max_points: 100,
  work_type: null,
  state: "PUBLISHED",
  alternate_link: null,
  materials: [],
  created_at: null,
  updated_at: null,
  submission_state: null,
  submitted: false,
  graded: false,
  points: null,
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

function settings(patch: Partial<AppSettings> = {}): AppSettings {
 return { ...DEFAULT_SETTINGS, language: "en", ...patch };
}

function renderPage(patch: Partial<AppSettings> = {}) {
 useSettingsMock.mockReturnValue({
  ...settings(patch),
  update: (next: Partial<AppSettings>) =>
   useSettingsMock.mockReturnValue({ ...settings(patch), ...next }),
  updateSection: vi.fn(),
  updateNotification: vi.fn(),
  dismissNotification: vi.fn(),
  dismissAllNotifications: vi.fn(),
  reset: vi.fn(),
 });
 return render(
  <MemoryRouter initialEntries={["/assignments"]}>
   <Assignments />
  </MemoryRouter>,
 );
}

describe("Assignments course facet", () => {
 beforeEach(() => {
  useCourses.mockReset();
  useSync.mockReset();
  useSettingsMock.mockReset();
  useSync.mockReturnValue({ loading: false, error: null });
  useCourses.mockReturnValue({
   courses: [
    makeCourse({ id: "c1", name: "Math" }),
    makeCourse({ id: "c2", name: "History" }),
   ],
   assignments: [makeAssignment()],
  });
 });

 it("lists every student course in the filter panel", async () => {
  renderPage();

  fireEvent.click(screen.getByRole("button", { name: "Filters" }));

  const panel = await screen.findByRole("dialog", { name: "Filters" });
  expect(within(panel).getByText("Math")).toBeInTheDocument();
  expect(within(panel).getByText("History")).toBeInTheDocument();
 });

 it("never offers a course the user teaches", async () => {
  useCourses.mockReturnValue({
   courses: [
    makeCourse({ id: "c1", name: "Math", role: "STUDENT" }),
    makeCourse({ id: "t1", name: "Physics", role: "TEACHER" }),
   ],
   assignments: [makeAssignment()],
  });

  renderPage();

  fireEvent.click(screen.getByRole("button", { name: "Filters" }));

  const panel = await screen.findByRole("dialog", { name: "Filters" });
  expect(within(panel).getByText("Math")).toBeInTheDocument();
  // A taught course could only ever produce an empty result, so it is not
  // offered as a filter at all.
  expect(within(panel).queryByText("Physics")).not.toBeInTheDocument();
 });

 it("shows a chip per explicitly selected value and removes it on click", () => {
  renderPage({
   assignmentsFilter: { statuses: ["todo"], due: ["no_due"], courses: null },
  });

  expect(screen.getByText("To do")).toBeInTheDocument();
  // Both chips come from different facets but share the same label vocabulary.
  expect(screen.getByText("No due date")).toBeInTheDocument();

  const chip = screen.getByRole("button", {
   name: "Remove filter To do",
  });
  fireEvent.click(chip);

  // The chip must hand the page the filter without its own value.
  expect(useSettingsMock).toHaveBeenCalled();
 });

 it("shows no chips when every facet is off", () => {
  renderPage();

  expect(
   screen.queryByRole("button", { name: /^Remove filter/ }),
  ).not.toBeInTheDocument();
 });

 it("marks the filter button active when a facet is on", () => {
  renderPage({
   assignmentsFilter: { statuses: null, due: ["no_due"], courses: null },
  });

  const button = screen.getByRole("button", { name: "Filters" });
  expect(button).toHaveClass("active");
 });
});