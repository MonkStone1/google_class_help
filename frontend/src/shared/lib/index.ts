/**
 * The public API of `shared/lib` — pure functions, no React (guardrail #2).
 *
 * Three unrelated concerns that share no state: class names (`cn`), calendar
 * and score formatting (`dates`), and the URL round-trip of the assignment
 * filters (`url`). They are one slice because they are one layer; they are
 * separate files because a change to filter parsing should not have to survive
 * a change to date formatting.
 */

export { cn } from "./cn.ts";
export { LOCALE } from "./dates.ts";
export type { RelativeDayLabel } from "./dates.ts";
export {
  createdTime,
  dayKey,
  detectLanguage,
  formatDate,
  formatDateTimeShort,
  formatPoints,
  formatTime,
  isSameDay,
  parseDue,
  percentOf,
  relativeDayLabel,
  setLocale,
  startOfDay,
  toLocalDate,
} from "./dates.ts";
export {
  DUE_FILTER_KEYS,
  canonicalDue,
  canonicalStatuses,
  formatCourseFilter,
  formatDueFilter,
  formatStatusFilter,
  normalizeCollapsedCourses,
  normalizeCourseFilter,
  normalizeDueFilter,
  normalizeStatusFilter,
  parseCourseFilter,
  parseDueFilter,
  parseStatusFilter,
  pruneCourseSelection,
  STATUS_FILTER_KEYS,
} from "./url.ts";