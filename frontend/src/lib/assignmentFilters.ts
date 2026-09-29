/**
 * Pure helpers for the assignments filter (status + due date + course facets).
 *
 * Every facet shares one convention, which is what makes the panel easy to
 * explain: `null` means "the facet is off, everything matches", an empty array
 * means "nothing is selected, nothing matches", and a non-empty array is the
 * explicit allow-list. Values inside one facet are a union (OR); the facets
 * themselves are combined with AND.
 *
 * React-free on purpose: the same status semantics are used by the assignments
 * page and by the subject detail page, and the parsing stays testable in
 * isolation (same split as `lib/search.ts`, ADR-0012).
 */

import type {
 Assignment,
 AssignmentDueFilter,
 AssignmentFilterStatus,
 AssignmentStatusFilter,
 AssignmentsFilter,
 SortKey,
} from "../types.ts";
import { parseDue, createdTime } from "../dates.ts";

/** Facet order in the filter panel: the four states the dashboard offers. */
export const STATUS_FILTER_KEYS: readonly AssignmentFilterStatus[] = [
 "todo",
 "overdue",
 "completed",
 "graded",
];

/** Facet order of the separate due-date filter. */
export const DUE_FILTER_KEYS: readonly AssignmentDueFilter[] = [
 "has_due",
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

/** The same canonical order for the due-date facet. */
export function canonicalDue(
 values: readonly AssignmentDueFilter[],
): AssignmentDueFilter[] {
 return DUE_FILTER_KEYS.filter((key) => values.includes(key));
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
 return canonicalStatuses(
  [...STATUS_FILTER_KEYS].filter((k) => wanted.has(k)),
 );
}

/** `null` drops the `status` parameter; `""` encodes "nothing selected". */
export function formatStatusFilter(
 values: readonly AssignmentFilterStatus[] | null,
): string | null {
 return values === null ? null : canonicalStatuses(values).join(",");
}

/**
 * `?due=no_due` → `["no_due"]`, with the same `null` / `[]` convention as the
 * status facet.
 */
export function parseDueFilter(
 raw: string | null,
): AssignmentDueFilter[] | null {
 if (raw === null || raw.trim() === "all") {
  return null;
 }
 const wanted = new Set(splitList(raw));
 return canonicalDue([...DUE_FILTER_KEYS].filter((k) => wanted.has(k)));
}

/** `null` drops the `due` parameter; `""` encodes "nothing selected". */
export function formatDueFilter(
 values: readonly AssignmentDueFilter[] | null,
): string | null {
 return values === null ? null : canonicalDue(values).join(",");
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

/** Defensive read of the due-date facet saved in localStorage. */
export function normalizeDueFilter(
 value: AssignmentDueFilter[] | null | undefined,
): AssignmentDueFilter[] | null {
 if (!Array.isArray(value)) {
  return null;
 }
 const keys = value.filter((key) => DUE_FILTER_KEYS.includes(key));
 return rescueFullyDropped(value, canonicalDue(keys));
}

/** Defensive read of the value persisted in localStorage (ADR-0006). */
export function normalizeCourseFilter(
 value: string[] | null | undefined,
): string[] | null {
 return Array.isArray(value) ? [...value] : null;
}

/** Defensive read of the collapsed grade groups saved in localStorage. */
export function normalizeCollapsedCourses(value: unknown): string[] {
 if (!Array.isArray(value)) {
  return [];
 }
 return [
  ...new Set(
   value.filter((id): id is string => typeof id === "string" && id.length > 0),
  ),
 ];
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