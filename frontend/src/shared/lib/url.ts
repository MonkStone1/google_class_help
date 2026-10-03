/**
 * URL <-> facet conversion for the assignments filter (ADR-0013).
 *
 * Split out of the filtering itself because the two answer different questions:
 * this file is about the SHAPE OF A LINK — which values may appear in a URL,
 * in which order, and what their absence means — and it is the half that must
 * behave identically for the assignments page and the subject detail page.
 * Keeping it in `shared/lib/` also means a caller can round-trip a URL without
 * pulling in the whole filter model.
 *
 * The convention every function follows:
 * - `null` = the facet is off, and the parameter is DROPPED from the URL;
 * - `""` = nothing is selected, which is a real state worth sharing;
 * - a present-but-empty or fully unrecognised value therefore means "nothing
 *   matches", never "everything", so a stale link cannot quietly widen a list.
 *
 * The facet KEYS live here rather than in the filter feature, because they are
 * what a URL is allowed to carry: the filter module needs them to test a
 * selection, and `shared/` may not import upward to borrow them.
 */

import type {
    AssignmentDueFilter,
    AssignmentFilterStatus,
} from "../types/index.ts";

/** Facet values in the canonical order, so URLs stay diff-friendly. */
export const STATUS_FILTER_KEYS: readonly AssignmentFilterStatus[] = [
    "todo",
    "overdue",
    "completed",
    "graded",
];

/** The separate due-date facet. */
export const DUE_FILTER_KEYS: readonly AssignmentDueFilter[] = [
    "has_due",
    "no_due",
];

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

/** `"todo,overdue"` → `["todo", "overdue"]`, order-insensitive, de-duplicated. */
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

/** Keeps only ids the cache still knows, so a stale link cannot filter to void. */
function knownOnly(
    values: readonly string[],
    knownIds: readonly string[],
): string[] {
    return knownIds.filter((id) => values.includes(id));
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
        [...STATUS_FILTER_KEYS].filter((key) => wanted.has(key)),
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
    return canonicalDue([...DUE_FILTER_KEYS].filter((key) => wanted.has(key)));
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
 * dropped, and a selection that went fully stale falls back to "all" instead of
 * an empty list, which would look like a broken page rather than a filter.
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

/**
 * Defensive read of the values persisted in localStorage (ADR-0006).
 *
 * They sit here rather than in the filter feature because the SETTINGS STORE
 * needs them and the store is below every layer: a value written by an older
 * build, or hand-edited in devtools, must not be able to put a key the panel
 * does not know into the state. Membership filtering is the runtime guard —
 * junk keys simply drop out.
 */
export function normalizeStatusFilter(
    value: AssignmentFilterStatus[] | null | undefined,
): AssignmentFilterStatus[] | null {
    if (!Array.isArray(value)) {
        return null;
    }
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

/** Defensive read of the course allow-list saved in localStorage (ADR-0006). */
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