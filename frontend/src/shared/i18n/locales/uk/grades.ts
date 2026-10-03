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
  // Графік динаміки оцінок (ADR-0042).
  "grades.chart.open": "Графік",
  "grades.chart.title": "Динаміка оцінок",
  "grades.chart.close": "Закрити",
  "grades.chart.ariaLabel": "Динаміка оцінок — {course}",
  "grades.chart.axis.percent": "Бал, %",
  "grades.chart.axis.points": "Бали",
  "grades.chart.axis.task": "Завдання",
  "grades.chart.legend.points": "Отримані бали",
  "grades.chart.legend.percent": "Бал, %",
  "grades.chart.legend.average": "Середній бал курсу",
  "grades.chart.tooltip.grade": "{points} / {max}",
  "grades.chart.tooltip.due": "Термін {date}",
  "grades.chart.tooltip.noDue": "Без терміну",
  "grades.chart.empty": "Замало виставлених робіт для графіка",
  "grades.chart.table.caption": "Дані динаміки оцінок",
  "grades.chart.table.task": "Завдання",
  "grades.chart.table.points": "Бали",
  "grades.chart.table.percent": "Бал, %",
  "grades.chart.noAxisTask": "№{n}",
} as const;
