/**
 * The grades strings, ru.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/ru/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const ru_grades = {
  "grades.title": "Оценки",
  "grades.overall": "Общий средний балл: {value}%",
  "grades.empty": "Оценок пока нет",
  "grades.emptyHint": "Оценки появятся, когда учителя вернут проверенные работы в Google Classroom.",
  "grades.average": "Средний балл: {value}%",
  "grades.noGrades": "Оценок пока нет",
  "studentGrades.attachments": "Вложения ({count})",
} as const;
