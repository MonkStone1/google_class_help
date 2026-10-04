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
  // The grade-trend chart (ADR-0042). The chart is ONE line of the RAW points
  // Classroom stores, on the scale the user picked in Settings, with dates
  // underneath — so it needs no legend: there is nothing to tell apart.
  "grades.chart.open": "Chart",
  "grades.chart.title": "Grade trend",
  "grades.chart.close": "Close",
  "grades.chart.ariaLabel": "Grade trend for {course}",
  "grades.chart.axis.score": "Points",
  "grades.chart.axis.date": "Date",
  "grades.chart.tooltip.score": "{score} points",
  "grades.chart.tooltip.points": "{points} / {max}",
  "grades.chart.tooltip.due": "Due {date}",
  "grades.chart.tooltip.noDue": "No deadline",
  "grades.chart.empty": "Not enough graded work for a chart",
  "grades.chart.table.caption": "Grade trend data",
  "grades.chart.table.task": "Assignment",
  "grades.chart.table.date": "Date",
  "grades.chart.table.score": "Points",
  "grades.chart.table.scoreValue": "{score} / {max}",
  "grades.chart.noAxisTask": "#{n}",
} as const;
