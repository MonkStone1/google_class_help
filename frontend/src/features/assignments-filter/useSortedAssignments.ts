import { useMemo } from "react";

import { createdTime, parseDue, percentOf } from "../../shared/lib/index.ts";
import type { Assignment, SortKey } from "../../shared/types/index.ts";

/**
 * The list ordering of the assignments screens, memoised.
 *
 * This is a HOOK and not a plain function because the two pages that use it
 * re-render on every filter change, and sorting a few hundred assignments on
 * each keystroke is wasted work. `useMemo` on `[assignments, sortKey]` keeps the
 * cost to the moments the list actually changes.
 *
 * It lives in the feature rather than in `shared/lib/` for the same reason the
 * dates module lost its copy: "what order should this list be in" is a product
 * decision about one screen, not a mechanism another screen might reuse. A
 * second screen that wants a different order writes its own — which is the
 * difference between a policy and a setting.
 */
export function useSortedAssignments(
    assignments: Assignment[],
    sortKey: SortKey,
): Assignment[] {
    return useMemo(() => {
        const copy = [...assignments];
        const priorityRank = { high: 0, medium: 1, low: 2 } as const;
        const due = (a: Assignment) => parseDue(a.due_at)?.getTime() ?? Infinity;
        switch (sortKey) {
            case "priority":
                copy.sort(
                    (a, b) =>
                        priorityRank[a.priority] - priorityRank[b.priority] ||
                        due(a) - due(b),
                );
                break;
            case "grade":
                copy.sort((a, b) => (percentOf(b) ?? -1) - (percentOf(a) ?? -1));
                break;
            case "newest":
                copy.sort(
                    (a, b) =>
                        createdTime(b.created_at) - createdTime(a.created_at),
                );
                break;
            case "oldest":
                copy.sort(
                    (a, b) =>
                        createdTime(a.created_at) - createdTime(b.created_at),
                );
                break;
            default:
                copy.sort((a, b) => due(a) - due(b));
        }
        return copy;
    }, [assignments, sortKey]);
}