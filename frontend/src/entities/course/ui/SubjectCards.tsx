import { ChevronRight, UserRound } from "lucide-react";
import type { ReactNode } from "react";

import { useI18n } from "../../../shared/i18n/index.ts";
import type { Course } from "../../../shared/types/index.ts";

/**
 * One course as a card.
 *
 * `wrap` is how the card is opened, passed in rather than decided here. A card
 * that imported `react-router-dom` would make the domain layer decide WHERE a
 * subject lives, and it is exactly that knowledge `entities/` must not have
 * (ADR-0040 guardrail #4). The caller owns the navigation; this file owns how a
 * course reads.
 */
export function SubjectCard({
    course,
    wrap,
}: {
    course: Course;
    wrap: (content: ReactNode) => ReactNode;
}) {
  const { t } = useI18n();
  return (
    <>
      {wrap(
        <>
          <div className="subject-card-top">
            <h3>{course.name}</h3>
            {course.role === "TEACHER" ? (
              <span className="badge badge-role">{t("teacher.role")}</span>
            ) : null}
            <ChevronRight size={18} className="subject-card-chevron" />
          </div>
          {course.teachers.length > 0 ? (
            <div className="subject-card-teachers">
              <UserRound size={14} />
              {course.teachers.join(", ")}
            </div>
          ) : null}
          <div className="subject-card-stats">
            {course.role === "TEACHER" ? (
              <>
                <span>
                  {t("teacher.studentsCount", { count: course.student_count })}
                </span>
                <span>
                  {t("teacher.assignmentsCount", {
                    count: course.total_assignments,
                  })}
                </span>
              </>
            ) : (
              <>
                <span>
                  {t("subject.section.assignments", {
                    count: course.total_assignments,
                  })}
                </span>
                <span className={course.todo_count > 0 ? "text-warning" : ""}>
                  {t("subject.section.todo", { count: course.todo_count })}
                </span>
                <span className={course.overdue_count > 0 ? "text-danger" : ""}>
                  {t("subject.section.overdue", {
                    count: course.overdue_count,
                  })}
                </span>
              </>
            )}
            {course.average_grade === null ? null : (
              <span className="subject-card-average">
                {t("subject.avg", { value: course.average_grade })}
              </span>
            )}
          </div>
        </>,
      )}
    </>
  );
}
