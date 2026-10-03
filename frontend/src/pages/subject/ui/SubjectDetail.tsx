import { ArrowLeft } from "lucide-react";
import { useMemo, useState, useEffect } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { AssignmentCard } from "../../../entities/assignment/index.ts";
import { AssignmentModal } from "../../../features/assignment-modal/index.ts";
import { EmptyState, SectionSkeleton } from "../../../shared/ui/index.ts";
import { TeacherCourse } from "./TeacherCourse.tsx";
import { useCourses } from "../../../entities/course/index.ts";
import { useSync } from "../../../features/sync/index.ts";
import { useSettings } from "../../../shared/settings/index.ts";
import { useI18n } from "../../../shared/i18n/index.ts";
import type { I18nKey } from "../../../shared/i18n/index.ts";
import { matchesStatus, sortAssignments } from "../../../features/assignments-filter/index.ts";
import type { Assignment, AssignmentStatusFilter, SortKey } from "../../../shared/types/index.ts";

const STATUS_TABS: Array<{
  key: AssignmentStatusFilter | "all";
  labelKey: I18nKey;
}> = [
  { key: "all", labelKey: "filter.all" },
  { key: "todo", labelKey: "filter.todo" },
  { key: "overdue", labelKey: "filter.overdue" },
  { key: "completed", labelKey: "filter.completed" },
  { key: "graded", labelKey: "filter.graded" },
  { key: "ungraded", labelKey: "filter.ungraded" },
];

const SORT_OPTIONS: Array<{ key: SortKey; labelKey: I18nKey }> = [
  { key: "due", labelKey: "sort.due" },
  { key: "priority", labelKey: "sort.priority" },
  { key: "grade", labelKey: "sort.grade" },
  { key: "newest", labelKey: "sort.newest" },
  { key: "oldest", labelKey: "sort.oldest" },
];

export function SubjectDetail() {
  const { courseId } = useParams<{ courseId: string }>();
  const { courses, assignments } = useCourses();
  const { loading } = useSync();
  const { cardDensity, defaultSort, subjectTab, update } = useSettings();
  const { t } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();
  const [selected, setSelected] = useState<Assignment | null>(null);

  const assignmentParam = searchParams.get("assignment");

  // Deep link from the global search: ?assignment=<id> opens that card.
  useEffect(() => {
    if (!assignmentParam) {
      return;
    }
    const match = assignments.find((item) => item.id === assignmentParam);
    if (match) {
      setSelected(match);
    }
  }, [assignmentParam, assignments]);

  // URL parameters win when present (shareable links); otherwise the last
  // used tab and sort are restored from the settings store (ADR-0006).
  const tab = (searchParams.get("tab") ?? subjectTab) as
    | AssignmentStatusFilter
    | "all";
  const sortKey = (searchParams.get("sort") ?? defaultSort) as SortKey;

  const course = courses.find((c) => c.id === courseId);

  const visible = useMemo(() => {
    const mine = assignments.filter((a) => a.course_id === courseId);
    const filtered = mine.filter((a) => matchesStatus(a, tab));
    return sortAssignments(filtered, sortKey);
  }, [assignments, courseId, tab, sortKey]);

  if (loading) {
    return (
      <div className="page">
        <SectionSkeleton rows={5} />
      </div>
    );
  }

  if (!course) {
    return (
      <div className="page">
        <EmptyState
          title={t("subject.notFound")}
          subtitle={t("subject.notFoundHint")}
        />
      </div>
    );
  }

  // Teacher course: class-wide view (all assignments, roster, grades). The
  // student view below is untouched for student courses.
  if (course.role === "TEACHER") {
    return <TeacherCourse course={course} />;
  }

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    next.set(key, value);
    setSearchParams(next, { replace: true });
  };

  const closeModal = () => {
    setSelected(null);
    if (!searchParams.has("assignment")) {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete("assignment");
    setSearchParams(next, { replace: true });
  };

  return (
    <div className="page">
      <Link to="/subjects" className="back-link">
        <ArrowLeft size={15} /> {t("subject.back")}
      </Link>

      <div className="page-header">
        <div>
          <h1>{course.name}</h1>
          <div className="page-subtitle">
            {course.teachers.length > 0
              ? course.teachers.join(", ")
              : t("subject.noTeacher")}
            {course.room ? ` · ${course.room}` : ""}
          </div>
          {course.description ? (
            <p className="course-description">{course.description}</p>
          ) : null}
          <div className="subject-detail-stats">
            <span>
              {t("subject.assignments", { count: course.total_assignments })}
            </span>
            <span>{t("subject.todo", { count: course.todo_count })}</span>
            <span className={course.overdue_count > 0 ? "text-danger" : ""}>
              {t("subject.overdue", { count: course.overdue_count })}
            </span>
            {course.average_grade === null ? null : (
              <span>{t("subject.avg", { value: course.average_grade })}</span>
            )}
          </div>
        </div>
      </div>

      <div className="filter-bar">
        <div className="tabs">
          {STATUS_TABS.map((item) => (
            <button
              key={item.key}
              type="button"
              className={tab === item.key ? "tab active" : "tab"}
              onClick={() => {
                setParam("tab", item.key);
                update({ subjectTab: item.key });
              }}
            >
              {t(item.labelKey)}
            </button>
          ))}
        </div>
        <label className="sort-select">
          {t("filter.sortBy")}
          <select
            value={sortKey}
            onChange={(event) => {
              setParam("sort", event.target.value);
              update({ defaultSort: event.target.value as SortKey });
            }}
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.key} value={option.key}>
                {t(option.labelKey)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {visible.length === 0 ? (
        <EmptyState title={t("subject.noMatch")} />
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

      <AssignmentModal assignment={selected} onClose={closeModal} />
    </div>
  );
}
