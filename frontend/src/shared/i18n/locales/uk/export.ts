/**
 * The Excel-export strings, uk.
 *
 * The `dateHint` text is verbatim the wording the task specified, in Ukrainian:
 * a teacher reading this sentence is being told where the date came from and
 * that they may change it, and rewording it would change what they were told.
 *
 * `dateMemory` is a SEPARATE sentence added next to it, not an edit of it. It
 * says the one thing `dateHint` does not: the dialog now remembers the dates,
 * so "you can change it" no longer means "again, every time". Keeping it apart
 * is what lets the mandated wording stay verbatim.
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
  "export.dateMemory":
    "Зміниті дати запам’ятовуються на цьому комп’ютері, тому наступний експорт починається з них. Якщо очистити поле, знову буде дата створення завдання.",
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