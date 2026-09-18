import { describe, expect, it } from "vitest";

import type { Assignment } from "../types.ts";
import {
  canonicalStatuses,
  filterAssignments,
  formatStatusFilter,
  parseStatusFilter,
  pruneCourseSelection,
  sortAssignments,
} from "./assignmentFilters.ts";

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

describe("matchesPanelStatuses semantics", () => {
  it("no_due checked alone selects nothing", () => {
    const undated = makeAssignment({ due_at: null });
    expect(
      filterAssignments([undated], { statuses: ["no_due"], courses: null }),
    ).toHaveLength(0);
  });

  it("undated todo task shows when no_due + todo are checked", () => {
    const undated = makeAssignment({ due_at: null });
    expect(
      filterAssignments([undated], {
        statuses: ["no_due", "todo"],
        courses: null,
      }),
    ).toHaveLength(1);
  });

  it("no_due alone does not select a dated task", () => {
    const dated = makeAssignment({ due_at: "2026-01-01T12:00:00" });
    expect(
      filterAssignments([dated], { statuses: ["no_due"], courses: null }),
    ).toHaveLength(0);
  });

  it("a dated task still matches through its own checked state", () => {
    // `no_due` is only an extra condition for undated tasks (ADR-0013):
    // a dated todo task selected with `todo` is shown regardless of it.
    const dated = makeAssignment({ due_at: "2026-01-01T12:00:00" });
    expect(
      filterAssignments([dated], {
        statuses: ["no_due", "todo"],
        courses: null,
      }),
    ).toHaveLength(1);
  });

  it("a null status facet matches everything", () => {
    const dated = makeAssignment({ due_at: "2026-01-01T12:00:00" });
    const undated = makeAssignment({ id: "a2", due_at: null });
    expect(
      filterAssignments([dated, undated], { statuses: null, courses: null }),
    ).toHaveLength(2);
  });

  it("an empty status facet matches nothing", () => {
    const dated = makeAssignment({ due_at: "2026-01-01T12:00:00" });
    expect(
      filterAssignments([dated], { statuses: [], courses: null }),
    ).toHaveLength(0);
  });

  it("the course facet is an allow-list", () => {
    const math = makeAssignment({ id: "m", course_id: "c-math" });
    const physics = makeAssignment({ id: "p", course_id: "c-physics" });
    const filtered = filterAssignments([math, physics], {
      statuses: null,
      courses: ["c-math"],
    });
    expect(filtered.map((item) => item.id)).toEqual(["m"]);
  });
});

describe("status filter parsing", () => {
  it("canonicalizes to the panel facet order", () => {
    expect(canonicalStatuses(["no_due", "todo"])).toEqual(["todo", "no_due"]);
  });

  it("treats null and legacy `all` as the off facet", () => {
    expect(parseStatusFilter(null)).toBeNull();
    expect(parseStatusFilter("all")).toBeNull();
  });

  it("keeps a present-but-empty value as an empty selection", () => {
    expect(parseStatusFilter("zzz")).toEqual([]);
    expect(formatStatusFilter([])).toBe("");
  });

  it("drops unknown values and formats canonically", () => {
    expect(parseStatusFilter("graded,todo,zzz")).toEqual(["todo", "graded"]);
    expect(formatStatusFilter(["graded", "todo"])).toBe("todo,graded");
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
    const valid = makeAssignment({ id: "valid", created_at: "2026-01-01T00:00:00" });
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
