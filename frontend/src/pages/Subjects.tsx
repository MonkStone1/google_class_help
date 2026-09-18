import { BookOpen } from "lucide-react";

import { EmptyState, SectionSkeleton } from "../components/Skeletons.tsx";
import { SubjectCard } from "../components/SubjectCards.tsx";
import { useCourses, useSync } from "../context/DataContext.tsx";
import { useI18n } from "../i18n.ts";

export function Subjects() {
  const { courses } = useCourses();
  const { loading, status } = useSync();
  const { t } = useI18n();

  if (loading) {
    return (
      <div className="page">
        <h1>{t("subjects.title")}</h1>
        <SectionSkeleton rows={4} />
      </div>
    );
  }

  return (
    <div className="page">
      <h1>{t("subjects.title")}</h1>
      {status && !status.authenticated ? (
        <EmptyState
          icon={<BookOpen size={28} />}
          title={t("subjects.notSignedIn")}
          subtitle={t("subjects.notSignedInHint")}
        />
      ) : courses.length === 0 ? (
        <EmptyState
          icon={<BookOpen size={28} />}
          title={t("subjects.empty")}
          subtitle={t("subjects.emptyHint")}
        />
      ) : (
        <div className="subject-grid">
          {courses.map((course) => (
            <SubjectCard key={course.id} course={course} />
          ))}
        </div>
      )}
    </div>
  );
}
