import { ArrowLeft, ExternalLink, Paperclip } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { api } from "../shared/api/index.ts";
import { SubmissionStatusBadge } from "../entities/assignment/ui/Badges.tsx";
import { EmptyState, SectionSkeleton } from "../shared/ui/Skeletons.tsx";
import {
 formatDate,
 formatDateTimeShort,
 formatTime,
 parseDue,
} from "../shared/lib/dates.ts";
import { useI18n } from "../shared/i18n/index.ts";
import { useResource } from "../shared/hooks/useResource.ts";
import type { StudentGradeItem } from "../shared/types/index.ts";

/**
 * One student's coursework and submission state inside a teacher course
 * (section 7): Course → Grades → Student.
 *
 * A course with many assignments used to render one tall card per item, so
 * finding a single grade meant a long scroll. The rows are now a compact table
 * — one line per assignment, with the state and the grade on the same line —
 * and the extra details (attachments, Classroom link) stay available without
 * inflating the height of every row.
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
      {data?.average_percent === null || data?.average_percent === undefined
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
    <div className="table-wrap student-grades-table">
     <table className="data-table">
      <thead>
       <tr>
        <th>{t("assignment.title")}</th>
        <th>{t("modal.dueDate")}</th>
        <th>{t("assignment.column.status")}</th>
        <th>{t("assignment.column.grade")}</th>
        <th>{t("assignment.column.submitted")}</th>
       </tr>
      </thead>
      <tbody>
       {data.items.map((item) => (
        <StudentGradeRow
         key={item.assignment_id}
         courseId={courseId}
         item={item}
        />
       ))}
      </tbody>
     </table>
    </div>
   ) : null}
  </div>
 );
}

function StudentGradeRow({
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
  <tr>
   <td>
    <div className="student-grade-cell">
     <Link
      to={`/subjects/${courseId}/assignments/${item.assignment_id}`}
      className="student-grade-title"
     >
      {item.title}
     </Link>
     <div className="student-grade-links">
      {item.attachments.length > 0 ? (
       <details className="student-grade-attachments">
        <summary>
         <Paperclip size={12} />{" "}
         {t("studentGrades.attachments", {
          count: item.attachments.length,
         })}
        </summary>
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
       </details>
      ) : null}
      {item.alternate_link ? (
       <a
        className="student-grade-classroom"
        href={item.alternate_link}
        target="_blank"
        rel="noreferrer"
        aria-label={t("card.openInClassroom")}
        title={t("card.openInClassroom")}
       >
        <ExternalLink size={13} />
       </a>
      ) : null}
     </div>
    </div>
   </td>
   <td className="matrix-muted">
    {due ? formatDate(due) : t("modal.noDueDate")}
    {due && formatTime(due) ? ` ${formatTime(due)}` : ""}
   </td>
   <td>
    <div className="student-grade-status">
     <SubmissionStatusBadge status={item.status} />
     {item.late ? (
      <span className="badge badge-overdue">{t("badge.late")}</span>
     ) : null}
    </div>
   </td>
   <td>
    {item.graded && item.points !== null ? (
     <span className="matrix-grade">
      {item.points} / {item.max_points ?? "?"}
      {item.percent === null ? "" : ` · ${item.percent}%`}
     </span>
    ) : (
     <span className="matrix-muted">{t("assignment.notGraded")}</span>
    )}
   </td>
   <td className="matrix-muted">
    {submitted
     ? `${formatDateTimeShort(submitted)} ${formatTime(submitted)}`.trim()
     : "—"}
   </td>
  </tr>
 );
}