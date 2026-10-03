/**
 * The grades strings, en.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/en/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const en_grades = {
  "grades.title": "Grades",
  "grades.overall": "Overall average: {value}%",
  "grades.empty": "No grades yet",
  "grades.emptyHint": "Grades appear here after your teachers return graded work in Google Classroom.",
  "grades.average": "Average: {value}%",
  "grades.noGrades": "No grades yet",
  "studentGrades.attachments": "Attachments ({count})",
} as const;
