/**
 * The assignments filter model: what a facet MEANS (ADR-0013).
 *
 * Every facet shares one convention, which is what makes the panel easy to
 * explain: `null` means "the facet is off, everything matches", an empty array
 * means "nothing is selected, nothing matches", and a non-empty array is the
 * explicit allow-list. Values inside one facet are a union (OR); the facets
 * themselves are combined with AND.
 *
 * React-free on purpose: the same status semantics are used by the assignments
 * page and by the subject detail page, and the logic stays testable in
 * isolation (same split as `features/global-search/`, ADR-0012).
 *
 * The URL half — parsing `?status=…` and writing it back — lives in
 * `shared/lib/url.ts`, and so do the facet KEYS: they are exactly the values a
 * URL is allowed to carry, and `shared/` may not import upward to borrow them.
 * This file keeps the matching, the counting, the sorting and the defensive
 * reads of stored values.
 */

import type {
    Assignment,
    AssignmentDueFilter,
    AssignmentFilterStatus,
    AssignmentStatusFilter,
    AssignmentsFilter,
    SortKey,
} from "../../shared/types/index.ts";
import {
    canonicalDue,
    canonicalStatuses,
    DUE_FILTER_KEYS,
    STATUS_FILTER_KEYS,
} from "../../shared/lib/index.ts";
import { createdTime, parseDue } from "../../shared/lib/index.ts";

export { STATUS_FILTER_KEYS, DUE_FILTER_KEYS, canonicalDue, canonicalStatuses };

/** `all` means "the filter is off"; `ungraded` is only used by SubjectDetail. */
export function matchesStatus(
 assignment: Assignment,
 status: AssignmentStatusFilter | "all",
): boolean {
 switch (status) {
  case "todo":
   return !assignment.submitted;
  case "overdue":
   return assignment.is_overdue;
  case "completed":
   return assignment.submitted;
  case "graded":
   return assignment.graded;
  case "ungraded":
   return !assignment.graded;
  default:
   return true;
 }
}

/**
 * Due-date facet matching.
 *
 * Unlike the old `no_due`, both values are self-sufficient: each one describes
 * a complete set on its own, so `no_due` alone shows every undated assignment
 * regardless of its state. Choosing it together with a state narrows the list
 * to the intersection ("To do" + "No due date" = not submitted AND undated),
 * which falls out of the AND between the two facets — no special casing here.
 */
export function matchesDue(
 assignment: Assignment,
 due: AssignmentDueFilter,
): boolean {
 return due === "no_due" ? !assignment.due_at : Boolean(assignment.due_at);
}

/** One facet of the panel: a plain OR over the selected values. */
function matchesFacet<T extends string>(
 values: readonly T[],
 predicate: (value: T) => boolean,
): boolean {
 return values.some(predicate);
}

/**
 * Applies all three facets: states and due dates are unions (OR), the facets
 * themselves are ANDed, and courses stay an explicit allow-list.
 */
export function filterAssignments(
 assignments: readonly Assignment[],
 filter: AssignmentsFilter,
): Assignment[] {
 return assignments.filter(
  (assignment) =>
   (filter.statuses === null ||
    matchesFacet(filter.statuses, (status) =>
     matchesStatus(assignment, status),
    )) &&
   (filter.due === null ||
    matchesFacet(filter.due, (due) => matchesDue(assignment, due))) &&
   (filter.courses === null || filter.courses.includes(assignment.course_id)),
 );
}

/**
 * Number of assignments per state, computed with the *other* facets already
 * applied — that is what makes a panel count answer "what will I get if I also
 * tick this one?" instead of repeating the same number everywhere.
 */
export function statusCounts(
 assignments: readonly Assignment[],
 filter: AssignmentsFilter,
): Record<AssignmentFilterStatus, number> {
 const counts = {
  todo: 0,
  overdue: 0,
  completed: 0,
  graded: 0,
 } satisfies Record<AssignmentFilterStatus, number>;
 for (const assignment of assignments) {
  // The status facet itself is ignored here, so every state is counted
  // against the same set (due dates + courses).
  if (
   (filter.due !== null &&
    !matchesFacet(filter.due, (due) => matchesDue(assignment, due))) ||
   (filter.courses !== null && !filter.courses.includes(assignment.course_id))
  ) {
   continue;
  }
  for (const status of STATUS_FILTER_KEYS) {
   if (matchesStatus(assignment, status)) {
    counts[status] += 1;
   }
  }
 }
 return counts;
}

/** Number of assignments per due-date value, with status + courses applied. */
export function dueCounts(
 assignments: readonly Assignment[],
 filter: AssignmentsFilter,
): Record<AssignmentDueFilter, number> {
 const counts = {
  has_due: 0,
  no_due: 0,
 } satisfies Record<AssignmentDueFilter, number>;
 for (const assignment of assignments) {
  if (
   (filter.statuses !== null &&
    !matchesFacet(filter.statuses, (status) =>
     matchesStatus(assignment, status),
    )) ||
   (filter.courses !== null && !filter.courses.includes(assignment.course_id))
  ) {
   continue;
  }
  for (const due of DUE_FILTER_KEYS) {
   if (matchesDue(assignment, due)) {
    counts[due] += 1;
   }
  }
 }
 return counts;
}

/** Sorts a copy of the list; assignments without a due date sort last. */
export function sortAssignments(
 items: readonly Assignment[],
 sortKey: SortKey,
): Assignment[] {
 const due = (a: Assignment) => parseDue(a.due_at)?.getTime() ?? Infinity;
 const priorityRank = { high: 0, medium: 1, low: 2 } as const;
 const percent = (a: Assignment) =>
  a.points !== null && a.max_points ? (a.points / a.max_points) * 100 : -1;
 const sorted = [...items];
 switch (sortKey) {
  case "priority":
   sorted.sort(
    (a, b) =>
     priorityRank[a.priority] - priorityRank[b.priority] || due(a) - due(b),
   );
   break;
  case "grade":
   sorted.sort((a, b) => percent(b) - percent(a));
   break;
  case "newest":
   sorted.sort(
    (a, b) => createdTime(b.created_at) - createdTime(a.created_at),
   );
   break;
  case "oldest":
   sorted.sort(
    (a, b) => createdTime(a.created_at) - createdTime(b.created_at),
   );
   break;
  default:
   sorted.sort((a, b) => due(a) - due(b));
 }
 return sorted;
}

/** Keeps only ids the cache still knows, so a stale link cannot filter to void. */
function knownOnly(
    values: readonly string[],
    knownIds: readonly string[],
): string[] {
    return knownIds.filter((id) => values.includes(id));
}

/** A selection that lost every value falls back to "all", not to "none". */
function rescueFullyDropped<T extends string>(
 original: readonly T[],
 surviving: T[],
): T[] | null {
 return surviving.length === 0 && original.length > 0 ? null : surviving;
}

/**
 * Saved-selection variant of the pruning above: courses that left the cache are
 * dropped, and a selection that went fully stale falls back to "all" instead
 * of an empty list, which would look like a broken page rather than a filter.
 */
export function pruneCourseSelection(
 values: string[] | null,
 knownCourseIds: readonly string[],
): string[] | null {
 if (values === null) {
  return null;
 }
 return rescueFullyDropped(values, knownOnly(values, knownCourseIds));
}

function sameList(
 left: readonly string[] | null,
 right: readonly string[] | null,
): boolean {
 if (left === null || right === null) {
  return left === right;
 }
 return (
  left.length === right.length &&
  left.every((value, index) => value === right[index])
 );
}

/** Used to skip redundant writes into the settings store. */
export function sameAssignmentsFilter(
 left: AssignmentsFilter,
 right: AssignmentsFilter,
): boolean {
 return (
  sameList(left.statuses, right.statuses) &&
  sameList(left.due, right.due) &&
  sameList(left.courses, right.courses)
 );
}