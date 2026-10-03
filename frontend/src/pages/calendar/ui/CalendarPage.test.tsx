import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CalendarPage } from "./CalendarPage.tsx";
import type { AppSettings, Assignment } from "../../../shared/types/index.ts";
import { DEFAULT_SETTINGS } from "../../../shared/types/index.ts";

const useCourses = vi.fn();
const useSync = vi.fn();
const useSettings = vi.fn();

vi.mock("../../../features/sync/index.ts", () => ({
 useSync: () => useSync(),
}));
vi.mock("../../../entities/course/index.ts", () => ({
 useCourses: () => useCourses(),
}));

vi.mock("../../../shared/settings/SettingsProvider.tsx", () => ({
 useSettings: () => useSettings(),
}));

// The component formats calendar labels through `useI18n()`, which resolves the
// locale from the mocked settings, so the tests must build the expected labels
// with the same locale instead of the machine default.
const LOCALE = "en-US";

function makeAssignment(overrides: Partial<Assignment> = {}): Assignment {
 return {
  id: "a1",
  course_id: "c1",
  course_name: "Math",
  title: "HW",
  description: null,
  due_at: null,
  max_points: null,
  work_type: null,
  state: null,
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

// The mocked settings context adds `update` on top of AppSettings.
type MockSettings = Partial<AppSettings> & {
 update: (patch: Partial<AppSettings>) => void;
};

function settingsWith(patch: Partial<MockSettings> = {}) {
 return { ...DEFAULT_SETTINGS, ...patch };
}

function renderPage() {
 return render(
  <MemoryRouter>
   <CalendarPage />
  </MemoryRouter>,
 );
}

/** A date `days` from today, formatted the way the backend serialises it. */
function dueIn(days: number): string {
 const date = new Date();
 date.setDate(date.getDate() + days);
 date.setHours(10, 0, 0, 0);
 const pad = (n: number) => String(n).padStart(2, "0");
 return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T10:00:00`;
}

/** The accessible label the grid puts on the cell of `days`-from-today. */
function dayCellLabel(days: number): string {
 const date = new Date();
 date.setDate(date.getDate() + days);
 return date.toLocaleDateString(LOCALE, {
  weekday: "long",
  day: "numeric",
  month: "long",
 });
}

/**
 * First day of the rendered month grid that belongs to another month than
 * today. The grid is 6 weeks starting on the Monday on/before the 1st, so the
 * days it spills into the neighbouring month are always the "outside" cells —
 * clicking one both moves the cursor and changes the visible month.
 */
function firstOutsideCell(): { label: string; month: string } {
 const first = new Date();
 first.setDate(1);
 const gridStart = new Date(first);
 gridStart.setDate(first.getDate() - ((first.getDay() + 6) % 7));
 for (let offset = 0; offset < 42; offset += 1) {
  const day = new Date(gridStart);
  day.setDate(gridStart.getDate() + offset);
  if (day.getMonth() !== first.getMonth()) {
   return {
    label: day.toLocaleDateString(LOCALE, {
     weekday: "long",
     day: "numeric",
     month: "long",
    }),
    // Kept as a Date: re-parsing the label would not be locale-safe.
    month: day.toLocaleDateString(LOCALE, {
     month: "long",
     year: "numeric",
    }),
   };
  }
 }
 throw new Error("no outside cell in the month grid");
}

describe("CalendarPage", () => {
 beforeEach(() => {
  useCourses.mockReset();
  useSync.mockReset();
  useSettings.mockReset();
  useSync.mockReturnValue({ loading: false });
 });

 it("clicking a day cell opens that day in the day view", () => {
  useCourses.mockReturnValue({ assignments: [] });
  const update = vi.fn();
  useSettings.mockReturnValue(
   settingsWith({ calendarView: "month", update }),
  );

  renderPage();

  // The cell is the clickable day surface: one click must both move the cursor
  // and persist the day view, so the user lands inside the day they picked.
  fireEvent.click(screen.getByLabelText(dayCellLabel(0)));

  expect(update).toHaveBeenCalledWith({ calendarView: "day" });
 });

 it("clicking a cell moves the cursor to that day", () => {
  useCourses.mockReturnValue({ assignments: [] });
  const update = vi.fn();
  useSettings.mockReturnValue(
   settingsWith({ calendarView: "month", update }),
  );

  renderPage();

  // An "outside" cell belongs to the neighbouring month, so the header proves
  // the cursor really moved to the clicked day instead of staying on today.
  const target = firstOutsideCell();

  fireEvent.click(screen.getByLabelText(target.label));

  expect(update).toHaveBeenCalledWith({ calendarView: "day" });
  expect(screen.getByText(target.month)).toBeInTheDocument();
 });

 it("switching to the day view resets the cursor to today", () => {
  useCourses.mockReturnValue({
   assignments: [
    makeAssignment({ title: "Today task", due_at: dueIn(0) }),
   ],
  });
  const update = vi.fn();
  useSettings.mockReturnValue(
   settingsWith({ calendarView: "month", update }),
  );

  renderPage();

  // Navigate away first, so a cursor that was never reset would show nothing.
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  expect(update).not.toHaveBeenCalledWith({ calendarView: "day" });

  fireEvent.click(screen.getByRole("button", { name: "Day" }));

  expect(update).toHaveBeenCalledWith({ calendarView: "day" });
  expect(screen.getByText("Today task")).toBeInTheDocument();
 });

 it("the day list marks submitted and overdue assignments", () => {
  useCourses.mockReturnValue({
   assignments: [
    makeAssignment({
     id: "done",
     title: "Done task",
     due_at: dueIn(0),
     submitted: true,
    }),
    makeAssignment({
     id: "late",
     title: "Late task",
     due_at: dueIn(0),
     is_overdue: true,
    }),
   ],
  });
  useSettings.mockReturnValue(
   settingsWith({ calendarView: "day", update: vi.fn() }),
  );

  renderPage();

  expect(screen.getByRole("button", { name: /Done task/ })).toHaveClass(
   "day-list-done",
  );
  expect(screen.getByRole("button", { name: /Late task/ })).toHaveClass(
   "day-list-overdue",
  );
 });

 it("a long course name is truncated but keeps its full text on hover", () => {
  const longName = "An Extremely Long Course Name That Should Not Overflow";
  useCourses.mockReturnValue({
   assignments: [
    makeAssignment({ title: "Essay", course_name: longName, due_at: dueIn(0) }),
   ],
  });
  useSettings.mockReturnValue(
   settingsWith({ calendarView: "day", update: vi.fn() }),
  );

  renderPage();

  const chip = screen.getByText(longName);
  expect(chip).toHaveClass("day-list-course");
  expect(chip).toHaveAttribute("title", longName);
 });
});