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
import { AdminAdmins } from "../../pages/admin/admins/ui/AdminAdmins.tsx";
import { AdminDashboard } from "../../pages/admin/dashboard/ui/AdminDashboard.tsx";
import { AdminFeedback } from "../../pages/admin/feedback/ui/AdminFeedback.tsx";
import { AdminFeedbackTicket } from "../../pages/admin/ticket/ui/AdminFeedbackTicket.tsx";
import { AssignmentDetail } from "../../pages/assignment/ui/AssignmentDetail.tsx";
import { Assignments } from "../../pages/assignments/ui/Assignments.tsx";
import { CalendarPage } from "../../pages/calendar/ui/CalendarPage.tsx";
import { Dashboard } from "../../pages/dashboard/ui/Dashboard.tsx";
import { FeedbackHome } from "../../pages/feedback/home/ui/FeedbackHome.tsx";
import { FeedbackNew } from "../../pages/feedback/new/ui/FeedbackNew.tsx";
import { FeedbackTicket } from "../../pages/feedback/ticket/ui/FeedbackTicket.tsx";
import { FeedbackTickets } from "../../pages/feedback/tickets/ui/FeedbackTickets.tsx";
import { Grades } from "../../pages/grades/ui/Grades.tsx";
import { Settings } from "../../pages/settings/ui/Settings.tsx";
import { StudentGrades } from "../../pages/student-grades/ui/StudentGrades.tsx";
import { SubjectDetail } from "../../pages/SubjectDetail.tsx";
import { Subjects } from "../../pages/subjects/ui/Subjects.tsx";
import { TeacherGrades } from "../../pages/teacher-grades/ui/TeacherGrades.tsx";

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