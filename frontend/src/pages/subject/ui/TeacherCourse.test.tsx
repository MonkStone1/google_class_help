import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TeacherCourse } from "./TeacherCourse.tsx";
import { api } from "../../../shared/api/index.ts";
import { SettingsProvider } from "../../../shared/settings/index.ts";
import { invalidateAllResources } from "../../../shared/hooks/index.ts";
import type { Assignment, Course } from "../../../shared/types/index.ts";
import { DEFAULT_SETTINGS } from "../../../shared/types/index.ts";

// The export must never write a real file from a test.
const saveBuffer = vi.hoisted(() => vi.fn());
vi.mock("../../../features/excel-export/engine/download.ts", () => ({
  saveBuffer,
  XLSX_MIME: "text/x",
}));
vi.mock("../../../features/excel-export/engine/workbook.ts", () => ({
  buildWorkbookBuffer: vi.fn(async () => new ArrayBuffer(8)),
  fillWorksheet: vi.fn(),
}));

const getCourseCoursework = vi.spyOn(api, "getCourseCoursework");
const getCourseGrades = vi.spyOn(api, "getCourseGrades");

function makeCourse(overrides: Partial<Course> = {}): Course {
  return {
    id: "c1",
    name: "Математика 8/А",
    description: null,
    section: null,
    room: null,
    course_state: "ACTIVE",
    teachers: ["Ivanova"],
    role: "TEACHER",
    student_count: 12,
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
    id: "w1",
    course_id: "c1",
    course_name: "Математика 8/А",
    title: "Урок 1. 20.09.2026 Теми",
    description: "Прочитати https://example.com/a",
    due_at: null,
    max_points: null,
    work_type: null,
    state: null,
    alternate_link: null,
    materials: [],
    created_at: "2026-09-20T10:00:00",
    updated_at: null,
    submission_state: null,
    submitted: false,
    graded: false,
    points: null,
    late: false,
    is_overdue: false,
    priority: "low",
    role: "TEACHER",
    student_count: 0,
    submission_count: 0,
    graded_count: 0,
    average_percent: null,
    ...overrides,
  };
}

function renderPage(course = makeCourse()) {
  localStorage.setItem(
    "gc-settings",
    JSON.stringify({ ...DEFAULT_SETTINGS, language: "en" }),
  );
  return render(
    <MemoryRouter>
      <SettingsProvider>
        <TeacherCourse course={course} />
      </SettingsProvider>
    </MemoryRouter>,
  );
}

describe("the export button on the teacher course page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // The resource cache is module-level and keyed by course, so without this
    // the second test would read the payload cached by the first one.
    invalidateAllResources();
    getCourseGrades.mockResolvedValue({
      course_id: "c1",
      course_name: "Математика 8/А",
      role: "TEACHER",
      rows: [],
      class_average: null,
      assignments: [],
      last_sync: null,
    });
  });

  it("offers the export once the coursework has loaded", async () => {
    getCourseCoursework.mockResolvedValue([makeAssignment()]);

    renderPage();

    const button = await screen.findByRole("button", { name: /Export to Excel/i });
    expect(button).toBeEnabled();
    expect(saveBuffer).not.toHaveBeenCalled();
  });

  it("is disabled while the coursework is still loading", () => {
    getCourseCoursework.mockReturnValue(new Promise(() => undefined));

    renderPage();

    // Nothing to export yet, and the teacher should not reach a dialog that
    // can only tell them there is nothing there.
    expect(
      screen.getByRole("button", { name: /Export to Excel/i }),
    ).toBeDisabled();
  });

  it("builds the export from the data this page already loaded", async () => {
    getCourseCoursework.mockResolvedValue([makeAssignment()]);
    renderPage();
    await screen.findByRole("button", { name: /Export to Excel/i });

    fireEvent.click(screen.getByRole("button", { name: /Export to Excel/i }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Export", hidden: false }),
    );

    await waitFor(() => expect(saveBuffer).toHaveBeenCalledTimes(1));
    // One read of the coursework, no request of its own: the export adds
    // nothing to the network (ADR-0041).
    expect(getCourseCoursework).toHaveBeenCalledTimes(1);
    expect(saveBuffer.mock.calls[0][1]).toBe(
      "Математика 8_А_електронний_щоденник.xls",
    );
  });
});