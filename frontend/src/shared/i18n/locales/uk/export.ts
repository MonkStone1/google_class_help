/**
 * The Excel-export strings, uk.
 *
 * The `dateHint` text is verbatim the wording the task specified, in Ukrainian:
 * a teacher reading this sentence is being told where the date came from and
 * that they may change it, and rewording it would change what they were told.
 *
 * `export.preset.ukranian_dictionary_nz` is the DOMAIN NAME, not a translation,
 * so it is identical in all three dictionaries.
 */
export const uk_export = {
  "export.button": "Експортувати у Excel",
  "export.title": "Експорт курсу у Excel",
  "export.preset": "Формат експорту",
  "export.preset.ukranian_dictionary_nz": "ukranian-dictionary-nz.ua",
  "export.dateHint":
    "Дата за замовчуванням береться з дати створення завдання в Google Classroom. За потреби її можна змінити перед експортом.",
  "export.dateColumn": "Дата",
  "export.cancel": "Скасувати",
  "export.submit": "Експортувати",
  "export.working": "Готуємо файл…",
  "export.done": "Файл завантажено.",
  "export.empty": "Немає завдань для експорту",
  "export.missingDates": "{count} завдань без дати",
  "export.close": "Закрити",
  "export.error.noAssignments": "Немає завдань для експорту.",
  "export.error.invalidPreset": "Цей формат експорту недоступний.",
  "export.error.invalidData":
    "Деякі завдання містять дані, які неможливо експортувати.",
  "export.error.invalidDate": "Одна з дат не є коректною датою.",
  "export.error.build": "Не вдалося створити файл Excel.",
  "export.error.download":
    "Не вдалося зберегти файл. Перевірте налаштування браузера.",
} as const;