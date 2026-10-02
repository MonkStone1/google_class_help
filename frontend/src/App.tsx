import { useEffect, useRef } from "react";
import {
    Navigate,
    Route,
    Routes,
    useLocation,
    useSearchParams,
} from "react-router-dom";

import { AdminSidebar } from "./components/AdminSidebar.tsx";
import { Sidebar } from "./components/Sidebar.tsx";
import { TopBar } from "./components/TopBar.tsx";
import { BootSplash } from "./components/BootSplash.tsx";
import { Landing } from "./components/Landing.tsx";
import { RequireAdmin } from "./components/RequireAdmin.tsx";
import { RequireSuperAdmin } from "./components/RequireSuperAdmin.tsx";
import { SignIn } from "./components/SignIn.tsx";
import { SyncToaster } from "./components/SyncToaster.tsx";
import { Toaster } from "./components/Toaster.tsx";
import { DataProvider, useAuth, useSync } from "./context/DataContext.tsx";
import { SettingsProvider } from "./context/SettingsContext.tsx";
import { DashboardBoundary } from "./components/ErrorBoundary.tsx";
import { useI18n } from "./i18n.ts";
import { AdminAdmins } from "./pages/AdminAdmins.tsx";
import { AdminDashboard } from "./pages/AdminDashboard.tsx";
import { AdminFeedback } from "./pages/AdminFeedback.tsx";
import { AdminFeedbackTicket } from "./pages/AdminFeedbackTicket.tsx";
import { Assignments } from "./pages/Assignments.tsx";
import { AssignmentDetail } from "./pages/AssignmentDetail.tsx";
import { CalendarPage } from "./pages/CalendarPage.tsx";
import { Dashboard } from "./pages/Dashboard.tsx";
import { FeedbackHome } from "./pages/FeedbackHome.tsx";
import { FeedbackNew } from "./pages/FeedbackNew.tsx";
import { FeedbackTicket } from "./pages/FeedbackTicket.tsx";
import { FeedbackTickets } from "./pages/FeedbackTickets.tsx";
import { Grades } from "./pages/Grades.tsx";
import { Settings } from "./pages/Settings.tsx";
import { StudentGrades } from "./pages/StudentGrades.tsx";
import { SubjectDetail } from "./pages/SubjectDetail.tsx";
import { Subjects } from "./pages/Subjects.tsx";
import { TeacherGrades } from "./pages/TeacherGrades.tsx";

export default function App() {
  return (
    <SettingsProvider>
      <DataProvider>
        {/*
          The toast host lives here, next to AppShell and not inside it: the
          shell returns early for the splash, the landing and the sign-in gate,
          and a sync that finishes in the background must be announced on the
          surface the user actually came back to. `<Toaster />` needs the
          settings (theme + language), `<SyncToaster />` the sync state.
        */}
        <Toaster />
        <SyncToaster />
        <AppShell />
      </DataProvider>
    </SettingsProvider>
  );
}

function AppShell() {
  const { t } = useI18n();
  const { auth, sessionRequired } = useAuth();
  const { loading } = useSync();
  const { pathname } = useLocation();
  // Search lives in the URL: a reload keeps the query, the link is shareable
  // and the browser Back button cancels it — same contract as the filters.
  const [searchParams, setSearchParams] = useSearchParams();
  const search = searchParams.get("q") ?? "";

  // A browser that never had a session should meet the public landing page,
  // not a bare login card; a browser whose session merely EXPIRED already
  // knows the site and only needs the way back in (ADR-0029). The ref, not
  // state: the distinction is read during render and must not re-render.
  const hadSession = useRef(false);
  if (auth?.authenticated) {
    hadSession.current = true;
  }
  const signedOut = sessionRequired && !auth?.authenticated;
  const showLanding = signedOut && !hadSession.current;

  // Until the first response arrives we do not know which surface belongs to
  // this browser, so render nothing that could be wrong: `auth` is null and
  // the dataset request is still in flight. A 401 sets `auth` to SIGNED_OUT
  // inside `request()` (api.ts), so the splash is lifted as soon as the gate
  // is known — it never waits for the other three requests to settle.
  const bootUnknown = auth === null && loading;

  // Hooks must run on every render, so the sign-in gate below returns only
  // after all of them.
  useEffect(() => {
    // The landing owns the document title while it is on screen.
    if (showLanding) return;
    document.title = t("app.title");
  }, [t, showLanding]);

  if (bootUnknown) {
    return <BootSplash />;
  }

  // §26: a 401 means this browser has no application session — route back to
  // the login state instead of rendering pages that can only 401 again. The
  // desktop build never sets `sessionRequired`, so its workflow is untouched.
  if (showLanding) {
    return <Landing />;
  }
  if (signedOut) {
    return <SignIn />;
  }

  // The console is a separate shell (D1): a path under /admin renders
  // `AdminShell`, everything else the public shell below. Branching on the
  // location — rather than mounting both and hiding one — is what keeps the
  // public navigation free of admin entries by construction.
  if (isAdminPath(pathname)) {
    return <AdminShell />;
  }

  const onSearch = (value: string) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value) {
          next.set("q", value);
        } else {
          next.delete("q");
        }
        return next;
      },
      { replace: true },
    );
  };

  return (
    <div className="app-layout">
      <Sidebar />
      <div className="app-main">
        <TopBar search={search} onSearch={onSearch} />
        <main className="app-content">
          <DashboardBoundary>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/subjects" element={<Subjects />} />
              <Route
                path="/subjects/:courseId/grades"
                element={<TeacherGrades />}
              />
              <Route
                path="/subjects/:courseId/students/:studentId"
                element={<StudentGrades />}
              />
              <Route
                path="/subjects/:courseId/assignments/:courseworkId"
                element={<AssignmentDetail />}
              />
              <Route path="/subjects/:courseId" element={<SubjectDetail />} />
              <Route path="/assignments" element={<Assignments />} />
              <Route path="/grades" element={<Grades />} />
              <Route path="/calendar" element={<CalendarPage />} />
              {/* Feedback (ADR-0035): the user surface is open to any signed-in
                  account; identity comes from the session, never the form. */}
              <Route path="/feedback" element={<FeedbackHome />} />
              <Route path="/feedback/new" element={<FeedbackNew />} />
              <Route path="/feedback/tickets" element={<FeedbackTickets />} />
              <Route
                path="/feedback/tickets/:id"
                element={<FeedbackTicket />}
              />
              <Route path="/settings" element={<Settings />} />
              {/* Every /admin path belongs to the console shell (D1). A user who
                  lands here is redirected to `/` by RequireAdmin rather than
                  shown an admin frame. */}
              <Route path="/admin/*" element={<Navigate to="/admin" replace />} />
            </Routes>
          </DashboardBoundary>
        </main>
      </div>
    </div>
  );
}

/**
 * Whether a path belongs to the admin console.
 *
 * A prefix match on the SEGMENT, not a string prefix: `/administrator` is a
 * different place and must render the public shell. `/admin` itself and
 * everything below it are the console.
 */
function isAdminPath(pathname: string): boolean {
  return pathname === "/admin" || pathname.startsWith("/admin/");
}

/**
 * The `/admin` console shell (D1/D2, ADR-0036).
 *
 * The SAME layout markup as the user shell — `div.app-layout`, the sidebar,
 * `div.app-main` with `main.app-content` — with `AdminSidebar` instead of
 * `Sidebar`. Mirroring the structure is the point: the console must look like
 * the rest of the product, and only the navigation differs.
 *
 * **There is no `<TopBar>` here** (п.8). The console is a back office for
 * tickets, and every control the topbar carried was either meaningless or
 * actively misleading on it:
 *
 * - the global search looks through the *assignments and courses* cache, which
 *   an administrator has no use for while working a ticket queue;
 * - the sync button and its timestamp belong to a user's own Google grant —
 *   the console has no dataset of its own to sync;
 * - the notification bell is built from the same assignments (ADR-0004);
 * - the theme toggle is the only genuinely useful one, and it is reachable from
 *   `/settings` for the same person.
 *
 * Removing it also drops the `?q=` plumbing this shell carried for the search
 * box — there is nothing left to feed it.
 *
 * The guards are per route, not one wrapper around the shell: `RequireAdmin`
 * sends a non-administrator to `/`, while `RequireSuperAdmin` additionally keeps
 * a plain administrator out of `/admin/admins` (D11/D3 — UX only; the API
 * refuses both cases regardless).
 */
function AdminShell() {
  const { auth } = useAuth();

  // The console is an authenticated surface: until the session answer arrives
  // there is nothing honest to render, and the guards below would redirect a
  // flash of it to `/`. Render nothing until `auth` is decided.
  if (!auth) return null;

  return (
    <div className="app-layout">
      <AdminSidebar />
      <div className="app-main">
        <main className="app-content">
          <DashboardBoundary>
            <Routes>
              <Route
                path="/admin"
                element={
                  <RequireAdmin>
                    <AdminDashboard />
                  </RequireAdmin>
                }
              />
              <Route
                path="/admin/feedback"
                element={
                  <RequireAdmin>
                    <AdminFeedback />
                  </RequireAdmin>
                }
              />
              <Route
                path="/admin/feedback/:id"
                element={
                  <RequireAdmin>
                    <AdminFeedbackTicket />
                  </RequireAdmin>
                }
              />
              <Route
                path="/admin/admins"
                element={
                  <RequireAdmin>
                    <RequireSuperAdmin>
                      <AdminAdmins />
                    </RequireSuperAdmin>
                  </RequireAdmin>
                }
              />
              {/* An unknown console path goes to the console root, never to the
                  public dashboard: leaving the console for a typo would be
                  confusing, and the guards above own the redirect to `/`. */}
              <Route
                path="/admin/*"
                element={<Navigate to="/admin" replace />}
              />
            </Routes>
          </DashboardBoundary>
        </main>
      </div>
    </div>
  );
}
