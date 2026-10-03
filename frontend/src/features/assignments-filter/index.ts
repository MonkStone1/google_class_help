/**
 * The public API of `features/assignments-filter` — one filter, applied the
 * same way everywhere.
 *
 * Three layers, and the folder keeps them apart on purpose: `filters.ts` says
 * what "overdue" means and how a set of statuses normalizes, `useSorted` is
 * the React binding, and `ui/FilterPanel` is the control. A page takes all
 * three from here; the sorting rule is shared because the assignments list, the
 * course page and the search results must never disagree about it.
 */

export {
  dueCounts,
  filterAssignments,
  matchesDue,
  matchesStatus,
  pruneCourseSelection,
  sameAssignmentsFilter,
  sortAssignments,
  statusCounts,
} from "./filters.ts";
export { useSortedAssignments } from "./useSortedAssignments.ts";
export { FilterPanel } from "./ui/FilterPanel.tsx";