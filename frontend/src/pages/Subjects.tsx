import { BookOpen } from "lucide-react";
import { Link } from "react-router-dom";

import { EmptyState, SectionSkeleton } from "../shared/ui/Skeletons.tsx";
import { SubjectCard } from "../entities/course/index.ts";
import { useCourses } from "../entities/course/index.ts";
import { useSync } from "../features/sync/index.ts";
import { useI18n } from "../shared/i18n/index.ts";

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
            <SubjectCard
              key={course.id}
              course={course}
              // The route lives here, not in the card: the domain states how a
              // course reads, the page states where it goes (ADR-0040 #4).
              wrap={(content) => (
                <Link
                  to={`/subjects/${course.id}`}
                  className="card subject-card"
                >
                  {content}
                </Link>
              )}
            />
          ))}
        </div>
      )}
    </div>
  );
}
