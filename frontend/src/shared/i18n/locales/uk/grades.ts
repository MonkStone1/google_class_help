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
  // Графік динаміки оцінок (ADR-0042): одна лінія за шкалою оцінок 1…12.
  "grades.chart.open": "Графік",
  "grades.chart.title": "Динаміка оцінок",
  "grades.chart.close": "Закрити",
  "grades.chart.ariaLabel": "Динаміка оцінок — {course}",
  "grades.chart.axis.grade": "Оцінка",
  "grades.chart.axis.date": "Дата",
  "grades.chart.tooltip.grade": "Оцінка {grade}",
  "grades.chart.tooltip.points": "{points} / {max}",
  "grades.chart.tooltip.due": "Термін {date}",
  "grades.chart.tooltip.noDue": "Без терміну",
  "grades.chart.empty": "Замало виставлених робіт для графіка",
  "grades.chart.table.caption": "Дані динаміки оцінок",
  "grades.chart.table.task": "Завдання",
  "grades.chart.table.date": "Дата",
  "grades.chart.table.grade": "Оцінка",
  "grades.chart.table.gradeValue": "{grade} ({points} / {max})",
  "grades.chart.noAxisTask": "№{n}",
} as const;
