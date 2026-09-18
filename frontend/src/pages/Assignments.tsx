import { ListChecks, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { AssignmentCard } from "../components/AssignmentCard.tsx";
import { AssignmentModal } from "../components/AssignmentModal.tsx";
import { FilterPanel } from "../components/FilterPanel.tsx";
import { EmptyState, SectionSkeleton } from "../components/Skeletons.tsx";
import { useCourses, useSync } from "../context/DataContext.tsx";
import { useSettings } from "../context/SettingsContext.tsx";
import { useI18n } from "../i18n.ts";
import {
  STATUS_FILTER_KEYS,
  canonicalStatuses,
  filterAssignments,
  formatCourseFilter,
  formatStatusFilter,
  parseCourseFilter,
  parseStatusFilter,
  pruneCourseSelection,
  sameAssignmentsFilter,
  sortAssignments,
} from "../lib/assignmentFilters.ts";
import { cn } from "../lib/cn.ts";
import type {
  Assignment,
  AssignmentFilterStatus,
  AssignmentsFilter,
  SortKey,
} from "../types.ts";

export function Assignments() {
  const { assignments, courses } = useCourses();
  const { loading, error } = useSync();
  const { cardDensity, defaultSort, assignmentsFilter, update } = useSettings();
  const { t } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();
  const [selected, setSelected] = useState<Assignment | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);

  const sortKey = (searchParams.get("sort") ?? defaultSort) as SortKey;

  const courseIds = useMemo(
    () => courses.map((course) => course.id),
    [courses],
  );

  // A link may carry a filter (`/assignments?status=overdue` from the sidebar);
  // when it does, it wins. Otherwise the last saved filter is used, so leaving
  // the page and coming back keeps the panel as it was (ADR-0013).
  const urlHasFilter =
    searchParams.has("status") || searchParams.has("courses");
  const urlFilter = useMemo<AssignmentsFilter>(
    () => ({
      statuses: parseStatusFilter(searchParams.get("status")),
      courses: parseCourseFilter(searchParams.get("courses"), courseIds),
    }),
    [searchParams, courseIds],
  );
  const savedFilter = useMemo<AssignmentsFilter>(
    () => ({
      statuses: assignmentsFilter.statuses,
      courses: pruneCourseSelection(assignmentsFilter.courses, courseIds),
    }),
    [assignmentsFilter, courseIds],
  );

  const activeFilter = urlHasFilter ? urlFilter : savedFilter;
  const statuses = activeFilter.statuses;
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

  const resetFilters = () => applyFilter({ statuses: null, courses: null });

  const filtersActive = statuses !== null || selectedCourses !== null;

  const visible = useMemo(
    () =>
      sortAssignments(filterAssignments(assignments, activeFilter), sortKey),
    [assignments, activeFilter, sortKey],
  );

  if (loading) {
    return (
      <div className="page">
        <h1>{t("assignments.title")}</h1>
        <SectionSkeleton rows={6} />
      </div>
    );
  }

  return (
    <div className="page">
      <h1>{t("assignments.title")}</h1>
      {error ? <div className="alert alert-warning">{error}</div> : null}

      <div className="filter-bar">
        <div className="filter-bar-end">
          <button
            type="button"
            className={cn("filter-button", filtersActive && "active")}
            onClick={() => setPanelOpen(true)}
            aria-haspopup="dialog"
            aria-expanded={panelOpen}
          >
            <SlidersHorizontal size={15} />
            {t("filter.open")}
            {filtersActive ? (
              <span className="filter-dot" aria-hidden="true" />
            ) : null}
          </button>
          <label className="sort-select">
            {t("filter.sortBy")}
            <select
              value={sortKey}
              onChange={(event) => setSort(event.target.value)}
            >
              <option value="due">{t("sort.due")}</option>
              <option value="priority">{t("sort.priority")}</option>
              <option value="grade">{t("sort.grade")}</option>
              <option value="newest">{t("sort.newest")}</option>
              <option value="oldest">{t("sort.oldest")}</option>
            </select>
          </label>
        </div>
      </div>

      {filtersActive && assignments.length > 0 ? (
        <div className="filter-summary">
          {t("filter.showing", {
            shown: visible.length,
            total: assignments.length,
          })}
        </div>
      ) : null}

      {visible.length === 0 ? (
        <EmptyState
          icon={<ListChecks size={28} />}
          title={
            assignments.length === 0
              ? t("assignments.empty")
              : t("filter.noMatch")
          }
          subtitle={
            assignments.length === 0 ? t("assignments.emptyHint") : undefined
          }
          action={
            filtersActive && assignments.length > 0 ? (
              <button type="button" className="button" onClick={resetFilters}>
                {t("filter.reset")}
              </button>
            ) : undefined
          }
        />
      ) : (
        <div className="assignment-grid">
          {visible.map((assignment) => (
            <AssignmentCard
              key={assignment.id}
              assignment={assignment}
              density={cardDensity}
              onOpen={setSelected}
            />
          ))}
        </div>
      )}

      <FilterPanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        courses={courses}
        statuses={statuses}
        selectedCourses={selectedCourses}
        onToggleStatus={toggleStatus}
        onSelectAllStatuses={() =>
          applyFilter({ ...activeFilter, statuses: null })
        }
        onClearAllStatuses={() =>
          applyFilter({ ...activeFilter, statuses: [] })
        }
        onToggleCourse={toggleCourse}
        onSelectAllCourses={() =>
          applyFilter({ ...activeFilter, courses: null })
        }
        onClearAllCourses={() => applyFilter({ ...activeFilter, courses: [] })}
        onReset={resetFilters}
      />

      <AssignmentModal
        assignment={selected}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}
