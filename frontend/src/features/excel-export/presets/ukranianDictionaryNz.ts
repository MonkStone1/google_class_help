import type { ExportPreset, ExportSource } from "../engine/types.ts";

/**
 * The `ukranian_dictionary_nz` preset (ADR-0041).
 *
 * Everything that makes this file THE Ukrainian dictionary format rather than
 * "an export" lives here: the five columns and their order, the cleaning rules
 * for the content column, the URL replacement in the homework column, the
 * `dd.mm.yyyy` date format and the file-name suffix. The engine knows none of
 * it, and the UI never hardcodes it — which is why a Russian or an English
 * preset will be a new file and a new dictionary entry, not a new branch
 * anywhere else.
 *
 * The column HEADERS are Ukrainian on purpose and are NOT localized. They are
 * the contract with the importer at `ukranian-dictionary-nz.ua`; an English UI
 * still exports Ukrainian headers, and that is the correct behaviour.
 */

/** `Урок` as a whole word: `Урок 15`, `урок №7`, but never `уроки`. */
const LESSON_WORD = /(^|[^\p{L}])урок(?![\p{L}])/giu;

/** A `DD.MM.YYYY` date, in either position. */
const DATE = /\d{1,2}\.\d{2}\.\d{4}/g;

/** Any http(s) link; the character class stops at the delimiters of prose. */
const URL = /\bhttps?:\/\/[^\s<>()[\]]+/giu;

/** What a link is replaced with — the site's own wording, not a URL. */
const LINK_LABEL = "(Google classroom)";

/**
 * Punctuation that only exists because something was removed from beside it.
 *
 * `.` is deliberately absent: `15.` is a lesson number, not an orphan left by
 * deleting a date, and trimming it would change the meaning of the row.
 */
const ORPHAN_PUNCTUATION = /^[\s:,\-–—]+|[\s:,\-–—]+$/gu;

/**
 * `Урок 15. 20.09.2026 Алгоритми` → `15. Алгоритми`.
 *
 * Rules, in order (ADR-0041):
 * 1. drop the word `Урок` on a word boundary, case-insensitively;
 * 2. drop every date;
 * 3. collapse the whitespace and newlines the removals left behind;
 * 4. trim punctuation that is now dangling at either end — but keep the dot
 *    of a lesson number, which is not an orphan;
 * 5. if what is left is empty, fall back to the ORIGINAL title, because an
 *    empty diary entry is worse than a redundant one.
 */
export function transformContent(title: string): string {
  const stripped = title
    .replace(LESSON_WORD, "$1")
    .replace(DATE, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(ORPHAN_PUNCTUATION, "")
    .trim();
  return stripped.length > 0 ? stripped : title;
}

/**
 * `Прочитати матеріал https://example.com/test` →
 * `Прочитати матеріал (Google classroom)`.
 *
 * EVERY link is replaced, not the first one: a homework with two links must not
 * export one dead Classroom URL and one placeholder. A missing description
 * becomes an empty cell, never the string "null".
 *
 * The label is capital-G because that is the spelling in the reference file the
 * teacher already imports (`(Google classroom)`); a lowercase `g` would make
 * every homework line differ from the diary it is supposed to match.
 *
 * Line breaks are KEPT: the reference homework is a numbered list split over
 * real newlines, and collapsing it into one line would produce a wall of text
 * where the teacher wrote four points.
 */
export function transformHomework(
  description: string | null | undefined,
): string {
  return (description ?? "").replace(URL, LINK_LABEL).trim();
}

/**
 * The assignment creation date as LOCAL midnight.
 *
 * The naive `new Date(created_at)` is UTC when the string carries no offset,
 * and ExcelJS converts a `Date` to a serial by UTC too — together those turn
 * 20.09 into 19.09 in every zone east of Greenwich (ADR-0041). Rebuilding the
 * day from its parts is what makes the file read 20.09.2026 everywhere.
 */
function defaultDate(createdAt: string | null | undefined): Date | null {
  if (!createdAt) return null;
  const parsed = new Date(createdAt);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Date(
    parsed.getFullYear(),
    parsed.getMonth(),
    parsed.getDate(),
  );
}

/** The preset itself. Registered by the feature, not by the engine. */
export const ukranianDictionaryNzPreset: ExportPreset = {
  id: "ukranian_dictionary_nz",
  labelKey: "export.preset.ukranian_dictionary_nz",
  worksheetName: "Щоденник",
  // The five headers, in the order the site reads them: the sign, the date,
  // the content, the homework under its full name, and the teacher's own
  // `Заміна` column. `№` and `Домашнє завдання` are what the importer expects —
  // shortening either of them back to a header word would make the file
  // unimportable, and so would leaving out `Заміна`, which the reference file
  // carries in every row.
  //
  // There is deliberately NO `headerFill` here: no bold, no shading, no font
  // size of our own. Everything is written in the workbook's own default type,
  // so every cell in the file is the same size and weight (ADR-0041).
  columns: [
    { key: "number", header: "№", kind: "number", width: 6 },
    {
      // The day is written as the TEXT `DD.MM.YYYY`, exactly as the reference
      // diary stores it. Two reasons, and the second is the one that bit us:
      // the importer reads this column as text, and a text cell cannot carry a
      // time of day — a real date cell had `21:00:00` in it, because the
      // creation stamp that produced it was an evening one. The teacher still
      // edits the day in the preview; only what lands in the file is text.
      key: "date",
      header: "Дата",
      kind: "date",
      width: 12,
      writeAsText: true,
    },
    {
      key: "content",
      header: "Зміст",
      kind: "text",
      width: 46,
      wrap: true,
      text: (source: ExportSource) => transformContent(source.title),
    },
    {
      key: "homework",
      header: "Домашнє завдання",
      kind: "text",
      width: 60,
      wrap: true,
      text: (source: ExportSource) => transformHomework(source.description),
    },
    {
      // `Заміна` — "replacement/substitute lesson". It is the teacher's OWN
      // column: the reference file keeps it present and EMPTY in every row,
      // because it is filled in by hand when a lesson is moved. Exporting it
      // empty is what matches the file, and dropping it would break a file
      // whose later columns are addressed by position.
      key: "substitute",
      header: "Заміна",
      kind: "text",
      width: 30,
      wrap: true,
      text: () => "",
    },
  ],
  // `date: "General"` and not `dd.mm.yyyy` on purpose: the `Дата` cell holds
  // TEXT, and a number format is what a number is displayed with. The
  // `DD.MM.YYYY` the importer wants is in the string itself, not in a style.
  numberFormat: { number: "0", date: "General", text: "General" },
  sort: { primary: "createdAt", tiebreak: "id" },
  filenameSuffix: "електронний_щоденник",
  // The portal takes `.xls` uploads, so that is the name the file must have.
  // The BYTES are still a modern workbook — ExcelJS cannot write the old BIFF
  // format — so this is the extension the importer requires, not a claim about
  // the container. Excel and LibreOffice both open it; Excel may warn once that
  // the extension does not match the content.
  fileExtension: "xls",
  mimeType: "application/vnd.ms-excel",
  defaultDate,
};