import type { Assignment } from "./assignment.ts";

export type Priority = Assignment["priority"];

export type AssignmentStatusFilter =
    "all" | "todo" | "overdue" | "completed" | "graded" | "ungraded";

/** The four states the assignments filter panel lets you combine. */
export type AssignmentFilterStatus = Exclude<
    AssignmentStatusFilter,
    "all" | "ungraded"
>;

/**
 * Whether an assignment has a deadline. This is its own facet, not a status:
 * both values are self-sufficient and are combined with the status facet by
 * AND, never as an extra condition of a status.
 */
export type AssignmentDueFilter = "has_due" | "no_due";

/**
 * Saved "last used" state of the assignments filter panel (ADR-0013), kept in
 * the settings store so leaving the page and coming back does not reset it.
 * Every facet shares one convention: `null` = facet off (everything matches),
 * `[]` = nothing selected (nothing matches).
 */
export type AssignmentsFilter = {
    statuses: AssignmentFilterStatus[] | null;
    due: AssignmentDueFilter[] | null;
    courses: string[] | null;
};

export type SortKey = "due" | "priority" | "grade" | "newest" | "oldest";

export type CalendarViewMode = "month" | "week" | "day";

export type ThemeMode = "light" | "dark" | "system";

/**
 * The scales a school grades on. Classroom stores raw points per assignment, so
 * the chart needs to be told what the top of the axis means — and it must be
 * the USER who says so, because the app has no way to know that one course is
 * marked out of 12 and the next out of 100 (ADR-0042).
 */
export type GradeScale = 12 | 100;

export type Language = "en" | "uk" | "ru";

export type DashboardSections = {
    overdue: boolean;
    today: boolean;
    tomorrow: boolean;
    upcoming: boolean;
    completed: boolean;
    stats: boolean;
};

export type NotificationPrefs = {
    dueToday: boolean;
    dueTomorrow: boolean;
    overdue: boolean;
};

export type AppSettings = {
    theme: ThemeMode;
    language: Language;
    upcomingDays: 3 | 7 | 14;
    defaultSort: SortKey;
    cardDensity: "compact" | "comfortable";
    sections: DashboardSections;
    notifications: NotificationPrefs;
    /** Dismissed reminder keys ("kind:assignmentId") kept in storage. */
    dismissedNotifications: string[];
    assignmentsFilter: AssignmentsFilter;
    /** Last used calendar view, so a reload reopens the same one. */
    calendarView: CalendarViewMode;
    /**
     * Course ids whose grade groups are collapsed on the Grades tab. Groups not
     * listed here are expanded, so a fresh profile starts with everything open.
     */
    collapsedGradeCourses: string[];
    /** Last used status tab on the subject detail page. */
    subjectTab: AssignmentStatusFilter | "all";
    /** Top of the grade axis. 12 in a Ukrainian school, 100 on a percentage one. */
    gradeScale: GradeScale;
};

export const DEFAULT_SETTINGS: AppSettings = {
    theme: "system",
    language: "en",
    upcomingDays: 7,
    defaultSort: "due",
    cardDensity: "comfortable",
    sections: {
        overdue: true,
        today: true,
        tomorrow: true,
        upcoming: true,
        completed: true,
        stats: true,
    },
    notifications: {
        dueToday: true,
        dueTomorrow: true,
        overdue: true,
    },
    dismissedNotifications: [],
    assignmentsFilter: {
        statuses: null,
        due: null,
        courses: null,
    },
    calendarView: "month",
    collapsedGradeCourses: [],
    subjectTab: "all",
    gradeScale: 12,
};