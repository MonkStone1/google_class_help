import { ArrowLeft, ExternalLink, RefreshCw } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api.ts";
import { SubmissionStatusBadge } from "../components/Badges.tsx";
import { EmptyState, SectionSkeleton } from "../components/Skeletons.tsx";
import {
  formatDate,
  formatDateTimeShort,
  formatTime,
  parseDue,
} from "../dates.ts";
import { useI18n } from "../i18n.ts";
import { invalidateResources, useResource } from "../lib/resource.ts";
import type { StudentGradeItem } from "../types.ts";

/**
 * One student's coursework and submission state inside a teacher course
 * (section 7): Course → Grades → Student.
 */
export function StudentGrades() {
  const { courseId = "", studentId = "" } = useParams<{
    courseId: string;
    studentId: string;
  }>();
  const { t } = useI18n();
  const grades = useResource(
    `course:${courseId}:student:${studentId}`,
    (signal) => api.getStudentGrades(courseId, studentId, signal),
  );

  const refresh = () => {
    invalidateResources(`course:${courseId}:student:${studentId}`);
    grades.refresh();
  };

  const data = grades.data;

  return (
    <div className="page">
      <Link to={`/subjects/${courseId}/grades`} className="back-link">
        <ArrowLeft size={15} /> {t("teacher.backToGrades")}
      </Link>

      <div className="page-header">
        <div>
          <h1>
            {t("teacher.studentGrades", {
              name: data?.student?.full_name || studentId,
            })}
          </h1>
          <div className="page-subtitle">
            {data?.course_name ?? ""}
            {data?.average_percent === null ||
            data?.average_percent === undefined
              ? ""
              : ` · ${t("teacher.grades.classAverage", {
                  value: data.average_percent,
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
          <button type="button" className="button" onClick={refresh}>
            <RefreshCw size={15} /> {t("teacher.refresh")}
          </button>
        </div>
      </div>

      {grades.loading && !data ? <SectionSkeleton rows={4} /> : null}
      {grades.error ? (
        <div className="alert alert-error">{grades.error}</div>
      ) : null}

      {data && data.items.length === 0 ? (
        <EmptyState title={t("teacher.noStudentItems")} />
      ) : null}

      {data && data.items.length > 0 ? (
        <ul className="student-grade-list">
          {data.items.map((item) => (
            <StudentGradeCard
              key={item.assignment_id}
              courseId={courseId}
              item={item}
            />
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function StudentGradeCard({
  courseId,
  item,
}: {
  courseId: string;
  item: StudentGradeItem;
}) {
  const { t } = useI18n();
  const due = parseDue(item.due_at);
  const submitted = parseDue(item.submitted_at);
  return (
    <li className="card student-grade-card">
      <div className="student-grade-head">
        <Link
          to={`/subjects/${courseId}/assignments/${item.assignment_id}`}
          className="student-grade-title"
        >
          {item.title}
        </Link>
        <SubmissionStatusBadge status={item.status} />
      </div>

      <div className="student-grade-meta">
        <span>
          {t("modal.dueDate")}:{" "}
          {due
            ? `${formatDate(due)} ${formatTime(due)}`.trim()
            : t("modal.noDueDate")}
        </span>
        <span>
          {t("modal.maxPoints")}: {item.max_points ?? "—"}
        </span>
        {item.graded && item.points !== null ? (
          <span className="student-grade-score">
            {item.points} / {item.max_points ?? "?"}
            {item.percent === null ? "" : ` · ${item.percent}%`}
          </span>
        ) : (
          <span className="matrix-muted">{t("assignment.notGraded")}</span>
        )}
        {submitted ? (
          <span>
            {t("assignment.column.submitted")}: {formatDateTimeShort(submitted)}{" "}
            {formatTime(submitted)}
          </span>
        ) : null}
        {item.late ? (
          <span className="badge badge-overdue">{t("badge.late")}</span>
        ) : null}
      </div>

      {item.attachments.length > 0 ? (
        <div className="student-grade-attachments">
          <span>{t("assignment.submissions")}:</span>
          <ul>
            {item.attachments.map((attachment, index) => (
              <li key={index}>
                {attachment.url ? (
                  <a href={attachment.url} target="_blank" rel="noreferrer">
                    {attachment.title || attachment.url}
                  </a>
                ) : (
                  <span>{attachment.title ?? "—"}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {item.alternate_link ? (
        <a
          className="card-link"
          href={item.alternate_link}
          target="_blank"
          rel="noreferrer"
        >
          <ExternalLink size={13} /> {t("card.openInClassroom")}
        </a>
      ) : null}
    </li>
  );
}
