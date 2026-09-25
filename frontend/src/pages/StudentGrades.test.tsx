import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StudentGrades } from "./StudentGrades.tsx";
import { api } from "../api.ts";
import { SettingsProvider } from "../context/SettingsContext.tsx";
import { invalidateAllResources } from "../lib/resource.ts";
import type { StudentGradeItem, StudentGrades as StudentGradesData } from "../types.ts";
import { DEFAULT_SETTINGS } from "../types.ts";

const getStudentGrades = vi.spyOn(api, "getStudentGrades");
function makeItem(overrides: Partial<StudentGradeItem> = {}): StudentGradeItem {
 return {
  assignment_id: "w1",
  title: "Quiz",
  due_at: "2026-01-05T12:00:00",
  max_points: 100,
  submission_state: "RETURNED",
  status: "graded",
  submitted: true,
  returned: true,
  graded: true,
  late: false,
  points: 90,
  percent: 90,
  submitted_at: "2026-01-04T10:00:00",
  updated_at: null,
  attachments: [],
  alternate_link: null,
  ...overrides,
 };
}

function makeData(items: StudentGradeItem[]): StudentGradesData {
 return {
  course_id: "c1",
  course_name: "Math",
  student: { id: "s1", full_name: "Sam", email: null, photo_url: null },
  average_percent: 90,
  items,
  last_sync: null,
 };
}

function renderPage() {
 // The assertions below use the English labels, so pin the language instead of
 // inheriting the machine default through detectLanguage().
 localStorage.setItem(
  "gc-settings",
  JSON.stringify({ ...DEFAULT_SETTINGS, language: "en" }),
 );
 return render(
  <MemoryRouter initialEntries={["/subjects/c1/students/s1"]}>
   {/* The page reads its labels through useI18n, which needs the settings. */}
   <SettingsProvider>
    <Routes>
     <Route
      path="/subjects/:courseId/students/:studentId"
      element={<StudentGrades />}
     />
    </Routes>
   </SettingsProvider>
  </MemoryRouter>,
 );
}

describe("StudentGrades compact table", () => {
 beforeEach(() => {
  getStudentGrades.mockReset();
  // The resource cache is module-level and keyed by course+student, so without
  // this the second test would read the payload cached by the first one.
  invalidateAllResources();
 });

 it("renders one row per assignment instead of a stack of cards", async () => {
  getStudentGrades.mockResolvedValue(
   makeData([makeItem(), makeItem({ assignment_id: "w2", title: "Essay" })]),
  );

  renderPage();

  const rows = await screen.findAllByRole("row");
  // One header row plus one row per assignment.
  expect(rows).toHaveLength(3);
  expect(screen.getByText("Quiz")).toBeInTheDocument();
  expect(screen.getByText("Essay")).toBeInTheDocument();
 });

 it("shows the status and the grade side by side in the same row", async () => {
  getStudentGrades.mockResolvedValue(makeData([makeItem()]));

  renderPage();

  const row = (await screen.findAllByRole("row"))[1];
  const cells = within(row).getAllByRole("cell");
  // assignment | due | status | grade | submitted
  expect(cells).toHaveLength(5);
  expect(cells[2]).toHaveTextContent("Graded");
  expect(cells[3]).toHaveTextContent("90 / 100");
 });

 it("keeps the late marker next to the status", async () => {
  getStudentGrades.mockResolvedValue(
   makeData([makeItem({ late: true, status: "returned" })]),
  );

  renderPage();

  const row = (await screen.findAllByRole("row"))[1];
  const cells = within(row).getAllByRole("cell");
  expect(cells[2]).toHaveTextContent("Late");
  expect(cells[2]).toHaveTextContent("Returned");
 });

 it("never renders a missing grade as zero", async () => {
  getStudentGrades.mockResolvedValue(
   makeData([
    makeItem({
     status: "turned_in",
     graded: false,
     returned: false,
     points: null,
     percent: null,
    }),
   ]),
  );

  renderPage();

  const row = (await screen.findAllByRole("row"))[1];
  const cells = within(row).getAllByRole("cell");
  expect(cells[3]).toHaveTextContent("Not graded");
  // A missing grade must never be rendered as 0 (ADR-0008).
  expect(cells[3]).not.toHaveTextContent("0 /");
 });

 it("collapses attachments behind a disclosure so the row stays compact", async () => {
  getStudentGrades.mockResolvedValue(
   makeData([
    makeItem({
     attachments: [
      { type: "link", title: "Answer sheet", url: "https://example.com/a" },
     ],
     alternate_link: "https://classroom.google.com/x",
    }),
   ]),
  );

  renderPage();

  const row = (await screen.findAllByRole("row"))[1];
  const cells = within(row).getAllByRole("cell");
  expect(cells[0]).toHaveTextContent("Attachments (1)");
  // The attachment is present but only reachable through the disclosure, so a
  // long file list cannot make the row taller than one line.
  const attachment = within(cells[0]).getByRole("link", {
   name: "Answer sheet",
  });
  expect(attachment).toBeInTheDocument();
  expect(
   within(cells[0]).getByRole("link", {
    name: "Open in Google Classroom",
   }),
  ).toBeInTheDocument();
 });
});