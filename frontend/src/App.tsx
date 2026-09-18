import { useEffect } from "react";
import { Route, Routes, useSearchParams } from "react-router-dom";

import { Sidebar } from "./components/Sidebar.tsx";
import { TopBar } from "./components/TopBar.tsx";
import { DataProvider } from "./context/DataContext.tsx";
import { SettingsProvider } from "./context/SettingsContext.tsx";
import { DuplicateTabNotice } from "./components/DuplicateTabNotice.tsx";
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
  // Search lives in the URL: a reload keeps the query, the link is shareable
  // and the browser Back button cancels it — same contract as the filters.
  const [searchParams, setSearchParams] = useSearchParams();
  const search = searchParams.get("q") ?? "";

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

  useEffect(() => {
    document.title = t("app.title");
  }, [t]);

  return (
    <div className="app-layout">
      <Sidebar />
      <div className="app-main">
        <DuplicateTabNotice />
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
