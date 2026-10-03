import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AssignmentDetail } from "./AssignmentDetail.tsx";
import { api } from "../shared/api/index.ts";
import { SettingsProvider } from "../shared/settings/SettingsProvider.tsx";
import { invalidateAllResources } from "../shared/hooks/useResource.ts";
import type { AssignmentDetail as AssignmentDetailData } from "../shared/types/index.ts";
import { DEFAULT_SETTINGS } from "../shared/types/index.ts";

const getAssignmentDetail = vi.spyOn(api, "getAssignmentDetail");

function makeData(state: string | null): AssignmentDetailData {
 return {
  id: "w1",
  course_id: "c1",
  course_name: "Physics",
  title: "Lab",
  description: null,
  due_at: "2026-01-05T12:00:00",
  max_points: 100,
  work_type: null,
  state,
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
  role: "TEACHER",
  student_count: 0,
  submission_count: 0,
  graded_count: 0,
  average_percent: null,
  submissions: [],
  status_counts: {},
 };
}

// The state lives in the fetched payload, so this helper only sets the language.
async function renderWithLanguage(language: "en" | "ru") {
 localStorage.setItem(
  "gc-settings",
  JSON.stringify({ ...DEFAULT_SETTINGS, language }),
 );
 render(
  <MemoryRouter initialEntries={["/subjects/c1/assignments/w1"]}>
   <SettingsProvider>
    <Routes>
     <Route
      path="/subjects/:courseId/assignments/:courseworkId"
      element={<AssignmentDetail />}
     />
    </Routes>
   </SettingsProvider>
  </MemoryRouter>,
 );
 return screen.findByText("Lab");
}

describe("AssignmentDetail work state label", () => {
 beforeEach(() => {
  getAssignmentDetail.mockReset();
  invalidateAllResources();
 });

 it("shows the localized label instead of the raw Google enum", async () => {
  getAssignmentDetail.mockResolvedValue(makeData("PUBLISHED"));
  await renderWithLanguage("ru");

  expect(screen.getByText("Опубликовано")).toBeInTheDocument();
  expect(screen.queryByText("PUBLISHED")).not.toBeInTheDocument();
 });

 it("localizes a draft as well", async () => {
  getAssignmentDetail.mockResolvedValue(makeData("DRAFT"));
  await renderWithLanguage("ru");

  expect(screen.getByText("Черновик")).toBeInTheDocument();
  expect(screen.queryByText("DRAFT")).not.toBeInTheDocument();
 });

 it("falls back to a placeholder for an unknown state", async () => {
  getAssignmentDetail.mockResolvedValue(makeData("SOMETHING_NEW"));
  await renderWithLanguage("en");

  expect(screen.getByText("Unknown status")).toBeInTheDocument();
 });

 it("shows a dash when the course has no state at all", async () => {
  getAssignmentDetail.mockResolvedValue(makeData(null));
  await renderWithLanguage("en");

  // The details list uses a dash for every missing value, so the state row is
  // located by its own label rather than by the dash itself.
  const stateTerm = screen.getByText("Assignment status");
  const stateValue = stateTerm.parentElement?.querySelector("dd");
  expect(stateValue).toHaveTextContent("—");
 });
});