import { useMemo } from "react";

import type { I18nKey } from "./i18n.ts";
import type { Assignment, Language } from "./types.ts";

/** BCP-47 locales used by Intl date formatting. */
export const LOCALE: Record<Language, string> = {
  en: "en-US",
  uk: "uk-UA",
  ru: "ru-RU",
};

let currentLocale = "en-US";

/** Switch the locale used by all date formatters (called on language change). */
export function setLocale(locale: string) {
  currentLocale = locale;
}

/**
 * Best-effort initial language from the browser/system.
 *
 * The WHOLE preference list is walked, not just `navigator.language`: a
 * browser whose UI is, say, German can still list Ukrainian second, and that
 * is a better guess for our three dictionaries than dropping straight to
 * English. The first supported tag wins; a list with no supported tag (or a
 * browser that exposes neither list) is English.
 */
export function detectLanguage(): Language {
  const preferred =
    navigator.languages && navigator.languages.length > 0
      ? navigator.languages
      : [navigator.language];
  for (const tag of preferred) {
    const normalized = tag.toLowerCase();
    if (normalized.startsWith("uk")) {
      return "uk";
    }
    if (normalized.startsWith("ru")) {
      return "ru";
    }
    if (normalized.startsWith("en")) {
      return "en";
    }
  }
  return "en";
}

/**
 * Parse a backend sync timestamp (`last_sync`, `last_sync_finished_at`, …)
 * for rendering in the browser's local zone.
 *
 * The backend stores these as naive UTC datetimes serialized without an
 * offset, so `new Date("2026-09-19T00:00:00")` would wrongly read them as
 * local time (stage 7, §26 — UTC rendered in the local zone). A value that
 * already carries an offset (`Z` or `±HH:MM`) is taken at face value.
 */
export function toLocalDate(value: string | null): Date | null {
  if (!value) {
    return null;
  }
  const hasOffset = value.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(value);
  const parsed = new Date(hasOffset ? value : `${value}Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function parseDue(value: string | null): Date | null {
  if (!value) {
    return null;
  }
  // FastAPI serializes naive datetimes without a timezone suffix.
  const cleaned = value.replace("T", " ");
  const match = cleaned.match(
    /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/,
  );
  if (!match) {
    return null;
  }
  const [, y, m, d, h, min, s] = match;
  return new Date(
    Number(y),
    Number(m) - 1,
    Number(d),
    Number(h),
    Number(min),
    Number(s),
  );
}

/** Safe epoch ms for `created_at`; invalid/missing values sort as 0, never NaN. */
export function createdTime(value: string | null | undefined): number {
  if (!value) {
    return 0;
  }
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? 0 : time;
}

export function formatDate(value: Date | null): string {
  if (!value) {
    return "";
  }
  return value.toLocaleDateString(currentLocale, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

export function formatTime(value: Date | null): string {
  if (!value) {
    return "";
  }
  const hours = value.getHours();
  const minutes = value.getMinutes();
  if (hours === 23 && minutes === 59) {
    return "";
  }
  return value.toLocaleTimeString(currentLocale, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDateTimeShort(value: Date | null): string {
  if (!value) {
    return "";
  }
  const now = new Date();
  const sameYear = value.getFullYear() === now.getFullYear();
  return value.toLocaleDateString(currentLocale, {
    day: "numeric",
    month: "short",
    year: sameYear ? undefined : "numeric",
  });
}

export type RelativeDayLabel = { key: I18nKey; count: number };

export function relativeDayLabel(value: Date | null): RelativeDayLabel | null {
  if (!value) {
    return null;
  }
  const today = startOfDay(new Date());
  const diff = Math.round(
    (startOfDay(value).getTime() - today.getTime()) / (24 * 60 * 60 * 1000),
  );
  if (diff === 0) {
    return { key: "date.today", count: 0 };
  }
  if (diff === 1) {
    return { key: "date.tomorrow", count: 0 };
  }
  if (diff === -1) {
    return { key: "date.yesterday", count: 0 };
  }
  if (diff < -1) {
    return { key: "date.daysOverdue", count: Math.abs(diff) };
  }
  return { key: "date.inDays", count: diff };
}

export function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}
export function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

export function dayKey(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function formatPoints(assignment: Assignment): string {
  if (assignment.points === null && assignment.max_points === null) {
    return "";
  }
  if (assignment.points !== null && assignment.max_points !== null) {
    return `${assignment.points} / ${assignment.max_points}`;
  }
  if (assignment.max_points !== null) {
    return `0 / ${assignment.max_points}`;
  }
  return `${assignment.points}`;
}

export function percentOf(assignment: Assignment): number | null {
  if (
    assignment.points === null ||
    assignment.max_points === null ||
    assignment.max_points === 0
  ) {
    return null;
  }
  return Math.round((assignment.points / assignment.max_points) * 100);
}

export function useSortedAssignments(
  assignments: Assignment[],
  sortKey: string,
): Assignment[] {
  return useMemo(() => {
    const copy = [...assignments];
    const priorityRank = { high: 0, medium: 1, low: 2 } as const;
    const due = (a: Assignment) => parseDue(a.due_at)?.getTime() ?? Infinity;
    switch (sortKey) {
      case "priority":
        copy.sort(
          (a, b) =>
            priorityRank[a.priority] - priorityRank[b.priority] ||
            due(a) - due(b),
        );
        break;
      case "grade":
        copy.sort((a, b) => (percentOf(b) ?? -1) - (percentOf(a) ?? -1));
        break;
      case "newest":
        copy.sort(
          (a, b) => createdTime(b.created_at) - createdTime(a.created_at),
        );
        break;
      case "oldest":
        copy.sort(
          (a, b) => createdTime(a.created_at) - createdTime(b.created_at),
        );
        break;
      default:
        copy.sort((a, b) => due(a) - due(b));
    }
    return copy;
  }, [assignments, sortKey]);
}
