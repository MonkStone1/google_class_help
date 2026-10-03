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
  // График динамики оценок (ADR-0042): одна линия по шкале оценок 1…12.
  "grades.chart.open": "График",
  "grades.chart.title": "Динамика оценок",
  "grades.chart.close": "Закрыть",
  "grades.chart.ariaLabel": "Динамика оценок — {course}",
  "grades.chart.axis.grade": "Оценка",
  "grades.chart.axis.date": "Дата",
  "grades.chart.tooltip.grade": "Оценка {grade}",
  "grades.chart.tooltip.points": "{points} / {max}",
  "grades.chart.tooltip.due": "Срок {date}",
  "grades.chart.tooltip.noDue": "Без срока",
  "grades.chart.empty": "Слишком мало выставленных работ для графика",
  "grades.chart.table.caption": "Данные динамики оценок",
  "grades.chart.table.task": "Задание",
  "grades.chart.table.date": "Дата",
  "grades.chart.table.grade": "Оценка",
  "grades.chart.table.gradeValue": "{grade} ({points} / {max})",
  "grades.chart.noAxisTask": "№{n}",
} as const;
