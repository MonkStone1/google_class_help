/**
 * Global search over the locally cached Classroom data.
 *
 * Pure and dependency-free so the ranking is easy to reason about and reuse:
 * the top bar feeds it the assignments and courses from DataContext and
 * renders whatever comes back, in the order returned.
 */

import { parseDue } from "../dates.ts";
import type { Assignment, Course } from "../types.ts";

export type SearchHit =
  | { type: "assignment"; assignment: Assignment }
  | { type: "course"; course: Course };

export type SearchResults = {
  hits: SearchHit[];
  assignments: number;
  courses: number;
};

/** Weights decide which field dominates when a query matches several. */
const WEIGHT = {
  assignmentTitle: 6,
  assignmentCourse: 2,
  assignmentDescription: 1,
  courseName: 6,
  courseTeacher: 2,
  courseMeta: 1,
} as const;

const MAX_ASSIGNMENTS = 8;
const MAX_COURSES = 5;

type Field = { value: string | null | undefined; weight: number };

export const EMPTY_RESULTS: SearchResults = {
  hits: [],
  assignments: 0,
  courses: 0,
};

function normalize(value: string): string {
  return value.toLocaleLowerCase().replace(/\s+/g, " ").trim();
}

/**
 * Scores a single field against the already-normalized query.
 * Returns 0 when the field does not contain the query at all.
 */
function scoreField(
  raw: string | null | undefined,
  query: string,
  weight: number,
): number {
  if (!raw) {
    return 0;
  }
  const text = normalize(raw);
  if (!text) {
    return 0;
  }
  const index = text.indexOf(query);
  if (index === -1) {
    return 0;
  }
  // Whole-field > word-start > anywhere inside the field.
  if (text === query) {
    return weight * 3;
  }
  const boundary =
    index === 0 || /[\s\-_/·.,()[\]]/.test(text[index - 1] ?? "");
  return weight * (boundary ? 2 : 1);
}

function courseScore(course: Course, tokens: string[]): number {
  return scoreTokens(
    [
      { value: course.name, weight: WEIGHT.courseName },
      { value: course.teachers.join(" "), weight: WEIGHT.courseTeacher },
      { value: course.section, weight: WEIGHT.courseMeta },
      { value: course.room, weight: WEIGHT.courseMeta },
      { value: course.description, weight: WEIGHT.courseMeta },
    ],
    tokens,
  );
}

function assignmentScore(assignment: Assignment, tokens: string[]): number {
  return scoreTokens(
    [
      { value: assignment.title, weight: WEIGHT.assignmentTitle },
      { value: assignment.course_name, weight: WEIGHT.assignmentCourse },
      { value: assignment.description, weight: WEIGHT.assignmentDescription },
    ],
    tokens,
  );
}

/**
 * Every token must match at least one field (AND semantics, order-independent),
 * so "homework math" still finds "Math homework". Each field can satisfy
 * several tokens, so "math homework" also works.
 */
function scoreTokens(fields: Field[], tokens: string[]): number {
  let total = 0;
  for (const token of tokens) {
    let best = 0;
    for (const field of fields) {
      const score = scoreField(field.value, token, field.weight);
      if (score > best) {
        best = score;
      }
    }
    if (best === 0) {
      return 0;
    }
    total += best;
  }
  return total;
}

function dueTime(assignment: Assignment): number {
  return parseDue(assignment.due_at)?.getTime() ?? Infinity;
}

export function searchAll(
  assignments: Assignment[],
  courses: Course[],
  rawQuery: string,
): SearchResults {
  const tokens = normalize(rawQuery).split(" ").filter(Boolean);
  if (tokens.length === 0) {
    return EMPTY_RESULTS;
  }

  const assignmentHits = assignments
    .map((assignment) => ({
      assignment,
      score: assignmentScore(assignment, tokens),
    }))
    .filter((hit) => hit.score > 0)
    .sort(
      (a, b) =>
        b.score - a.score ||
        dueTime(a.assignment) - dueTime(b.assignment) ||
        a.assignment.title.localeCompare(b.assignment.title),
    )
    .slice(0, MAX_ASSIGNMENTS)
    .map<SearchHit>((hit) => ({
      type: "assignment",
      assignment: hit.assignment,
    }));

  const courseHits = courses
    .map((course) => ({ course, score: courseScore(course, tokens) }))
    .filter((hit) => hit.score > 0)
    .sort(
      (a, b) => b.score - a.score || a.course.name.localeCompare(b.course.name),
    )
    .slice(0, MAX_COURSES)
    .map<SearchHit>((hit) => ({ type: "course", course: hit.course }));

  return {
    hits: [...assignmentHits, ...courseHits],
    assignments: assignmentHits.length,
    courses: courseHits.length,
  };
}

/** Human-readable subtitle shown under a course result. */
export function courseSubtitle(course: Course): string {
  return [course.teachers.join(", "), course.section, course.room]
    .filter((part) => part && part.trim().length > 0)
    .join(" · ");
}
