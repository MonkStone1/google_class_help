import { describe, expect, it } from "vitest";

import type { Assignment, Course } from "../types.ts";
import { courseSubtitle, searchAll } from "./search.ts";

function makeAssignment(overrides: Partial<Assignment> = {}): Assignment {
  return {
    id: "a1",
    course_id: "c1",
    course_name: "Math",
    title: "Homework",
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

function makeCourse(overrides: Partial<Course> = {}): Course {
  return {
    id: "c1",
    name: "Mathematics",
    description: null,
    section: null,
    room: null,
    course_state: null,
    teachers: ["Ada Lovelace"],
    role: "STUDENT",
    student_count: 0,
    total_assignments: 0,
    todo_count: 0,
    overdue_count: 0,
    graded_count: 0,
    average_grade: null,
    ...overrides,
  };
}

describe("searchAll", () => {
  it("returns nothing for an empty or whitespace query", () => {
    expect(searchAll([makeAssignment()], [makeCourse()], "   ").hits).toEqual([]);
  });

  it("matches tokens with AND semantics regardless of order", () => {
    const result = searchAll(
      [makeAssignment({ title: "Math homework" })],
      [],
      "homework math",
    );
    expect(result.assignments).toBe(1);
  });

  it("requires every token to match something", () => {
    const result = searchAll(
      [makeAssignment({ title: "Math homework" })],
      [],
      "math physics",
    );
    expect(result.assignments).toBe(0);
  });

  it("ranks a title match above a weaker field match", () => {
    const titleMatch = makeAssignment({ id: "title", title: "Essay" });
    const described = makeAssignment({
      id: "described",
      title: "Reading",
      description: "essay outline",
    });
    const ids = searchAll([described, titleMatch], [], "essay").hits.map((hit) =>
      hit.type === "assignment" ? hit.assignment.id : "course",
    );
    expect(ids).toEqual(["title", "described"]);
  });

  it("sorts equal-scoring assignments by due date", () => {
    const later = makeAssignment({
      id: "later",
      due_at: "2030-01-01T00:00:00",
    });
    const sooner = makeAssignment({
      id: "sooner",
      due_at: "2026-01-01T00:00:00",
    });
    const ids = searchAll([later, sooner], [], "homework").hits.map((hit) =>
      hit.type === "assignment" ? hit.assignment.id : "course",
    );
    expect(ids).toEqual(["sooner", "later"]);
  });

  it("finds courses by teacher name", () => {
    const result = searchAll(
      [],
      [makeCourse({ teachers: ["Grace Hopper"] })],
      "hopper",
    );
    expect(result.courses).toBe(1);
  });
});

describe("courseSubtitle", () => {
  it("joins teachers, section and room, skipping blanks", () => {
    expect(
      courseSubtitle(
        makeCourse({ teachers: ["Ada"], section: "1A", room: "   " }),
      ),
    ).toBe("Ada · 1A");
  });
});