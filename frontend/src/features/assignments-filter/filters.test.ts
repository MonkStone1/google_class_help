import { describe, expect, it } from "vitest";

import type {
  Assignment,
  AssignmentsFilter,
} from "../../shared/types/index.ts";
import {
  dueCounts,
  filterAssignments,
  pruneCourseSelection,
  sortAssignments,
  statusCounts,
} from "./filters.ts";
// The facet KEYS and the URL round-trip live in `shared/lib/url.ts` and are
// tested there: they describe what a LINK may carry, not how a facet matches.

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

const NO_FILTER: AssignmentsFilter = {
 statuses: null,
 due: null,
 courses: null,
};

const DATED = { due_at: "2026-01-01T12:00:00" };

describe("due-date facet (ADR-0013)", () => {
 it("`no_due` alone selects every undated assignment, whatever its state", () => {
  const undatedTodo = makeAssignment({ due_at: null });
  const undatedDone = makeAssignment({
   id: "a2",
   due_at: null,
   submitted: true,
  });
  const dated = makeAssignment({ id: "a3", ...DATED });
  const filtered = filterAssignments([undatedTodo, undatedDone, dated], {
   ...NO_FILTER,
   due: ["no_due"],
  });
  expect(filtered.map((item) => item.id)).toEqual(["a1", "a2"]);
 });

 it("`has_due` alone selects every dated assignment, whatever its state", () => {
  const datedTodo = makeAssignment({ id: "a1", ...DATED });
  const undated = makeAssignment({ id: "a2", due_at: null });
  const filtered = filterAssignments([datedTodo, undated], {
   ...NO_FILTER,
   due: ["has_due"],
  });
  expect(filtered.map((item) => item.id)).toEqual(["a1"]);
 });

 it("both values together match everything, since every task falls in one", () => {
  const dated = makeAssignment({ id: "a1", ...DATED });
  const undated = makeAssignment({ id: "a2", due_at: null });
  const filtered = filterAssignments([dated, undated], {
   ...NO_FILTER,
   due: ["has_due", "no_due"],
  });
  expect(filtered).toHaveLength(2);
 });

 it("'To do' + 'No due date' is the intersection: not submitted AND undated", () => {
  const undatedTodo = makeAssignment({ id: "a1", due_at: null });
  const undatedGraded = makeAssignment({
   id: "a2",
   due_at: null,
   submitted: true,
   graded: true,
  });
  const datedTodo = makeAssignment({ id: "a3", ...DATED });
  const filtered = filterAssignments(
   [undatedTodo, undatedGraded, datedTodo],
   { ...NO_FILTER, statuses: ["todo"], due: ["no_due"] },
  );
  // The graded undated task is excluded by the status, the dated one by the due
  // facet: the two facets are ANDed, never merged.
  expect(filtered.map((item) => item.id)).toEqual(["a1"]);
 });

 it("an empty due facet matches nothing", () => {
  const dated = makeAssignment({ ...DATED });
  expect(
   filterAssignments([dated], { ...NO_FILTER, due: [] }),
  ).toHaveLength(0);
 });

 it("a null due facet matches everything", () => {
  const dated = makeAssignment({ ...DATED });
  const undated = makeAssignment({ id: "a2", due_at: null });
  expect(filterAssignments([dated, undated], NO_FILTER)).toHaveLength(2);
 });
});

describe("status facet and the course allow-list", () => {
 it("the status facet is a plain OR", () => {
  const todo = makeAssignment({ id: "todo" });
  const done = makeAssignment({ id: "done", submitted: true });
  const filtered = filterAssignments([todo, done], {
   ...NO_FILTER,
   statuses: ["todo", "completed"],
  });
  expect(filtered.map((item) => item.id)).toEqual(["todo", "done"]);
 });

 it("an empty status facet matches nothing", () => {
  const dated = makeAssignment({ ...DATED });
  expect(
   filterAssignments([dated], { ...NO_FILTER, statuses: [] }),
  ).toHaveLength(0);
 });

 it("the course facet is an allow-list", () => {
  const math = makeAssignment({ id: "m", course_id: "c-math" });
  const physics = makeAssignment({ id: "p", course_id: "c-physics" });
  const filtered = filterAssignments([math, physics], {
   ...NO_FILTER,
   courses: ["c-math"],
  });
  expect(filtered.map((item) => item.id)).toEqual(["m"]);
 });

 it("facets are ANDed with each other", () => {
  const match = makeAssignment({ id: "m", course_id: "c-math", ...DATED });
  const wrongCourse = makeAssignment({
   id: "p",
   course_id: "c-physics",
   ...DATED,
  });
  const filtered = filterAssignments([match, wrongCourse], {
   statuses: ["todo"],
   due: ["has_due"],
   courses: ["c-math"],
  });
  expect(filtered.map((item) => item.id)).toEqual(["m"]);
 });
});

describe("facet counts", () => {
 const datedTodo = makeAssignment({ id: "a1", ...DATED });
 const datedDone = makeAssignment({
  id: "a2",
  ...DATED,
  submitted: true,
  graded: true,
 });
 const undatedTodo = makeAssignment({ id: "a3", due_at: null });
 const all = [datedTodo, datedDone, undatedTodo];

 it("counts each state against the same set, ignoring the state facet", () => {
  const counts = statusCounts(all, NO_FILTER);
  expect(counts).toEqual({ todo: 2, overdue: 0, completed: 1, graded: 1 });
 });

 it("status counts narrow once a due value is selected", () => {
  const counts = statusCounts(all, { ...NO_FILTER, due: ["no_due"] });
  expect(counts).toEqual({ todo: 1, overdue: 0, completed: 0, graded: 0 });
 });

 it("due counts ignore the due facet but honour the state facet", () => {
  const counts = dueCounts(all, { ...NO_FILTER, statuses: ["completed"] });
  expect(counts).toEqual({ has_due: 1, no_due: 0 });
 });

 it("counts respect the course allow-list", () => {
  const counts = statusCounts(all, { ...NO_FILTER, courses: ["other"] });
  expect(counts.todo).toBe(0);
 });
});

describe("pruneCourseSelection", () => {
 it("falls back to `all` when every saved course left the cache", () => {
  expect(pruneCourseSelection(["gone"], ["present"])).toBeNull();
 });

 it("keeps the surviving courses otherwise", () => {
  expect(pruneCourseSelection(["a", "b"], ["b", "c"])).toEqual(["b"]);
 });
});

describe("sortAssignments", () => {
 it("sorts invalid created_at as 0 instead of producing NaN", () => {
  const broken = makeAssignment({ id: "broken", created_at: "not-a-date" });
  const valid = makeAssignment({
   id: "valid",
   created_at: "2026-01-01T00:00:00",
  });
  expect(sortAssignments([broken, valid], "newest").map((a) => a.id)).toEqual([
   "valid",
   "broken",
  ]);
  expect(sortAssignments([broken, valid], "oldest").map((a) => a.id)).toEqual([
   "broken",
   "valid",
  ]);
 });

 it("sorts assignments without a due date last", () => {
  const undated = makeAssignment({ id: "undated", due_at: null });
  const later = makeAssignment({ id: "later", due_at: "2030-01-01T00:00:00" });
  const sooner = makeAssignment({
   id: "sooner",
   due_at: "2026-01-01T00:00:00",
  });
  expect(sortAssignments([undated, later, sooner], "due").map((a) => a.id)).toEqual(
   ["sooner", "later", "undated"],
  );
 });
});