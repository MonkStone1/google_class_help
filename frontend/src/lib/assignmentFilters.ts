/**
 * Pure helpers for the assignments filter (status + course facets).
 *
 * Both facets share one convention, which is what makes the panel easy to
 * explain: `null` means "the facet is off, everything matches", an empty array
 * means "nothing is selected, nothing matches", and a non-empty array is the
 * explicit allow-list.
 *
 * React-free on purpose: the same status semantics are used by the assignments
 * page and by the subject detail page, and the parsing stays testable in
 * isolation (same split as `lib/search.ts`, ADR-0012).
 */

import type {
 Assignment,
 AssignmentFilterStatus,
 AssignmentStatusFilter,
 AssignmentsFilter,
 SortKey,
} from "../types.ts";
import { parseDue, createdTime } from "../dates.ts";

/** Facet order in the filter panel: the five states the dashboard offers. */
export const STATUS_FILTER_KEYS: readonly AssignmentFilterStatus[] = [
 "todo",
 "overdue",
 "completed",
 "graded",
 "no_due",
];

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
  case "no_due":
   return !assignment.due_at;
  default:
   return true;
 }
}

/**
 * Panel-level matching for the status facet (ADR-0013).
 *
 * `matchesStatus` treats the states as overlapping unions, which is fine for
 * the subject page tabs but not for the panel: an undated task that is not
 * submitted matches both `todo` and `no_due`, so unchecking only one of them
 * would leave the task visible through the other. Inside the panel `no_due` is
 * therefore a **required extra condition** for undated tasks, and a dated task
 * never matches `no_due`:
 *
 * - dated tasks: at least one of the checked `todo|overdue|completed|graded`;
 * - undated tasks: `no_due` checked **and** at least one of the checked
 *   `todo|overdue|completed|graded` (its own state must be selected too).
 *
 * Consequence: `no_due` checked alone selects nothing — undated tasks still
 * need their submission state checked as well.
 */
function matchesPanelStatuses(
 assignment: Assignment,
 statuses: readonly AssignmentFilterStatus[],
): boolean {
 const selected = new Set(statuses);
 const stateMatches = (
  ["todo", "overdue", "completed", "graded"] as const
 ).some((status) => selected.has(status) && matchesStatus(assignment, status));
 if (!assignment.due_at) {
  return selected.has("no_due") && stateMatches;
 }
 return stateMatches;
}

/** Applies both facets: statuses are a union (OR), courses an allow-list.
 *  `no_due` is a required extra condition — see {@link matchesPanelStatuses}. */
export function filterAssignments(
 assignments: readonly Assignment[],
 filter: AssignmentsFilter,
): Assignment[] {
 return assignments.filter(
  (assignment) =>
   (filter.statuses === null ||
    matchesPanelStatuses(assignment, filter.statuses)) &&
   (filter.courses === null || filter.courses.includes(assignment.course_id)),
 );
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

function splitList(raw: string): string[] {
 const seen = new Set<string>();
 for (const part of raw.split(",")) {
  const value = part.trim();
  if (value && value !== "all") {
   seen.add(value);
  }
 }
 return [...seen];
}

function knownOnly(
 values: readonly string[],
 knownIds: readonly string[],
): string[] {
 return knownIds.filter((id) => values.includes(id));
}

/** Facet values in the canonical facet order, so URLs stay diff-friendly. */
export function canonicalStatuses(
 values: readonly AssignmentFilterStatus[],
): AssignmentFilterStatus[] {
 return STATUS_FILTER_KEYS.filter((key) => values.includes(key));
}

/**
 * `?status=todo,overdue` → `["todo", "overdue"]`.
 *
 * `null` (no parameter, or the legacy `status=all`) means "every status";
 * a present-but-empty or fully unknown value means "nothing matches", exactly
 * like the course facet.
 */
export function parseStatusFilter(
 raw: string | null,
): AssignmentFilterStatus[] | null {
 if (raw === null || raw.trim() === "all") {
  return null;
 }
 const wanted = new Set(splitList(raw));
 return canonicalStatuses([...STATUS_FILTER_KEYS].filter((k) => wanted.has(k)));
}

/** `null` drops the `status` parameter; `""` encodes "nothing selected". */
export function formatStatusFilter(
 values: readonly AssignmentFilterStatus[] | null,
): string | null {
 return values === null ? null : canonicalStatuses(values).join(",");
}

/**
 * `?courses=<id>,<id>` → known ids only.
 *
 * Same convention as {@link parseStatusFilter}; ids that are no longer in the
 * cache are ignored, so a stale link cannot produce an unexplainable empty list.
 */
export function parseCourseFilter(
 raw: string | null,
 knownCourseIds: readonly string[],
): string[] | null {
 if (raw === null || raw.trim() === "all") {
  return null;
 }
 return knownOnly(splitList(raw), knownCourseIds);
}

/** `null` drops the `courses` parameter; `""` encodes "nothing selected". */
export function formatCourseFilter(
 values: readonly string[] | null,
): string | null {
 return values === null ? null : values.join(",");
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
 * dropped, and a selection that went fully stale falls back to "all" instead of
 * an empty list, which would look like a broken page rather than a filter.
 */
export function pruneCourseSelection(
 values: readonly string[] | null,
 knownCourseIds: readonly string[],
): string[] | null {
 if (values === null) {
  return null;
 }
 return rescueFullyDropped(values, knownOnly(values, knownCourseIds));
}

/** Defensive read of the value persisted in localStorage (ADR-0006). */
export function normalizeStatusFilter(
 value: AssignmentFilterStatus[] | null | undefined,
): AssignmentFilterStatus[] | null {
 if (!Array.isArray(value)) {
  return null;
 }
 // Membership filtering is the runtime guard: junk keys simply drop out.
 const keys = value.filter((key) => STATUS_FILTER_KEYS.includes(key));
 return rescueFullyDropped(value, canonicalStatuses(keys));
}

/** Defensive read of the value persisted in localStorage (ADR-0006). */
export function normalizeCourseFilter(
 value: string[] | null | undefined,
): string[] | null {
 return Array.isArray(value) ? [...value] : null;
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
  sameList(left.courses, right.courses)
 );
}
