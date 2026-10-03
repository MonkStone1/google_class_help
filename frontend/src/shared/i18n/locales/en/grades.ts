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
  // The grade-trend chart (ADR-0042). Axis titles are short because they sit
  // inside the plot; the tooltip and the hidden table carry the long forms.
  "grades.chart.open": "Chart",
  "grades.chart.title": "Grade trend",
  "grades.chart.close": "Close",
  "grades.chart.ariaLabel": "Grade trend for {course}",
  "grades.chart.axis.percent": "Score, %",
  "grades.chart.axis.points": "Points",
  "grades.chart.axis.task": "Assignment",
  "grades.chart.legend.points": "Points earned",
  "grades.chart.legend.percent": "Score, %",
  "grades.chart.legend.average": "Course average",
  "grades.chart.tooltip.grade": "{points} / {max}",
  "grades.chart.tooltip.due": "Due {date}",
  "grades.chart.tooltip.noDue": "No deadline",
  "grades.chart.empty": "Not enough graded work for a chart",
  "grades.chart.table.caption": "Grade trend data",
  "grades.chart.table.task": "Assignment",
  "grades.chart.table.points": "Points",
  "grades.chart.table.percent": "Score, %",
  "grades.chart.noAxisTask": "#{n}",
} as const;
