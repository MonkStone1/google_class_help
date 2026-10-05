import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TeacherGrades } from "./TeacherGrades.tsx";
import { api } from "../../../shared/api/index.ts";
import { SettingsProvider } from "../../../shared/settings/index.ts";
import { invalidateAllResources } from "../../../shared/hooks/index.ts";
import type {
  StudentGradeRow,
  TeacherGradeDisplay,
  TeacherGrades as TeacherGradesData,
} from "../../../shared/types/index.ts";
import { DEFAULT_SETTINGS } from "../../../shared/types/index.ts";

const getCourseGrades = vi.spyOn(api, "getCourseGrades");

function makeRow(overrides: Partial<StudentGradeRow> = {}): StudentGradeRow {
  return {
    student: {
      id: "s1",
      full_name: "Sam",
      email: null,
      photo_url: null,
    },
    cells: [
      {
        coursework_id: "w1",
        status: "graded",
        submitted: true,
        returned: true,
        graded: true,
        late: false,
        points: 12,
        max_points: 12,
        percent: 100,
        submitted_at: null,
        updated_at: null,
      },
    ],
    average_percent: 100,
    ...overrides,
  };
}

function makeData(rows: StudentGradeRow[]): TeacherGradesData {
  return {
    course_id: "c1",
    course_name: "Math",
    role: "TEACHER",
    assignments: [
      { assignment_id: "w1", title: "Quiz", max_points: 12, due_at: null },
    ],
    rows,
    class_average: 100,
    last_sync: null,
  };
}

/** Renders the matrix with the given cell format already stored. */
function renderPage(display: TeacherGradeDisplay = "both") {
  // The assertions use the English labels, so the language is pinned instead of
  // inherited from detectLanguage() through the machine default.
  localStorage.setItem(
    "gc-settings",
    JSON.stringify({
      ...DEFAULT_SETTINGS,
      language: "en",
      teacherGradeDisplay: display,
    }),
  );
  return render(
    <MemoryRouter initialEntries={["/subjects/c1/grades"]}>
      <SettingsProvider>
        <Routes>
          <Route path="/subjects/:courseId/grades" element={<TeacherGrades />} />
        </Routes>
      </SettingsProvider>
    </MemoryRouter>,
  );
}

/** The one graded cell of the single row the fixtures build. */
async function gradedCell(): Promise<HTMLElement> {
  const row = (await screen.findAllByRole("row"))[1];
  const cells = within(row).getAllByRole("cell");
  // student | quiz | average
  return cells[1];
}

describe("TeacherGrades cell format", () => {
  beforeEach(() => {
    getCourseGrades.mockReset();
    // The resource cache is module-level and keyed by course, so without this the
    // second test would read the payload cached by the first one.
    invalidateAllResources();
    getCourseGrades.mockResolvedValue(makeData([makeRow()]));
  });

  it("shows the raw mark alone when the teacher picks points", async () => {
    // ADR-0043: "12" instead of "12 / 12" — the maximum belongs to the column,
    // not to the cell.
    renderPage("points");

    const cell = await gradedCell();
    expect(cell).toHaveTextContent("12");
    expect(cell).not.toHaveTextContent("/");
    expect(cell).not.toHaveTextContent("%");
  });

  it("shows the percentage alone when the teacher picks percent", async () => {
    renderPage("percent");

    const cell = await gradedCell();
    expect(cell).toHaveTextContent("100%");
    expect(cell).not.toHaveTextContent("/");
  });

  it("shows the mark out of the task when the teacher picks the ratio", async () => {
    // ADR-0043: "12 / 12" — the maximum travels with the mark, the percentage
    // does not.
    renderPage("ratio");

    const cell = await gradedCell();
    expect(cell).toHaveTextContent("12 / 12");
    expect(cell).not.toHaveTextContent("%");
  });

  it("keeps both numbers as the default format", async () => {
    renderPage();

    expect(await gradedCell()).toHaveTextContent("12 / 12 · 100%");
  });

  it("still reports the row average as a percentage", async () => {
    // The format setting is about the CELLS; the average is a different quantity
    // and Classroom only ever computes it in percent (ADR-0008).
    renderPage("points");

    const row = (await screen.findAllByRole("row"))[1];
    const cells = within(row).getAllByRole("cell");
    expect(cells[2]).toHaveTextContent("100%");
  });

  it("leaves an ungraded cell as its status, whatever the format", async () => {
    // "Not submitted" is not a grade, so there is nothing to reformat.
    getCourseGrades.mockResolvedValue(
      makeData([
        makeRow({
          cells: [
            {
              coursework_id: "w1",
              status: "not_submitted",
              submitted: false,
              returned: false,
              graded: false,
              late: false,
              points: null,
              max_points: 12,
              percent: null,
              submitted_at: null,
              updated_at: null,
            },
          ],
        }),
      ]),
    );

    renderPage("points");

    const cell = await gradedCell();
    expect(cell).toHaveTextContent("Not submitted");
    expect(cell).not.toHaveTextContent("0");
  });
});