import { GraduationCap } from "lucide-react";
import { useMemo } from "react";

import { EmptyState, SectionSkeleton } from "../components/Skeletons.tsx";
import { GradeHistorySparkline } from "../components/SubjectCards.tsx";
import { useCourses, useSync } from "../context/DataContext.tsx";
import { parseDue } from "../dates.ts";
import { useI18n } from "../i18n.ts";
import type { CourseGrades } from "../types.ts";

function historyPoints(course: CourseGrades) {
  return course.items
    .slice()
    .sort(
      (a, b) =>
        (parseDue(a.due_at)?.getTime() ?? 0) -
        (parseDue(b.due_at)?.getTime() ?? 0),
    )
    .map((item) => ({
      label: item.title,
      percent: item.percent ?? 0,
    }));
}

export function Grades() {
  const { courses, assignments } = useCourses();
  const { status, loading } = useSync();
  const { t } = useI18n();

  const grouped = useMemo(() => {
    // Derive per-course graded items from cached assignments.
    const byCourse = new Map<string, CourseGrades>();
    for (const course of courses) {
      byCourse.set(course.id, {
        course_id: course.id,
        course_name: course.name,
        average: course.average_grade,
        items: [],
      });
    }
    for (const assignment of assignments) {
      const group = byCourse.get(assignment.course_id);
      if (!group || !assignment.graded || assignment.points === null) {
        continue;
      }
      group.items.push({
        assignment_id: assignment.id,
        title: assignment.title,
        points: assignment.points,
        max_points: assignment.max_points,
        percent:
          assignment.max_points && assignment.max_points > 0
            ? Math.round((assignment.points / assignment.max_points) * 1000) /
              10
            : null,
        graded_at: null,
        due_at: assignment.due_at,
      });
    }
    return [...byCourse.values()].filter((group) => group.items.length > 0);
  }, [courses, assignments]);

  if (loading) {
    return (
      <div className="page">
        <h1>{t("grades.title")}</h1>
        <SectionSkeleton rows={4} />
      </div>
    );
  }

  return (
    <div className="page">
      <h1>{t("grades.title")}</h1>
      {status && status.average_grade !== null ? (
        <div className="alert alert-info">
          <GraduationCap size={16} />{" "}
          {t("grades.overall", { value: status.average_grade })}
        </div>
      ) : null}

      {grouped.length === 0 ? (
        <EmptyState
          icon={<GraduationCap size={28} />}
          title={t("grades.empty")}
          subtitle={t("grades.emptyHint")}
        />
      ) : (
        <div className="grades-list">
          {grouped.map((group) => (
            <section key={group.course_id} className="card grade-group">
              <div className="grade-group-header">
                <h2>{group.course_name}</h2>
                {group.average === null ? (
                  <span className="grade-average">{t("grades.noGrades")}</span>
                ) : (
                  <span className="grade-average">
                    {t("grades.average", { value: group.average })}
                  </span>
                )}
              </div>
              <GradeHistorySparkline percents={historyPoints(group)} />
              <ul className="grade-list">
                {group.items.map((item) => (
                  <li key={item.assignment_id} className="grade-row">
                    <span className="grade-title">{item.title}</span>
                    <span className="grade-value">
                      {item.points ?? "—"} / {item.max_points ?? "—"}
                      {item.percent === null ? "" : ` · ${item.percent}%`}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
