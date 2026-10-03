import { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { useSettings } from "../../../shared/settings/index.ts";
import { useI18n } from "../../../shared/i18n/index.ts";
import type { I18nKey } from "../../../shared/i18n/index.ts";
import {
  dueCounts,
  filterAssignments,
  pruneCourseSelection,
  sameAssignmentsFilter,
  sortAssignments,
  statusCounts,
} from "../../../features/assignments-filter/index.ts";
import {
  DUE_FILTER_KEYS,
  STATUS_FILTER_KEYS,
  canonicalDue,
  canonicalStatuses,
  formatCourseFilter,
  formatDueFilter,
  formatStatusFilter,
  parseCourseFilter,
  parseDueFilter,
  parseStatusFilter,
} from "../../../shared/lib/index.ts";
import type {
  Assignment,
  AssignmentDueFilter,
  AssignmentFilterStatus,
  AssignmentsFilter,
  Course,
  SortKey,
} from "../../../shared/types/index.ts";

const STATUS_LABELS: Record<AssignmentFilterStatus, I18nKey> = {
  todo: "filter.todo",
  overdue: "filter.overdue",
  completed: "filter.completed",
  graded: "filter.graded",
};

const DUE_LABELS: Record<AssignmentDueFilter, I18nKey> = {
  has_due: "filter.hasDue",
  no_due: "filter.noDue",
};

/** What the page needs from the filter, and nothing it does not. */
export type AssignmentsFilterBinding = {
  filterableCourses: Course[];
  activeFilter: AssignmentsFilter;
  statuses: AssignmentFilterStatus[] | null;
  due: AssignmentDueFilter[] | null;
  selectedCourses: string[] | null;
  sortKey: SortKey;
  filtersActive: boolean;
  visible: Assignment[];
  perStatus: Record<AssignmentFilterStatus, number>;
  perDue: Record<AssignmentDueFilter, number>;
  chips: { key: string; label: string; onRemove: () => void }[];
  toggleStatus: (status: AssignmentFilterStatus) => void;
  toggleDue: (value: AssignmentDueFilter) => void;
  toggleCourse: (courseId: string) => void;
  setAllStatuses: (value: AssignmentFilterStatus[] | null) => void;
  setAllDue: (value: AssignmentDueFilter[] | null) => void;
  setAllCourses: (value: string[] | null) => void;
  setSort: (value: string) => void;
  resetFilters: () => void;
};

export function useAssignmentsFilter(
  assignments: Assignment[],
  courses: Course[],
): AssignmentsFilterBinding {
  const { defaultSort, assignmentsFilter, update } = useSettings();
  const { t } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();

  const sortKey = (searchParams.get("sort") ?? defaultSort) as SortKey;

  // Courses the user teaches are not part of this page: their assignments
  // live on the course page, and /api/assignments never returns them. Listing
  // them here would offer a filter that can only ever produce an empty result.
  const filterableCourses = useMemo(
    () => courses.filter((course) => course.role === "STUDENT"),
    [courses],
  );
  const courseIds = useMemo(
    () => filterableCourses.map((course) => course.id),
    [filterableCourses],
  );

  // A link may carry a filter (`/assignments?status=overdue` from the sidebar);
  // when it does, it wins. Otherwise the last saved filter is used, so leaving
  // the page and coming back keeps the panel as it was (ADR-0013).
  const urlHasFilter =
    searchParams.has("status") ||
    searchParams.has("due") ||
    searchParams.has("courses");
  const urlFilter = useMemo<AssignmentsFilter>(
    () => ({
      statuses: parseStatusFilter(searchParams.get("status")),
      due: parseDueFilter(searchParams.get("due")),
      courses: parseCourseFilter(searchParams.get("courses"), courseIds),
    }),
    [searchParams, courseIds],
  );
  const savedFilter = useMemo<AssignmentsFilter>(
    () => ({
      statuses: assignmentsFilter.statuses,
      due: assignmentsFilter.due,
      courses: pruneCourseSelection(assignmentsFilter.courses, courseIds),
    }),
    [assignmentsFilter, courseIds],
  );

  const activeFilter = urlHasFilter ? urlFilter : savedFilter;
  const statuses = activeFilter.statuses;
  const due = activeFilter.due;
  const selectedCourses = activeFilter.courses;

  // A filter that arrived through a link is remembered as well, so the next
  // visit starts from it.
  useEffect(() => {
    if (!urlHasFilter || sameAssignmentsFilter(assignmentsFilter, urlFilter)) {
      return;
    }
    update({ assignmentsFilter: urlFilter });
  }, [urlHasFilter, urlFilter, assignmentsFilter, update]);

  // Every panel action writes both stores: settings, so the filter survives
  // navigation, and the URL, so the link stays accurate and shareable.
  const applyFilter = (next: AssignmentsFilter) => {
    update({ assignmentsFilter: next });
    setSearchParams(
      (current) => {
        const params = new URLSearchParams(current);
        const status = formatStatusFilter(next.statuses);
        if (status === null) {
          params.delete("status");
        } else {
          params.set("status", status);
        }
        const dueList = formatDueFilter(next.due);
        if (dueList === null) {
          params.delete("due");
        } else {
          params.set("due", dueList);
        }
        const courseList = formatCourseFilter(next.courses);
        if (courseList === null) {
          params.delete("courses");
        } else {
          params.set("courses", courseList);
        }
        return params;
      },
      { replace: true },
    );
  };

  const toggleStatus = (status: AssignmentFilterStatus) => {
    const current = statuses ?? STATUS_FILTER_KEYS;
    const next = current.includes(status)
      ? current.filter((item) => item !== status)
      : [...current, status];
    applyFilter({ ...activeFilter, statuses: canonicalStatuses(next) });
  };

  const toggleDue = (value: AssignmentDueFilter) => {
    const current = due ?? DUE_FILTER_KEYS;
    const next = current.includes(value)
      ? current.filter((item) => item !== value)
      : [...current, value];
    applyFilter({ ...activeFilter, due: canonicalDue(next) });
  };

  const toggleCourse = (courseId: string) => {
    const current = selectedCourses ?? courseIds;
    const next = current.includes(courseId)
      ? current.filter((id) => id !== courseId)
      : [...current, courseId];
    // Re-project onto the backend's course order so the URL stays canonical.
    applyFilter({
      ...activeFilter,
      courses: courseIds.filter((id) => next.includes(id)),
    });
  };

  // The chosen sort is remembered as the new default, so a reload or the next
  // visit reopens the list the way the user last arranged it (ADR-0006).
  const setSort = (value: string) => {
    update({ defaultSort: value as SortKey });
    setSearchParams(
      (current) => {
        const params = new URLSearchParams(current);
        params.set("sort", value);
        return params;
      },
      { replace: true },
    );
  };

  const resetFilters = () =>
    applyFilter({ statuses: null, due: null, courses: null });

  const filtersActive =
    statuses !== null || due !== null || selectedCourses !== null;

  const visible = useMemo(
    () =>
      sortAssignments(filterAssignments(assignments, activeFilter), sortKey),
    [assignments, activeFilter, sortKey],
  );

  // Each count answers "how many would I get with this value ticked?", so the
  // other facets are already applied and only the facet being counted is not.
  const perStatus = useMemo(
    () => statusCounts(assignments, activeFilter),
    [assignments, activeFilter],
  );
  const perDue = useMemo(
    () => dueCounts(assignments, activeFilter),
    [assignments, activeFilter],
  );

  // Chips mirror the explicit selections. A facet left at `null` means "all",
  // so it has nothing to show; an empty array means "nothing matches", which
  // the panel already states with its 0/N counter.
  const chips = useMemo(
    () => [
      ...(statuses ?? []).map((status) => ({
        key: `status:${status}`,
        label: t(STATUS_LABELS[status]),
        onRemove: () => toggleStatus(status),
      })),
      ...(due ?? []).map((value) => ({
        key: `due:${value}`,
        label: t(DUE_LABELS[value]),
        onRemove: () => toggleDue(value),
      })),
    ],
    // `t` is stable per language; the values drive the list itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [statuses, due, t],
  );

  return {
    filterableCourses,
    activeFilter,
    statuses,
    due,
    selectedCourses,
    sortKey,
    filtersActive,
    visible,
    perStatus,
    perDue,
    chips,
    toggleStatus,
    toggleDue,
    toggleCourse,
    setAllStatuses: (value) => applyFilter({ ...activeFilter, statuses: value }),
    setAllDue: (value) => applyFilter({ ...activeFilter, due: value }),
    setAllCourses: (value) => applyFilter({ ...activeFilter, courses: value }),
    setSort,
    resetFilters,
  };
}
