import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  CircleDot,
  GraduationCap,
  PartyPopper,
  TrendingUp,
} from "lucide-react";
import { useMemo, useState } from "react";

import { AssignmentCard } from "../components/AssignmentCard.tsx";
import { StatCard } from "../shared/ui/StatCard.tsx";
import { EmptyState, SectionSkeleton } from "../shared/ui/Skeletons.tsx";
import { AssignmentModal } from "../components/AssignmentModal.tsx";
import { useCourses } from "../entities/course/index.ts";
import { useSync } from "../features/sync/index.ts";
import { useSettings } from "../shared/settings/SettingsProvider.tsx";
import { parseDue, startOfDay } from "../shared/lib/dates.ts";
import { useI18n } from "../shared/i18n/index.ts";
import type { Assignment } from "../shared/types/index.ts";

export function Dashboard() {
  const { assignments } = useCourses();
  const { status, loading, error } = useSync();
  const { sections, upcomingDays, cardDensity } = useSettings();
  const { t } = useI18n();
  const [selected, setSelected] = useState<Assignment | null>(null);

  const buckets = useMemo(() => {
    const today = startOfDay(new Date());
    const tomorrow = new Date(today.getTime() + 24 * 60 * 60 * 1000);
    const horizon = new Date(
      today.getTime() + upcomingDays * 24 * 60 * 60 * 1000,
    );

    const overdue: Assignment[] = [];
    const dueToday: Assignment[] = [];
    const dueTomorrow: Assignment[] = [];
    const upcoming: Assignment[] = [];
    const completed: Assignment[] = [];

    for (const assignment of assignments) {
      const due = parseDue(assignment.due_at);
      if (assignment.submitted) {
        completed.push(assignment);
        continue;
      }
      if (assignment.is_overdue) {
        overdue.push(assignment);
      } else if (due && due >= today && due < tomorrow) {
        dueToday.push(assignment);
      } else if (
        due &&
        due >= tomorrow &&
        due < new Date(tomorrow.getTime() + 86400000)
      ) {
        dueTomorrow.push(assignment);
      } else if (due && due >= tomorrow && due <= horizon) {
        upcoming.push(assignment);
      }
    }
    completed.sort(
      (a, b) =>
        new Date(b.created_at ?? 0).getTime() -
        new Date(a.created_at ?? 0).getTime(),
    );
    return {
      overdue,
      dueToday,
      dueTomorrow,
      upcoming,
      completed: completed.slice(0, 6),
    };
  }, [assignments, upcomingDays]);

  if (loading) {
    return (
      <div className="page">
        <h1>{t("dash.title")}</h1>
        <SectionSkeleton rows={4} />
      </div>
    );
  }

  return (
    <div className="page">
      <h1>{t("dash.title")}</h1>
      {error ? (
        <div className="alert alert-warning">
          {error} {t("dash.showingCached")}
        </div>
      ) : null}

      {sections.stats && status ? (
        <div className="stat-grid">
          <StatCard
            label={t("stat.total")}
            value={status.total_assignments}
            icon={<CircleDot size={18} />}
          />
          <StatCard
            label={t("stat.completed")}
            value={status.completed}
            tone="success"
            icon={<CheckCircle2 size={18} />}
          />
          <StatCard
            label={t("stat.missing")}
            value={status.missing}
            tone="warning"
            icon={<CalendarClock size={18} />}
          />
          <StatCard
            label={t("stat.overdue")}
            value={status.overdue}
            tone="danger"
            icon={<AlertTriangle size={18} />}
          />
          <StatCard
            label={t("stat.dueToday")}
            value={status.due_today}
            tone="warning"
            icon={<CalendarClock size={18} />}
          />
          <StatCard
            label={t("stat.average")}
            value={
              status.average_grade === null ? "—" : `${status.average_grade}%`
            }
            icon={<TrendingUp size={18} />}
          />
        </div>
      ) : null}

      {sections.overdue ? (
        <section>
          <h2>{t("stat.overdue")}</h2>
          {buckets.overdue.length === 0 ? (
            <EmptyState
              icon={<CheckCircle2 size={28} />}
              title={t("dash.nothingOverdue")}
              subtitle={t("dash.caughtUp")}
            />
          ) : (
            <div className="assignment-grid">
              {buckets.overdue.map((assignment) => (
                <AssignmentCard
                  key={assignment.id}
                  assignment={assignment}
                  density={cardDensity}
                  onOpen={setSelected}
                />
              ))}
            </div>
          )}
        </section>
      ) : null}

      {sections.today ? (
        <section>
          <h2>{t("dash.today")}</h2>
          {buckets.dueToday.length === 0 ? (
            <EmptyState
              icon={<PartyPopper size={28} />}
              title={t("dash.noToday")}
            />
          ) : (
            <div className="assignment-grid">
              {buckets.dueToday.map((assignment) => (
                <AssignmentCard
                  key={assignment.id}
                  assignment={assignment}
                  density={cardDensity}
                  onOpen={setSelected}
                />
              ))}
            </div>
          )}
        </section>
      ) : null}

      {sections.tomorrow ? (
        <section>
          <h2>{t("dash.tomorrow")}</h2>
          {buckets.dueTomorrow.length === 0 ? (
            <EmptyState title={t("dash.noTomorrow")} />
          ) : (
            <div className="assignment-grid">
              {buckets.dueTomorrow.map((assignment) => (
                <AssignmentCard
                  key={assignment.id}
                  assignment={assignment}
                  density={cardDensity}
                  onOpen={setSelected}
                />
              ))}
            </div>
          )}
        </section>
      ) : null}

      {sections.upcoming ? (
        <section>
          <h2>{t("dash.upcoming", { days: upcomingDays })}</h2>
          {buckets.upcoming.length === 0 ? (
            <EmptyState title={t("dash.noUpcoming", { days: upcomingDays })} />
          ) : (
            <div className="assignment-grid">
              {buckets.upcoming.map((assignment) => (
                <AssignmentCard
                  key={assignment.id}
                  assignment={assignment}
                  density={cardDensity}
                  onOpen={setSelected}
                />
              ))}
            </div>
          )}
        </section>
      ) : null}

      {sections.completed ? (
        <section>
          <h2>{t("dash.completed")}</h2>
          {buckets.completed.length === 0 ? (
            <EmptyState title={t("dash.noCompleted")} />
          ) : (
            <div className="assignment-grid">
              {buckets.completed.map((assignment) => (
                <AssignmentCard
                  key={assignment.id}
                  assignment={assignment}
                  density={cardDensity}
                  onOpen={setSelected}
                />
              ))}
            </div>
          )}
        </section>
      ) : null}

      {status?.authenticated ? null : (
        <div className="alert alert-info">
          <GraduationCap size={16} />
          {t("dash.signInHint")}
        </div>
      )}

      <AssignmentModal
        assignment={selected}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}
