/**
 * Domain types of the frontend.
 *
 * The wire shapes are no longer hand-copied from `backend/schemas.py`: they
 * are generated into `api-schema.d.ts` by `npm run gen:api` (openapi-typescript
 * over FastAPI's OpenAPI document; `tools/dump_openapi.py` regenerates the
 * JSON without a running server). A field that changes on the backend now
 * breaks `tsc` instead of silently diverging at runtime.
 *
 * What stays hand-written here are the frontend's *own* concepts: filter
 * facets, settings, and the small unions the UI derives from the wire data.
 */

import type { components } from "./api-schema.d.ts";

type Schemas = components["schemas"];

/**
 * Pydantic always serializes a field, even when the request schema marks it
 * optional through a default or a nullable type — the OpenAPI generator
 * therefore understates what the wire carries (`description?: string | null`).
 * `Required<>` restores the contract the responses actually keep, while the
 * generated interface stays the source of truth for field names and types.
 */
type DeepRequired<T> = T extends (infer U)[]
  ? DeepRequired<U>[]
  : T extends object
    ? { [K in keyof T]-?: DeepRequired<T[K]> }
    : T;

type Wire<K extends keyof Schemas> = DeepRequired<Schemas[K]>;

/**
 * The backend derives these labels, so the schema models them as free-form
 * strings; the UI is written against the closed set it can actually receive.
 */
type WithStatus<T> = Omit<T, "status"> & { status: SubmissionStatus };

type AssignmentWire = Wire<"AssignmentOut">;

type PriorityLevel = "high" | "medium" | "low";

/** Material attached to an assignment or a submission. */
export type Material = Wire<"MaterialOut">;

/** Role of the signed-in user in a particular course (per course, not global). */
export type UserRole = "TEACHER" | "STUDENT";

/** Derived submission status; missing grade is never rendered as 0. */
export type SubmissionStatus =
  | "not_submitted"
  | "turned_in"
  | "returned"
  | "graded";

export type Student = Wire<"StudentOut">;

/** One student's submission for one assignment (teacher view). */
export type Submission = WithStatus<Wire<"SubmissionOut">>;

export type Assignment = Omit<AssignmentWire, "priority" | "role"> & {
  priority: PriorityLevel;
  role: UserRole;
};

/** Assignment page payload: metadata plus every student's submission state. */
export type AssignmentDetail = Omit<
  Wire<"AssignmentDetailOut">,
  "priority" | "role" | "submissions"
> & {
  priority: PriorityLevel;
  role: UserRole;
  submissions: Submission[];
};

export type Course = Omit<Wire<"CourseOut">, "role"> & {
  role: UserRole;
};

export type CourseDetail = Omit<Wire<"CourseDetailOut">, "role"> & {
  role: UserRole;
};

export type GradeColumn = Wire<"GradeColumn">;

export type SubmissionCell = WithStatus<Wire<"SubmissionCell">>;

export type StudentGradeRow = Omit<Wire<"StudentGradeRow">, "cells"> & {
  cells: SubmissionCell[];
};

/** Teacher grade matrix: students (rows) × assignments (columns). */
export type TeacherGrades = Omit<
  Wire<"TeacherGradesOut">,
  "rows" | "assignments"
> & {
  assignments: GradeColumn[];
  rows: StudentGradeRow[];
};

export type StudentGradeItem = WithStatus<Wire<"StudentGradeItem">>;

export type StudentGrades = Omit<Wire<"StudentGradesOut">, "items"> & {
  items: StudentGradeItem[];
};

export type GradeItem = Wire<"GradeItem">;

export type CourseGrades = Wire<"CourseGrades">;

export type AppStatus = Wire<"SyncStatus">;

export type AuthStatus = Wire<"AuthStatus">;

export type SyncResult = Wire<"SyncResult">;

export type Priority = Assignment["priority"];

export type AssignmentStatusFilter =
  | "all"
  | "todo"
  | "overdue"
  | "completed"
  | "graded"
  | "ungraded"
  | "no_due";

/** The five states the assignments filter panel lets you combine. */
export type AssignmentFilterStatus = Exclude<
  AssignmentStatusFilter,
  "all" | "ungraded"
>;

/**
 * Saved "last used" state of the assignments filter panel (ADR-0013), kept in
 * the settings store so leaving the page and coming back does not reset it.
 * Both facets share one convention: `null` = facet off (everything matches),
 * `[]` = nothing selected (nothing matches).
 */
export type AssignmentsFilter = {
  statuses: AssignmentFilterStatus[] | null;
  courses: string[] | null;
};

export type SortKey = "due" | "priority" | "grade" | "newest" | "oldest";

export type CalendarViewMode = "month" | "week" | "day";

export type ThemeMode = "light" | "dark" | "system";

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
  /** Last used status tab on the subject detail page. */
  subjectTab: AssignmentStatusFilter | "all";
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
    courses: null,
  },
  calendarView: "month",
  subjectTab: "all",
};
