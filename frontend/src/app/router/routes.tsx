/**
 * The route table, as DATA.
 *
 * It was two `<Routes>` blocks inside one 284-line `App.tsx`, which meant the
 * route list could not be read without also reading the session gate, the two
 * shells and the search plumbing around them. Declared here it is a list of
 * paths — and a test can assert it (`baseline.test.ts` freezes the twenty
 * entries, catch-alls included).
 *
 * `guard` is data too, not JSX: a route may say who may see it, and
 * `AppRouter` turns that into elements. That is what keeps `RequireAdmin` out
 * of this file while still making the requirement visible.
 */

import type { ReactNode } from "react";

import { RequireAdmin, RequireSuperAdmin } from "./guards.tsx";
import { AdminAdmins } from "../../pages/admin/admins/index.ts";
import { AdminDashboard } from "../../pages/admin/dashboard/index.ts";
import { AdminFeedback } from "../../pages/admin/feedback/index.ts";
import { AdminFeedbackTicket } from "../../pages/admin/ticket/index.ts";
import { AssignmentDetail } from "../../pages/assignment/index.ts";
import { Assignments } from "../../pages/assignments/index.ts";
import { CalendarPage } from "../../pages/calendar/index.ts";
import { Dashboard } from "../../pages/dashboard/index.ts";
import { FeedbackHome } from "../../pages/feedback/home/index.ts";
import { FeedbackNew } from "../../pages/feedback/new/index.ts";
import { FeedbackTicket } from "../../pages/feedback/ticket/index.ts";
import { FeedbackTickets } from "../../pages/feedback/tickets/index.ts";
import { Grades } from "../../pages/grades/index.ts";
import { Settings } from "../../pages/settings/index.ts";
import { StudentGrades } from "../../pages/student-grades/index.ts";
import { SubjectDetail } from "../../pages/subject/index.ts";
import { Subjects } from "../../pages/subjects/index.ts";
import { TeacherGrades } from "../../pages/teacher-grades/index.ts";

/** Who must be signed in for a route to render. */
export type Guard = "none" | "admin" | "super-admin";

export type RouteDefinition = {
    path: string;
    element: ReactNode;
    guard?: Guard;
};

export const USER_ROUTES: readonly RouteDefinition[] = [
    { path: "/", element: <Dashboard /> },
    { path: "/subjects", element: <Subjects /> },
    { path: "/subjects/:courseId/grades", element: <TeacherGrades /> },
    {
        path: "/subjects/:courseId/students/:studentId",
        element: <StudentGrades />,
    },
    {
        path: "/subjects/:courseId/assignments/:courseworkId",
        element: <AssignmentDetail />,
    },
    { path: "/subjects/:courseId", element: <SubjectDetail /> },
    { path: "/assignments", element: <Assignments /> },
    { path: "/grades", element: <Grades /> },
    { path: "/calendar", element: <CalendarPage /> },
    // Feedback (ADR-0035): the user surface is open to any signed-in account;
    // identity comes from the session, never the form.
    { path: "/feedback", element: <FeedbackHome /> },
    { path: "/feedback/new", element: <FeedbackNew /> },
    { path: "/feedback/tickets", element: <FeedbackTickets /> },
    { path: "/feedback/tickets/:id", element: <FeedbackTicket /> },
    { path: "/settings", element: <Settings /> },
];

export const ADMIN_ROUTES: readonly RouteDefinition[] = [
    { path: "/admin", element: <AdminDashboard />, guard: "admin" },
    { path: "/admin/feedback", element: <AdminFeedback />, guard: "admin" },
    {
        path: "/admin/feedback/:id",
        element: <AdminFeedbackTicket />,
        guard: "admin",
    },
    {
        path: "/admin/admins",
        element: (
            <RequireAdmin>
                <RequireSuperAdmin>
                    <AdminAdmins />
                </RequireSuperAdmin>
            </RequireAdmin>
        ),
    },
];

/**
 * The guards are per route, not one wrapper around the shell:
 * `RequireAdmin` sends a non-administrator to `/`, while
 * `RequireSuperAdmin` additionally keeps a plain administrator out of
 * `/admin/admins` (D11/D3 — UX only; the API refuses both cases regardless).
 */
export { RequireAdmin, RequireSuperAdmin };