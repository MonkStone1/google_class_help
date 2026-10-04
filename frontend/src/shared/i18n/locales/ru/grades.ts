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
  // График динамики оценок (ADR-0042): одна линия сырых баллов Classroom по
  // шкале, которую пользователь выбрал в настройках, и даты внизу.
  "grades.chart.open": "График",
  "grades.chart.title": "Динамика оценок",
  "grades.chart.close": "Закрыть",
  "grades.chart.ariaLabel": "Динамика оценок — {course}",
  "grades.chart.axis.score": "Балл",
  "grades.chart.axis.date": "Дата",
  "grades.chart.tooltip.score": "{score} балл.",
  "grades.chart.tooltip.points": "{points} / {max}",
  "grades.chart.tooltip.due": "Срок {date}",
  "grades.chart.tooltip.noDue": "Без срока",
  "grades.chart.empty": "Слишком мало выставленных работ для графика",
  "grades.chart.table.caption": "Данные динамики оценок",
  "grades.chart.table.task": "Задание",
  "grades.chart.table.date": "Дата",
  "grades.chart.table.score": "Балл",
  "grades.chart.table.scoreValue": "{score} / {max}",
  "grades.chart.noAxisTask": "№{n}",
} as const;
