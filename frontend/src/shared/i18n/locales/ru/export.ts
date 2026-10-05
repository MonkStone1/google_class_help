/**
 * The Excel-export strings, ru.
 *
 * The `dateHint` text is verbatim the wording the task specified, in Russian —
 * the same reason as in `uk`: the sentence tells the teacher where the date
 * came from and that they may change it, so it is not reworded here. The
 * reminder that changes are remembered is `dateMemory`, a separate key.
 */
export const ru_export = {
  "export.button": "Экспортировать в Excel",
  "export.title": "Экспорт курса в Excel",
  "export.preset": "Формат экспорта",
  "export.preset.ukranian_dictionary_nz": "ukranian-dictionary-nz.ua",
  "export.dateHint":
    "Дата по умолчанию берётся с даты создания задания в Google Classroom. При необходимости её можно изменить перед экспортом.",
  "export.dateMemory":
    "Изменённые даты запоминаются на этом компьютере, поэтому следующий экспорт начинается с них. Если очистить поле, снова будет дата создания задания.",
  "export.dateColumn": "Дата",
  "export.cancel": "Отмена",
  "export.submit": "Экспортировать",
  "export.working": "Готовим файл…",
  "export.done": "Файл загружен.",
  "export.empty": "Нет заданий для экспорта",
  "export.missingDates": "{count} заданий без даты",
  "export.close": "Закрыть",
  "export.error.noAssignments": "Нет заданий для экспорта.",
  "export.error.invalidPreset": "Этот формат экспорта недоступен.",
  "export.error.invalidData":
    "Некоторые задания содержат данные, которые нельзя экспортировать.",
  "export.error.invalidDate": "Одна из дат не является корректной датой.",
  "export.error.build": "Не удалось создать файл Excel.",
  "export.error.download":
    "Не удалось сохранить файл. Проверьте настройки браузера.",
} as const;