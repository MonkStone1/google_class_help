import {
  ArrowLeft,
  ClipboardList,
  GraduationCap,
  Users,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../../shared/api/index.ts";
import { AssignmentCard } from "../../../entities/assignment/index.ts";
import { ExcelExportButton } from "../../../features/excel-export/index.ts";
import { EmptyState, SectionSkeleton } from "../../../shared/ui/index.ts";
import { useSettings } from "../../../shared/settings/index.ts";
import { useI18n } from "../../../shared/i18n/index.ts";
import { useResource } from "../../../shared/hooks/index.ts";
import type { Assignment, Course, StudentGradeRow } from "../../../shared/types/index.ts";

type Tab = "assignments" | "students" | "grades";

/**
 * Teacher view of a course (section 5): course info, ALL assignments, the
 * student list and a grades overview. Data comes from the cached teacher
 * endpoints, shared through the resource cache so switching tabs does not
 * re-fetch the roster.
 */
export function TeacherCourse({ course }: { course: Course }) {
  const { t } = useI18n();
  const { cardDensity } = useSettings();
  const [tab, setTab] = useState<Tab>("assignments");

  const coursework = useResource(`course:${course.id}:coursework`, (signal) =>
    api.getCourseCoursework(course.id, signal),
  );
  const grades = useResource(`course:${course.id}:grades`, (signal) =>
    api.getCourseGrades(course.id, signal),
  );

  const updatedAt =
    Math.max(coursework.updatedAt ?? 0, grades.updatedAt ?? 0) || null;

  const students = grades.data?.rows ?? [];

  return (
    <div className="page">
      <Link to="/subjects" className="back-link">
        <ArrowLeft size={15} /> {t("subject.back")}
      </Link>

      <div className="page-header">
        <div>
          <h1>{course.name}</h1>
          <div className="page-subtitle">
            <span className="badge badge-role">{t("teacher.role")}</span>
            {course.teachers.length > 0
              ? ` · ${course.teachers.join(", ")}`
              : ""}
            {course.room ? ` · ${course.room}` : ""}
          </div>
          {course.description ? (
            <p className="course-description">{course.description}</p>
          ) : null}
          <div className="subject-detail-stats">
            <span>
              {t("teacher.assignmentsCount", {
                count: course.total_assignments,
              })}
            </span>
            <span>
              {t("teacher.studentsCount", { count: course.student_count })}
            </span>
            {course.average_grade === null ? null : (
              <span>{t("subject.avg", { value: course.average_grade })}</span>
            )}
          </div>
        </div>
        <div className="page-header-actions">
          {/* ADR-0041: the export reads the coursework this page has already
              loaded, so it adds no request and no state of its own here. */}
          <ExcelExportButton
            courseName={course.name}
            assignments={coursework.data ?? []}
          />
          {updatedAt ? (
            <span className="updated-label">
              {t("teacher.updated", {
                time: new Date(updatedAt).toLocaleTimeString(undefined, {
                  hour: "2-digit",
                  minute: "2-digit",
                }),
              })}
            </span>
          ) : null}
        </div>
      </div>

      <div className="filter-bar">
        <div className="tabs">
          <button
            type="button"
            className={tab === "assignments" ? "tab active" : "tab"}
            onClick={() => setTab("assignments")}
          >
            <ClipboardList size={15} /> {t("teacher.tab.assignments")}
          </button>
          <button
            type="button"
            className={tab === "students" ? "tab active" : "tab"}
            onClick={() => setTab("students")}
          >
            <Users size={15} /> {t("teacher.tab.students")}
          </button>
          <button
            type="button"
            className={tab === "grades" ? "tab active" : "tab"}
            onClick={() => setTab("grades")}
          >
            <GraduationCap size={15} /> {t("teacher.tab.grades")}
          </button>
        </div>
      </div>

      {tab === "assignments" ? (
        <CourseAssignments
          course={course}
          density={cardDensity}
          loading={coursework.loading}
          error={coursework.error}
          assignments={coursework.data}
        />
      ) : null}

      {tab === "students" ? (
        <CourseStudents
          course={course}
          loading={grades.loading}
          error={grades.error}
          students={students}
        />
      ) : null}

      {tab === "grades" ? (
        <CourseGradesOverview
          course={course}
          loading={grades.loading}
          error={grades.error}
          classAverage={grades.data?.class_average ?? null}
          gradedCount={grades.data?.assignments.length ?? 0}
        />
      ) : null}
    </div>
  );
}

function CourseAssignments({
  course,
  density,
  loading,
  error,
  assignments,
}: {
  course: Course;
  density: "compact" | "comfortable";
  loading: boolean;
  error: string | null;
  assignments: Assignment[] | null;
}) {
  const { t } = useI18n();
  if (loading && !assignments) {
    return <SectionSkeleton rows={4} />;
  }
  if (error) {
    return <div className="alert alert-error">{error}</div>;
  }
  if (!assignments || assignments.length === 0) {
    return <EmptyState title={t("teacher.assignments.empty")} />;
  }
  return (
    <div className="assignment-grid">
      {assignments.map((assignment) => (
        <AssignmentCard
          key={assignment.id}
          assignment={assignment}
          density={density}
          // The page owns the route; the card owns how an assignment reads
          // (ADR-0040 #4 — entities/ does not import the router).
          wrap={(content, className) => (
            <Link
              to={`/subjects/${course.id}/assignments/${assignment.id}`}
              className={className}
            >
              {content}
            </Link>
          )}
        />
      ))}
    </div>
  );
}

function CourseStudents({
  course,
  loading,
  error,
  students,
}: {
  course: Course;
  loading: boolean;
  error: string | null;
  students: StudentGradeRow[];
}) {
  const { t } = useI18n();
  if (loading && students.length === 0) {
    return <SectionSkeleton rows={3} />;
  }
  if (error) {
    return <div className="alert alert-error">{error}</div>;
  }
  if (students.length === 0) {
    return <EmptyState title={t("teacher.students.empty")} />;
  }
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>{t("teacher.grades.studentColumn")}</th>
            <th>{t("teacher.grades.averageColumn")}</th>
          </tr>
        </thead>
        <tbody>
          {students.map((row) => (
            <tr key={row.student.id}>
              <td>
                <Link to={`/subjects/${course.id}/students/${row.student.id}`}>
                  {row.student.full_name || row.student.id}
                </Link>
              </td>
              <td>
                {row.average_percent === null
                  ? t("teacher.grades.noAverage")
                  : `${row.average_percent}%`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CourseGradesOverview({
  course,
  loading,
  error,
  classAverage,
  gradedCount,
}: {
  course: Course;
  loading: boolean;
  error: string | null;
  classAverage: number | null;
  gradedCount: number;
}) {
  const { t } = useI18n();
  if (loading) {
    return <SectionSkeleton rows={2} />;
  }
  if (error) {
    return <div className="alert alert-error">{error}</div>;
  }
  return (
    <div className="card teacher-overview">
      <h2>{t("teacher.grades.overview")}</h2>
      <div className="subject-detail-stats">
        <span>
          {classAverage === null
            ? t("teacher.grades.noAverage")
            : t("teacher.grades.classAverage", { value: classAverage })}
        </span>
        <span>{t("teacher.assignmentsCount", { count: gradedCount })}</span>
      </div>
      <Link
        to={`/subjects/${course.id}/grades`}
        className="button button-primary"
      >
        <GraduationCap size={15} /> {t("teacher.grades.viewAll")}
      </Link>
    </div>
  );
}
