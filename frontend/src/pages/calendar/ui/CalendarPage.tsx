import { ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";

import { AssignmentModal } from "../../../features/assignment-modal/AssignmentModal.tsx";
import { EmptyState } from "../../../shared/ui/Skeletons.tsx";
import { useCourses } from "../../../entities/course/index.ts";
import { useSync } from "../../../features/sync/index.ts";
import { useSettings } from "../../../shared/settings/SettingsProvider.tsx";
import { dayKey, isSameDay, parseDue, startOfDay } from "../../../shared/lib/dates.ts";
import { useI18n } from "../../../shared/i18n/index.ts";
import { cn } from "../../../shared/lib/cn.ts";
import type { Assignment, CalendarViewMode } from "../../../shared/types/index.ts";

type ViewMode = "month" | "week" | "day";

function addDays(date: Date, days: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
}

function startOfWeek(date: Date): Date {
  const weekday = (date.getDay() + 6) % 7; // Monday = 0
  return addDays(startOfDay(date), -weekday);
}

export function CalendarPage() {
  const { assignments } = useCourses();
  const { loading } = useSync();
  const { calendarView, update } = useSettings();
  const { t, locale } = useI18n();
  // The last used view is persisted in the settings store, so a reload or the
  // next visit reopens the calendar exactly as it was left (ADR-0006).
  const view = calendarView;
  const [cursor, setCursor] = useState(() => startOfDay(new Date()));
  const [selected, setSelected] = useState<Assignment | null>(null);

  /**
   * Switching to the day view always lands on today, while the month and week
   * views keep the cursor where the user navigated to. `openDay` is the
   * separate path used by a calendar cell: it opens the day that was clicked,
   * not today.
   */
  const setView = (mode: CalendarViewMode) => {
    if (mode === "day") {
      setCursor(startOfDay(new Date()));
    }
    update({ calendarView: mode });
  };

  const openDay = (day: Date) => {
    setCursor(startOfDay(day));
    update({ calendarView: "day" });
  };

  const byDay = useMemo(() => {
    const map = new Map<string, Assignment[]>();
    for (const assignment of assignments) {
      const due = parseDue(assignment.due_at);
      if (!due) {
        continue;
      }
      const key = dayKey(due);
      const bucket = map.get(key) ?? [];
      bucket.push(assignment);
      map.set(key, bucket);
    }
    for (const bucket of map.values()) {
      bucket.sort(
        (a, b) =>
          (parseDue(a.due_at)?.getTime() ?? 0) -
          (parseDue(b.due_at)?.getTime() ?? 0),
      );
    }
    return map;
  }, [assignments]);

  const days = useMemo(() => {
    if (view === "day") {
      return [cursor];
    }
    if (view === "week") {
      return Array.from({ length: 7 }, (_, index) =>
        addDays(startOfWeek(cursor), index),
      );
    }
    const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const gridStart = startOfWeek(first);
    return Array.from({ length: 42 }, (_, index) => addDays(gridStart, index));
  }, [view, cursor]);

  const shift = (direction: 1 | -1) => {
    if (view === "day") {
      setCursor((c) => addDays(c, direction));
    } else if (view === "week") {
      setCursor((c) => addDays(c, 7 * direction));
    } else {
      setCursor((c) => new Date(c.getFullYear(), c.getMonth() + direction, 1));
    }
  };

  const headerLabel =
    view === "month"
      ? cursor.toLocaleDateString(locale, { month: "long", year: "numeric" })
      : view === "week"
        ? t("calendar.weekOf", {
            date: cursor.toLocaleDateString(locale, {
              day: "numeric",
              month: "short",
            }),
          })
        : cursor.toLocaleDateString(locale, {
            weekday: "long",
            day: "numeric",
            month: "long",
          });

  const title = (assignment: Assignment) =>
    `${assignment.course_name}: ${assignment.title}`;

  return (
    <div className="page">
      <div className="page-header">
        <h1>{t("calendar.title")}</h1>
        <div className="calendar-controls">
          <div className="tabs">
            {(["month", "week", "day"] as ViewMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                className={view === mode ? "tab active" : "tab"}
                onClick={() => setView(mode)}
              >
                {t(`calendar.${mode}`)}
              </button>
            ))}
          </div>
          <div className="calendar-nav">
            <button
              type="button"
              className="icon-button"
              onClick={() => shift(-1)}
              aria-label={t("calendar.previous")}
            >
              <ChevronLeft size={18} />
            </button>
            <span className="calendar-label">{headerLabel}</span>
            <button
              type="button"
              className="icon-button"
              onClick={() => shift(1)}
              aria-label={t("calendar.next")}
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="calendar-grid month">
          {Array.from({ length: 35 }, (_, index) => (
            <div key={index} className="calendar-cell skeleton-cell" />
          ))}
        </div>
      ) : view === "day" ? (
        <div>
          <DayList
            assignments={byDay.get(dayKey(cursor)) ?? []}
            onOpen={setSelected}
          />
        </div>
      ) : (
        <div className={cn("calendar-grid", view === "week" && "week")}>
          {view === "month" || view === "week"
            ? Array.from({ length: 7 }, (_, index) => (
                <div key={index} className="calendar-weekday">
                  {new Date(2024, 0, index + 1).toLocaleDateString(locale, {
                    weekday: "short",
                  })}
                </div>
              ))
            : null}
          {days.map((day) => {
            const items = byDay.get(dayKey(day)) ?? [];
            const outside =
              view === "month" && day.getMonth() !== cursor.getMonth();
            const isToday = isSameDay(day, new Date());
            return (
              <div
                key={dayKey(day)}
                className={cn(
                  "calendar-cell",
                  outside && "outside",
                  isToday && "today",
                  items.length > 0 && "has-items",
                )}
                onClick={() => openDay(day)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    openDay(day);
                  }
                }}
                role="button"
                tabIndex={0}
                aria-label={day.toLocaleDateString(locale, {
                  weekday: "long",
                  day: "numeric",
                  month: "long",
                })}
              >
                <div className="calendar-day-number">{day.getDate()}</div>
                <div className="calendar-items">
                  {items.slice(0, 3).map((assignment) => (
                    <button
                      key={assignment.id}
                      type="button"
                      className={cn(
                        "calendar-item",
                        assignment.is_overdue && "overdue",
                        assignment.submitted && "done",
                      )}
                      onClick={(event) => {
                        event.stopPropagation();
                        setSelected(assignment);
                      }}
                      title={title(assignment)}
                    >
                      {assignment.title}
                    </button>
                  ))}
                  {items.length > 3 ? (
                    <span className="calendar-more">
                      {t("calendar.more", { count: items.length - 3 })}
                    </span>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {assignments.length === 0 && !loading ? (
        <EmptyState
          title={t("calendar.empty")}
          subtitle={t("calendar.emptyHint")}
        />
      ) : null}

      <AssignmentModal
        assignment={selected}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}

function DayList({
  assignments,
  onOpen,
}: {
  assignments: Assignment[];
  onOpen: (assignment: Assignment) => void;
}) {
  const { t } = useI18n();
  if (assignments.length === 0) {
    return <EmptyState title={t("calendar.noDay")} />;
  }
  return (
    <div className="day-list">
      {assignments.map((assignment) => (
        <button
          key={assignment.id}
          type="button"
          className={cn(
            "card day-list-item",
            // Same colour language as the month/week chips (ADR-0009).
            assignment.is_overdue && "day-list-overdue",
            assignment.submitted && "day-list-done",
          )}
          onClick={() => onOpen(assignment)}
        >
          <span
            className="subject-chip day-list-course"
            title={assignment.course_name}
          >
            {assignment.course_name}
          </span>
          <span className="day-list-title">{assignment.title}</span>
          {assignment.max_points === null ? null : (
            <span className="day-list-points">
              {t("calendar.points", { count: assignment.max_points })}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
