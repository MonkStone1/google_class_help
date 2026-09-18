import { CheckCheck, Square, X } from "lucide-react";
import { useEffect } from "react";

import { useI18n } from "../i18n.ts";
import type { I18nKey } from "../i18n.ts";
import { STATUS_FILTER_KEYS } from "../lib/assignmentFilters.ts";
import { cn } from "../lib/cn.ts";
import type { AssignmentFilterStatus, Course } from "../types.ts";

const STATUS_LABELS: Record<AssignmentFilterStatus, I18nKey> = {
  todo: "filter.todo",
  overdue: "filter.overdue",
  completed: "filter.completed",
  graded: "filter.graded",
  no_due: "filter.noDue",
};

type Props = {
  open: boolean;
  onClose: () => void;
  courses: Course[];
  /** `null` = every status is included; `[]` = none is. */
  statuses: AssignmentFilterStatus[] | null;
  /** `null` = every course is included; `[]` = none is. */
  selectedCourses: string[] | null;
  onToggleStatus: (status: AssignmentFilterStatus) => void;
  onSelectAllStatuses: () => void;
  onClearAllStatuses: () => void;
  onToggleCourse: (courseId: string) => void;
  onSelectAllCourses: () => void;
  onClearAllCourses: () => void;
  onReset: () => void;
};

function OptionRow({
  label,
  count,
  selected,
  onToggle,
}: {
  label: string;
  count?: number;
  selected: boolean;
  onToggle: () => void;
}) {
  return (
    <label className={cn("filter-option", selected && "selected")}>
      <input type="checkbox" checked={selected} onChange={onToggle} />
      <span className="filter-option-label">{label}</span>
      {count === undefined ? null : (
        <span className="filter-option-count">{count}</span>
      )}
    </label>
  );
}

function SectionTools({
  onSelectAll,
  onClearAll,
}: {
  onSelectAll: () => void;
  onClearAll: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="filter-section-tools">
      <button
        type="button"
        className="filter-round-button"
        aria-label={t("filter.selectAll")}
        title={t("filter.selectAll")}
        onClick={onSelectAll}
      >
        <CheckCheck size={14} />
      </button>
      <button
        type="button"
        className="filter-round-button"
        aria-label={t("filter.clearAll")}
        title={t("filter.clearAll")}
        onClick={onClearAll}
      >
        <Square size={12} />
      </button>
    </div>
  );
}

export function FilterPanel({
  open,
  onClose,
  courses,
  statuses,
  selectedCourses,
  onToggleStatus,
  onSelectAllStatuses,
  onClearAllStatuses,
  onToggleCourse,
  onSelectAllCourses,
  onClearAllCourses,
  onReset,
}: Props) {
  const { t } = useI18n();

  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  const statusCount =
    statuses === null ? STATUS_FILTER_KEYS.length : statuses.length;
  const courseCount =
    selectedCourses === null ? courses.length : selectedCourses.length;
  const isStatusSelected = (status: AssignmentFilterStatus) =>
    statuses === null || statuses.includes(status);
  const isCourseSelected = (courseId: string) =>
    selectedCourses === null || selectedCourses.includes(courseId);
  const hasFilters = statuses !== null || selectedCourses !== null;

  return (
    <>
      <button
        type="button"
        className="filter-drawer-backdrop"
        aria-label={t("modal.close")}
        onClick={onClose}
      />

      <aside
        className="filter-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={t("filter.title")}
      >
        <header className="filter-drawer-header">
          <h2>{t("filter.title")}</h2>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label={t("modal.close")}
          >
            <X size={18} />
          </button>
        </header>

        <div className="filter-drawer-body">
          <section className="filter-section">
            <div className="filter-section-head">
              <h3>{t("filter.byStatus")}</h3>
              <span className="filter-section-count">
                {statusCount}/{STATUS_FILTER_KEYS.length}
              </span>
              <SectionTools
                onSelectAll={onSelectAllStatuses}
                onClearAll={onClearAllStatuses}
              />
            </div>
            <div className="filter-options">
              {STATUS_FILTER_KEYS.map((status) => (
                <OptionRow
                  key={status}
                  label={t(STATUS_LABELS[status])}
                  selected={isStatusSelected(status)}
                  onToggle={() => onToggleStatus(status)}
                />
              ))}
            </div>
          </section>

          <section className="filter-section">
            <div className="filter-section-head">
              <h3>{t("filter.byCourse")}</h3>
              <span className="filter-section-count">
                {courseCount}/{courses.length}
              </span>
              {courses.length === 0 ? null : (
                <SectionTools
                  onSelectAll={onSelectAllCourses}
                  onClearAll={onClearAllCourses}
                />
              )}
            </div>

            {courses.length === 0 ? (
              <p className="filter-empty">{t("filter.coursesEmpty")}</p>
            ) : (
              <div className="filter-options filter-options-scroll">
                {courses.map((course) => (
                  <OptionRow
                    key={course.id}
                    label={course.name}
                    count={course.total_assignments}
                    selected={isCourseSelected(course.id)}
                    onToggle={() => onToggleCourse(course.id)}
                  />
                ))}
              </div>
            )}
          </section>
        </div>

        <footer className="filter-drawer-footer">
          <button
            type="button"
            className="button"
            onClick={onReset}
            disabled={!hasFilters}
          >
            {t("filter.reset")}
          </button>
        </footer>
      </aside>
    </>
  );
}
