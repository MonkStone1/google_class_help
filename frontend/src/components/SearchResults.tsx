import { BookOpen, ListChecks } from "lucide-react";
import type { ReactNode } from "react";

import { formatDate, parseDue } from "../dates.ts";
import { useI18n } from "../i18n.ts";
import { cn } from "../lib/cn.ts";
import { courseSubtitle } from "../lib/search.ts";
import type { SearchHit } from "../lib/search.ts";
import type { Assignment } from "../types.ts";

type Props = {
  query: string;
  hits: SearchHit[];
  activeIndex: number;
  onSelect: (hit: SearchHit) => void;
  onHover: (index: number) => void;
};

type RowModel = {
  key: string;
  group: "assignment" | "course";
  title: string;
  subtitle: string;
  icon: ReactNode;
};

function toRow(hit: SearchHit, fallbackTeacher: string): RowModel {
  if (hit.type === "assignment") {
    return {
      key: `assignment-${hit.assignment.id}`,
      group: "assignment",
      title: hit.assignment.title,
      subtitle: assignmentSubtitle(hit.assignment),
      icon: <ListChecks size={15} />,
    };
  }
  return {
    key: `course-${hit.course.id}`,
    group: "course",
    title: hit.course.name,
    subtitle: courseSubtitle(hit.course) || fallbackTeacher,
    icon: <BookOpen size={15} />,
  };
}

function assignmentSubtitle(assignment: Assignment): string {
  const due = formatDate(parseDue(assignment.due_at));
  return due ? `${assignment.course_name} · ${due}` : assignment.course_name;
}

export function SearchResults({
  query,
  hits,
  activeIndex,
  onSelect,
  onHover,
}: Props) {
  const { t } = useI18n();

  if (hits.length === 0) {
    return (
      <div
        id="global-search-results"
        className="search-results"
        role="listbox"
        aria-label={t("search.label")}
      >
        <div className="search-empty">{t("search.noResults", { query })}</div>
      </div>
    );
  }

  const rows = hits.map((hit) => toRow(hit, t("subject.noTeacher")));

  return (
    <div
      id="global-search-results"
      className="search-results"
      role="listbox"
      aria-label={t("search.label")}
    >
      {rows.map((row, index) => {
        const previous = index > 0 ? rows[index - 1] : null;
        const showGroup = previous === null || previous.group !== row.group;
        return (
          <div key={row.key}>
            {showGroup ? (
              <div className="search-group-label">
                {row.group === "assignment"
                  ? t("search.assignments")
                  : t("search.subjects")}
              </div>
            ) : null}
            <button
              type="button"
              role="option"
              aria-selected={index === activeIndex}
              className={cn("search-result", index === activeIndex && "active")}
              onMouseEnter={() => onHover(index)}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => onSelect(hits[index])}
            >
              <span className="search-result-icon">{row.icon}</span>
              <span className="search-result-body">
                <span className="search-result-title">{row.title}</span>
                <span className="search-result-sub">{row.subtitle}</span>
              </span>
            </button>
          </div>
        );
      })}
    </div>
  );
}
