import { ListChecks, SlidersHorizontal, X } from "lucide-react";
import { useState } from "react";

import { AssignmentCard } from "../../../entities/assignment/index.ts";
import { AssignmentModal } from "../../../features/assignment-modal/index.ts";
import { FilterPanel } from "../../../features/assignments-filter/index.ts";
import { EmptyState, SectionSkeleton } from "../../../shared/ui/index.ts";
import { useCourses } from "../../../entities/course/index.ts";
import { useSync } from "../../../features/sync/index.ts";
import { useSettings } from "../../../shared/settings/index.ts";
import { useI18n } from "../../../shared/i18n/index.ts";
import { cn } from "../../../shared/lib/index.ts";
import type { Assignment } from "../../../shared/types/index.ts";
import { useAssignmentsFilter } from "./useAssignmentsFilter.ts";

/**
 * Every assignment the student is enrolled in, with the filter panel.
 *
 * The page is layout and list; the filter lives in `useAssignmentsFilter`
 * because it is two stores that have to agree (the saved settings and the URL)
 * plus the reconciliation between them, and that reconciliation is the same on
 * the course page. What is left here is what only this screen decides: which
 * card density to draw with, and what happens when a card is opened.
 */
export function Assignments() {
  const { assignments, courses } = useCourses();
  const { loading, error } = useSync();
  const { cardDensity } = useSettings();
  const { t } = useI18n();
  const [selected, setSelected] = useState<Assignment | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);

  const {
    filterableCourses,
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
    setAllStatuses,
    setAllDue,
    setAllCourses,
    setSort,
    resetFilters,
  } = useAssignmentsFilter(assignments, courses);

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

      {chips.length > 0 ? (
        <div className="filter-chips">
          {chips.map((chip) => (
            <button
              key={chip.key}
              type="button"
              className="filter-chip"
              onClick={chip.onRemove}
              aria-label={t("filter.removeChip", { value: chip.label })}
            >
              {chip.label}
              <X size={12} />
            </button>
          ))}
        </div>
      ) : null}

      {filtersActive && assignments.length > 0 ? (
        <div className="filter-summary" aria-live="polite">
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
        courses={filterableCourses}
        statuses={statuses}
        due={due}
        selectedCourses={selectedCourses}
        statusCounts={perStatus}
        dueCounts={perDue}
        onToggleStatus={toggleStatus}
        onSelectAllStatuses={() => setAllStatuses(null)}
        onClearAllStatuses={() => setAllStatuses([])}
        onToggleDue={toggleDue}
        onSelectAllDue={() => setAllDue(null)}
        onClearAllDue={() => setAllDue([])}
        onToggleCourse={toggleCourse}
        onSelectAllCourses={() => setAllCourses(null)}
        onClearAllCourses={() => setAllCourses([])}
        onReset={resetFilters}
      />

      <AssignmentModal
        assignment={selected}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}