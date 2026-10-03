import { CalendarDays, ExternalLink, Paperclip } from "lucide-react";
import type { ReactNode } from "react";

import { useI18n } from "../../../shared/i18n/index.ts";
import { cn } from "../../../shared/lib/index.ts";
import {
  formatDateTimeShort,
  formatTime,
  parseDue,
  relativeDayLabel,
} from "../../../shared/lib/index.ts";
import type { Assignment } from "../../../shared/types/index.ts";
import { GradeBadge, PriorityBadge, StatusBadge } from "./Badges.tsx";

type Props = {
  assignment: Assignment;
  density?: "compact" | "comfortable";
  onOpen?: (assignment: Assignment) => void;
  /**
   * How the card opens, when it is a navigation target at all: the caller wraps
   * the content and supplies the class. Teacher courses pass this to open the
   * dedicated assignment page (section 8) instead of a modal; the dashboard
   * passes `onOpen` and gets a button.
   */
  wrap?: (content: ReactNode, className: string) => ReactNode;
};

export function AssignmentCard({
  assignment,
  density = "comfortable",
  onOpen,
  wrap,
}: Props) {
  const due = parseDue(assignment.due_at);
  const { t } = useI18n();
  const label = relativeDayLabel(due);
  const isTeacher = assignment.role === "TEACHER";

  const content = (
    <>
      <div className="assignment-card-top">
        <span className="subject-chip">{assignment.course_name}</span>
        {isTeacher ? (
          <span className="badge badge-muted">
            {t("teacher.assignment.submittedCounter", {
              submitted: assignment.submission_count,
              total: assignment.student_count,
            })}
          </span>
        ) : (
          <StatusBadge assignment={assignment} />
        )}
      </div>
      <div className="assignment-card-title">{assignment.title}</div>
      {density !== "compact" && assignment.description ? (
        <div className="assignment-card-desc">
          {assignment.description.length > 160
            ? `${assignment.description.slice(0, 160)}…`
            : assignment.description}
        </div>
      ) : null}
      <div className="assignment-card-meta">
        <span
          className={cn("meta-due", assignment.is_overdue && "meta-overdue")}
        >
          <CalendarDays size={14} />
          {label
            ? t(label.key, label.count ? { count: label.count } : undefined)
            : t("date.noDueDate")}
          {due ? ` · ${formatDateTimeShort(due)}` : ""}
          {formatTime(due) ? ` · ${formatTime(due)}` : ""}
        </span>
        <span className="meta-right">
          {assignment.materials.length > 0 ? (
            <span className="meta-inline">
              <Paperclip size={13} /> {assignment.materials.length}
            </span>
          ) : null}
          {isTeacher ? (
            <span className="badge badge-muted">
              {t("teacher.assignment.gradedCounter", {
                graded: assignment.graded_count,
              })}
            </span>
          ) : (
            <>
              <PriorityBadge priority={assignment.priority} />
              {assignment.graded || assignment.submitted ? (
                <GradeBadge
                  points={assignment.points}
                  maxPoints={assignment.max_points}
                />
              ) : null}
            </>
          )}
        </span>
      </div>
      {!wrap && assignment.alternate_link ? (
        <a
          className="card-link"
          href={assignment.alternate_link}
          target="_blank"
          rel="noreferrer"
          onClick={(event) => event.stopPropagation()}
        >
          <ExternalLink size={13} /> {t("card.openInClassroom")}
        </a>
      ) : null}
    </>
  );

  const className = cn(
    "card assignment-card",
    !isTeacher && `priority-${assignment.priority}`,
    density === "compact" && "compact",
    wrap && "assignment-card-link",
  );

  // How the card is opened is the caller's decision: a teacher course navigates
  // to the dedicated page, the dashboard opens a modal. Deciding it here would
  // put `react-router-dom` in the domain layer (ADR-0040 guardrail #4), which is
  // the same reason `SubjectCard` takes a `wrap` callback.
  if (wrap) {
    return wrap(content, className);
  }

  return (
    <button
      type="button"
      className={className}
      onClick={() => onOpen?.(assignment)}
    >
      {content}
    </button>
  );
}
