import { ExternalLink, X } from "lucide-react";

import { formatDate, formatTime, parseDue } from "../../shared/lib/dates.ts";
import type { I18nKey } from "../../shared/i18n/index.ts";
import { useI18n } from "../../shared/i18n/index.ts";
import type { Assignment } from "../../shared/types/index.ts";
import { GradeBadge, PriorityBadge, StatusBadge } from "../../entities/assignment/ui/Badges.tsx";

type Props = {
  assignment: Assignment | null;
  onClose: () => void;
};

const MATERIAL_LABEL_KEY: Record<string, I18nKey> = {
  drive: "modal.material.drive",
  link: "modal.material.link",
  form: "modal.material.form",
  youtube: "modal.material.youtube",
};

const SUBMISSION_STATE_KEY: Record<string, I18nKey> = {
  CREATED: "modal.notStarted",
  NEW: "modal.notStarted",
  TURNED_IN: "badge.turnedIn",
  RETURNED: "badge.graded",
  RECLAIMED_BY_STUDENT: "modal.reclaimed",
};

export function AssignmentModal({ assignment, onClose }: Props) {
  // Hooks must run unconditionally: the modal is rendered with a null
  // assignment while closed, so the early return has to come after them.
  const { t } = useI18n();
  if (!assignment) {
    return null;
  }
  const due = parseDue(assignment.due_at);
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={assignment.title}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <div className="subject-chip">{assignment.course_name}</div>
            <h2>{assignment.title}</h2>
          </div>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label={t("modal.close")}
          >
            <X size={18} />
          </button>
        </div>

        <div className="modal-badges">
          <StatusBadge assignment={assignment} />
          <PriorityBadge priority={assignment.priority} />
          {assignment.graded || assignment.submitted ? (
            <GradeBadge
              points={assignment.points}
              maxPoints={assignment.max_points}
            />
          ) : null}
          {assignment.late ? (
            <span className="badge badge-overdue">{t("badge.late")}</span>
          ) : null}
        </div>

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
            <dt>{t("modal.submissionState")}</dt>
            <dd>
              {t(
                SUBMISSION_STATE_KEY[assignment.submission_state ?? ""] ??
                  "modal.notStarted",
              )}
            </dd>
          </div>
          <div>
            <dt>{t("modal.maxPoints")}</dt>
            <dd>{assignment.max_points ?? "—"}</dd>
          </div>
        </dl>

        {assignment.description ? (
          <div className="modal-description">
            <h3>{t("modal.description")}</h3>
            <p>{assignment.description}</p>
          </div>
        ) : null}

        {assignment.materials.length > 0 ? (
          <div className="modal-materials">
            <h3>{t("modal.materials")}</h3>
            <ul>
              {assignment.materials.map((material, index) => (
                <li key={index}>
                  {material.url ? (
                    <a
                      href={material.url ?? "#"}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {material.title ||
                        t(
                          MATERIAL_LABEL_KEY[material.type ?? "link"] ??
                            "modal.material",
                        )}
                    </a>
                  ) : (
                    <span>{material.title || t("modal.material")}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="modal-actions">
          {assignment.alternate_link ? (
            <a
              className="button button-primary"
              href={assignment.alternate_link}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={15} /> {t("card.openInClassroom")}
            </a>
          ) : null}
          <button type="button" className="button" onClick={onClose}>
            {t("modal.close")}
          </button>
        </div>
      </div>
    </div>
  );
}
