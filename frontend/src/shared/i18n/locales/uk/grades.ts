/**
 * The grades strings, uk.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/uk/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const uk_grades = {
  "grades.title": "Оцінки",
  "grades.overall": "Загальний середній бал: {value}%",
  "grades.empty": "Оцінок ще немає",
  "grades.emptyHint": "Оцінки з'являться, коли вчителі повернуть перевірені роботи в Google Classroom.",
  "grades.average": "Середній бал: {value}%",
  "grades.noGrades": "Оцінок ще немає",
  "studentGrades.attachments": "Вкладення ({count})",
} as const;
