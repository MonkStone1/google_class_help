import { AlertTriangle, CheckCircle2, CircleDashed, Clock } from "lucide-react";

import { useI18n } from "../../../shared/i18n/index.ts";
import type { I18nKey } from "../../../shared/i18n/index.ts";
import { cn } from "../../../shared/lib/index.ts";
import type { Assignment, Priority, SubmissionStatus } from "../../../shared/types/index.ts";

export function StatusBadge({ assignment }: { assignment: Assignment }) {
  const { t } = useI18n();
  if (assignment.is_overdue) {
    return (
      <span className="badge badge-overdue">
        <AlertTriangle size={13} /> {t("badge.overdue")}
      </span>
    );
  }
  if (assignment.submitted) {
    return (
      <span className="badge badge-done">
        <CheckCircle2 size={13} />{" "}
        {assignment.graded ? t("badge.graded") : t("badge.turnedIn")}
      </span>
    );
  }
  const due = parseDueForBadge(assignment.due_at);
  if (due?.toDateString() === new Date().toDateString()) {
    return (
      <span className="badge badge-today">
        <Clock size={13} /> {t("badge.dueToday")}
      </span>
    );
  }
  return (
    <span className="badge badge-todo">
      <CircleDashed size={13} /> {t("badge.todo")}
    </span>
  );
}

function parseDueForBadge(value: string | null): Date | null {
  if (!value) {
    return null;
  }
  const match = value.match(
    /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/,
  );
  if (!match) {
    return null;
  }
  const [, y, m, d, h, min, s] = match;
  return new Date(
    Number(y),
    Number(m) - 1,
    Number(d),
    Number(h),
    Number(min),
    Number(s),
  );
}

const PRIORITY_LABEL_KEY: Record<Priority, I18nKey> = {
  high: "badge.high",
  medium: "badge.medium",
  low: "badge.low",
};

export function PriorityBadge({ priority }: { priority: Priority }) {
  const { t } = useI18n();
  return (
    <span className={cn("badge", `badge-priority-${priority}`)}>
      {t(PRIORITY_LABEL_KEY[priority])}
    </span>
  );
}

export function GradeBadge({
  points,
  maxPoints,
}: {
  points: number | null;
  maxPoints: number | null;
}) {
  const { t } = useI18n();
  if (points === null) {
    return <span className="badge badge-muted">{t("badge.ungraded")}</span>;
  }
  const percent =
    maxPoints && maxPoints > 0 ? Math.round((points / maxPoints) * 100) : null;
  return (
    <span
      className={cn(
        "badge",
        percent !== null && percent >= 50
          ? "badge-grade-good"
          : "badge-grade-low",
      )}
    >
      {points} / {maxPoints ?? "?"}
      {percent === null ? "" : ` · ${percent}%`}
    </span>
  );
}

const SUBMISSION_STATUS_KEY: Record<SubmissionStatus, I18nKey> = {
  not_submitted: "status.not_submitted",
  turned_in: "status.turned_in",
  returned: "status.returned",
  graded: "status.graded",
};

/** Localized label key for a derived submission status (teacher views). */
export function submissionStatusKey(status: SubmissionStatus): I18nKey {
  return SUBMISSION_STATUS_KEY[status];
}

/** Canonical teacher-mode status badge: never contradicts a missing grade. */
export function SubmissionStatusBadge({
  status,
}: {
  status: SubmissionStatus;
}) {
  const { t } = useI18n();
  return (
    <span className={cn("badge", `badge-status-${status}`)}>
      {t(SUBMISSION_STATUS_KEY[status])}
    </span>
  );
}
