import { ArrowLeft, GraduationCap } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api.ts";
import { SubmissionStatusBadge } from "../components/Badges.tsx";
import { EmptyState, SectionSkeleton } from "../components/Skeletons.tsx";
import { formatDateTimeShort, parseDue } from "../dates.ts";
import { useI18n } from "../i18n.ts";
import { useResource } from "../lib/resource.ts";
import type { SubmissionCell } from "../types.ts";

/**
 * Dedicated teacher grades view (section 6): students as rows, assignments as
 * columns. Every cell is derived on the backend from the Classroom submission
 * state, so "not submitted", "returned" and "graded" are never conflated.
 */
export function TeacherGrades() {
  const { courseId = "" } = useParams<{ courseId: string }>();
  const { t } = useI18n();
  const grades = useResource(`course:${courseId}:grades`, (signal) =>
    api.getCourseGrades(courseId, signal),
  );

  const data = grades.data;

  return (
    <div className="page">
      <Link to={`/subjects/${courseId}`} className="back-link">
        <ArrowLeft size={15} /> {t("teacher.backToCourse")}
      </Link>

      <div className="page-header">
        <div>
          <h1>{t("teacher.grades.title")}</h1>
          <div className="page-subtitle">
            {data?.course_name ?? ""}
            {data?.class_average === null || data?.class_average === undefined
              ? ""
              : ` · ${t("teacher.grades.classAverage", {
                  value: data.class_average,
                })}`}
          </div>
        </div>
        <div className="page-header-actions">
          {grades.updatedAt ? (
            <span className="updated-label">
              {t("teacher.updated", {
                time: new Date(grades.updatedAt).toLocaleTimeString(undefined, {
                  hour: "2-digit",
                  minute: "2-digit",
                }),
              })}
            </span>
          ) : null}
        </div>
      </div>

      {grades.loading && !data ? <SectionSkeleton rows={5} /> : null}
      {grades.error ? (
        <div className="alert alert-error">{grades.error}</div>
      ) : null}

      {data && (data.rows.length === 0 || data.assignments.length === 0) ? (
        <EmptyState
          icon={<GraduationCap size={28} />}
          title={t("teacher.grades.empty")}
        />
      ) : null}

      {data && data.rows.length > 0 && data.assignments.length > 0 ? (
        <div className="table-wrap grades-matrix">
          <table className="data-table">
            <thead>
              <tr>
                <th className="sticky-col">
                  {t("teacher.grades.studentColumn")}
                </th>
                {data.assignments.map((column) => (
                  <th key={column.assignment_id}>
                    <Link
                      to={`/subjects/${courseId}/assignments/${column.assignment_id}`}
                    >
                      {column.title}
                    </Link>
                    {column.due_at ? (
                      <div className="matrix-col-sub">
                        {formatDateTimeShort(parseDue(column.due_at))}
                      </div>
                    ) : null}
                  </th>
                ))}
                <th>{t("teacher.grades.averageColumn")}</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row.student.id}>
                  <td className="sticky-col">
                    <Link
                      to={`/subjects/${courseId}/students/${row.student.id}`}
                    >
                      {row.student.full_name || row.student.id}
                    </Link>
                  </td>
                  {row.cells.map((cell) => (
                    <td key={cell.coursework_id}>
                      <GradeCell cell={cell} />
                    </td>
                  ))}
                  <td className="matrix-average">
                    {row.average_percent === null
                      ? "—"
                      : `${row.average_percent}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

function GradeCell({ cell }: { cell: SubmissionCell }) {
  const { t } = useI18n();
  if (cell.graded && cell.points !== null) {
    return (
      <span className="matrix-grade">
        {cell.points} / {cell.max_points ?? "?"}
        {cell.percent === null ? "" : ` · ${cell.percent}%`}
      </span>
    );
  }
  if (cell.status === "not_submitted") {
    return <span className="matrix-muted">{t("status.not_submitted")}</span>;
  }
  return <SubmissionStatusBadge status={cell.status} />;
}
