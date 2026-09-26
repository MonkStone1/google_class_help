import { useEffect, useRef } from "react";
import { Route, Routes, useSearchParams } from "react-router-dom";

import { Sidebar } from "./components/Sidebar.tsx";
import { TopBar } from "./components/TopBar.tsx";
import { BootSplash } from "./components/BootSplash.tsx";
import { Landing } from "./components/Landing.tsx";
import { SignIn } from "./components/SignIn.tsx";
import { DataProvider, useAuth, useSync } from "./context/DataContext.tsx";
import { SettingsProvider } from "./context/SettingsContext.tsx";
import { DashboardBoundary } from "./components/ErrorBoundary.tsx";
import { useI18n } from "./i18n.ts";
import { Assignments } from "./pages/Assignments.tsx";
import { AssignmentDetail } from "./pages/AssignmentDetail.tsx";
import { CalendarPage } from "./pages/CalendarPage.tsx";
import { Dashboard } from "./pages/Dashboard.tsx";
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
        <AppShell />
      </DataProvider>
    </SettingsProvider>
  );
}

function AppShell() {
  const { t } = useI18n();
  const { auth, sessionRequired } = useAuth();
  const { loading } = useSync();
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
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </DashboardBoundary>
        </main>
      </div>
    </div>
  );
}
