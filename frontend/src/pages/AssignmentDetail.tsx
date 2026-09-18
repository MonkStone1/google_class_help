import { ArrowLeft, ExternalLink, Paperclip, RefreshCw } from "lucide-react";
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
import type { Submission } from "../types.ts";

/**
 * Dedicated assignment page (sections 8–12): full metadata, materials and the
 * submission list of every student, so a teacher does not have to open Google
 * Classroom just to inspect submissions.
 */
export function AssignmentDetail() {
  const { courseId = "", courseworkId = "" } = useParams<{
    courseId: string;
    courseworkId: string;
  }>();
  const { t } = useI18n();
  const detail = useResource(
    `course:${courseId}:work:${courseworkId}`,
    (signal) => api.getAssignmentDetail(courseId, courseworkId, signal),
  );

  const refresh = () => {
    invalidateResources(`course:${courseId}:work:${courseworkId}`);
    detail.refresh();
  };

  const data = detail.data;
  const due = parseDue(data?.due_at ?? null);

  return (
    <div className="page">
      <Link to={`/subjects/${courseId}`} className="back-link">
        <ArrowLeft size={15} /> {t("teacher.backToCourse")}
      </Link>

      <div className="page-header">
        <div>
          <div className="page-subtitle">
            <span className="subject-chip">{data?.course_name ?? ""}</span>
          </div>
          <h1>{data?.title ?? t("assignment.title")}</h1>
        </div>
        <div className="page-header-actions">
          {detail.updatedAt ? (
            <span className="updated-label">
              {t("teacher.updated", {
                time: new Date(detail.updatedAt).toLocaleTimeString(undefined, {
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

      {detail.loading && !data ? <SectionSkeleton rows={4} /> : null}
      {detail.error ? (
        <div className="alert alert-error">{detail.error}</div>
      ) : null}

      {data ? (
        <>
          <section className="card assignment-detail-card">
            <h2>{t("assignment.details")}</h2>
            <dl className="modal-details">
              <div>
                <dt>{t("modal.dueDate")}</dt>
                <dd>
                  {due ? formatDate(due) : t("modal.noDueDate")}
                  {due && formatTime(due)
                    ? ` ${t("modal.at", { time: formatTime(due) })}`
                    : ""}
                </dd>
              </div>
              <div>
                <dt>{t("modal.maxPoints")}</dt>
                <dd>{data.max_points ?? "—"}</dd>
              </div>
              <div>
                <dt>{t("assignment.createdAt")}</dt>
                <dd>
                  {data.created_at
                    ? formatDateTimeShort(parseDue(data.created_at))
                    : "—"}
                </dd>
              </div>
              <div>
                <dt>{t("assignment.updatedAt")}</dt>
                <dd>
                  {data.updated_at
                    ? formatDateTimeShort(parseDue(data.updated_at))
                    : "—"}
                </dd>
              </div>
              <div>
                <dt>{t("assignment.column.status")}</dt>
                <dd>{data.state ?? "—"}</dd>
              </div>
            </dl>

            {data.description ? (
              <div className="modal-description">
                <h3>{t("assignment.description")}</h3>
                <p>{data.description}</p>
              </div>
            ) : null}

            {data.materials.length > 0 ? (
              <div className="modal-materials">
                <h3>{t("modal.materials")}</h3>
                <ul>
                  {data.materials.map((material, index) => (
                    <li key={index}>
                      {material.url ? (
                        <a href={material.url} target="_blank" rel="noreferrer">
                          <Paperclip size={13} />{" "}
                          {material.title || material.url}
                        </a>
                      ) : (
                        <span>{material.title ?? "—"}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {data.alternate_link ? (
              <a
                className="button button-primary"
                href={data.alternate_link}
                target="_blank"
                rel="noreferrer"
              >
                <ExternalLink size={15} /> {t("card.openInClassroom")}
              </a>
            ) : null}
          </section>

          <section className="card">
            <h2>{t("teacher.assignment.stats")}</h2>
            <div className="status-counts">
              <span className="status-count">
                {t("assignment.stats.submitted")}:{" "}
                <strong>{data.status_counts.turned_in ?? 0}</strong>
              </span>
              <span className="status-count">
                {t("assignment.stats.graded")}:{" "}
                <strong>{data.status_counts.graded ?? 0}</strong>
              </span>
              <span className="status-count">
                {t("status.returned")}:{" "}
                <strong>{data.status_counts.returned ?? 0}</strong>
              </span>
              <span className="status-count">
                {t("assignment.stats.notSubmitted")}:{" "}
                <strong>{data.status_counts.not_submitted ?? 0}</strong>
              </span>
            </div>
          </section>

          <section>
            <h2>{t("assignment.submissions")}</h2>
            {data.submissions.length === 0 ? (
              <EmptyState title={t("assignment.noSubmissions")} />
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t("assignment.column.student")}</th>
                      <th>{t("assignment.column.status")}</th>
                      <th>{t("assignment.column.grade")}</th>
                      <th>{t("assignment.column.submitted")}</th>
                      <th>{t("modal.materials")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.submissions.map((submission) => (
                      <SubmissionRow
                        key={submission.student_id}
                        courseId={courseId}
                        submission={submission}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}

function SubmissionRow({
  courseId,
  submission,
}: {
  courseId: string;
  submission: Submission;
}) {
  const { t } = useI18n();
  const submitted = parseDue(submission.submitted_at);
  return (
    <tr>
      <td>
        <Link to={`/subjects/${courseId}/students/${submission.student_id}`}>
          {submission.student_name || submission.student_id}
        </Link>
      </td>
      <td>
        <SubmissionStatusBadge status={submission.status} />
      </td>
      <td>
        {submission.graded && submission.points !== null ? (
          <span className="matrix-grade">
            {submission.points} / {submission.max_points ?? "?"}
            {submission.percent === null ? "" : ` · ${submission.percent}%`}
          </span>
        ) : (
          <span className="matrix-muted">{t("assignment.notGraded")}</span>
        )}
      </td>
      <td>
        {submitted
          ? `${formatDateTimeShort(submitted)} ${formatTime(submitted)}`.trim()
          : "—"}
      </td>
      <td>
        {submission.attachments.length === 0 ? (
          "—"
        ) : (
          <ul className="attachment-list">
            {submission.attachments.map((attachment, index) => (
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
        )}
      </td>
    </tr>
  );
}
