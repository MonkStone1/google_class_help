import ExcelJS from "exceljs";
import { describe, expect, it } from "vitest";

import { buildFilename } from "../engine/filename.ts";
import { buildRows, formatDayInput } from "../engine/rows.ts";
import type { ExportSource } from "../engine/types.ts";
import { buildWorkbookBuffer } from "../engine/workbook.ts";
import {
  transformContent,
  transformHomework,
  ukranianDictionaryNzPreset as preset,
} from "./ukranianDictionaryNz.ts";

/** Reads a generated buffer back as a workbook, which is the only real proof. */
async function reopen(buffer: ArrayBuffer): Promise<ExcelJS.Worksheet> {
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(
    Buffer.from(new Uint8Array(buffer)) as unknown as ExcelJS.Buffer,
  );
  return workbook.getWorksheet(preset.worksheetName) as ExcelJS.Worksheet;
}

/**
 * Test strings avoid the Ukrainian letters that have more than one look-alike
 * code point (`і`, `ї`, `є`, `ґ`): a title that differs from the expected one
 * only by an invisible character is a test that fails for the wrong reason and
 * teaches the reader nothing.
 */
function source(overrides: Partial<ExportSource> = {}): ExportSource {
  return {
    id: "w1",
    title: "Урок 15. 20.09.2026 Алгоритми",
    description: null,
    created_at: "2026-09-20T10:00:00",
    course_name: "Математика",
    ...overrides,
  };
}

describe("Зміст: the title is cleaned", () => {
  it("drops the lesson word and the date, keeping the lesson number", () => {
    expect(transformContent("Урок 15. 20.09.2026 Алгоритми")).toBe(
      "15. Алгоритми",
    );
  });

  it("drops every date, not just the first", () => {
    expect(transformContent("Урок 1. 01.09.2026 Теми 05.09.2026")).toBe(
      "1. Теми",
    );
  });

  it("drops a date from the beginning, the middle and the end", () => {
    expect(transformContent("20.09.2026 Урок 3 Теми")).toBe("3 Теми");
    expect(transformContent("Урок 3 20.09.2026 Теми")).toBe("3 Теми");
    expect(transformContent("Урок Теми 20.09.2026")).toBe("Теми");
  });

  it("removes the lesson word only on a word boundary", () => {
    // `Уроки` is a different word: deleting it would corrupt the title.
    expect(transformContent("Уроки 20.09.2026 Теми")).toBe("Уроки Теми");
  });

  it("trims the punctuation the removals orphaned", () => {
    expect(transformContent("Урок: 20.09.2026 Алгоритми")).toBe("Алгоритми");
    expect(transformContent("Урок - 20.09.2026 - Алгоритми")).toBe(
      "Алгоритми",
    );
  });

  it("keeps the dot of a lesson number, which is not an orphan", () => {
    expect(transformContent("Урок 15. 20.09.2026")).toBe("15.");
  });

  it("falls back to the original title when the cleaning empties it", () => {
    // An empty diary entry is worse than a redundant one, and the teacher can
    // still see and fix the row in the preview.
    expect(transformContent("Урок 20.09.2026")).toBe("Урок 20.09.2026");
  });

  it("leaves a title without a date untouched", () => {
    expect(transformContent("Алгоритми")).toBe("Алгоритми");
  });

  it("collapses the newlines a title may contain", () => {
    expect(transformContent("Урок 15.\n20.09.2026\nАлгоритми")).toBe(
      "15. Алгоритми",
    );
  });
});
describe("ДЗ: the description is cleaned", () => {
  it("replaces a link with the site's own wording", () => {
    expect(
      transformHomework("Прочитати матеріал https://example.com/test"),
    ).toBe("Прочитати матеріал (Google classroom)");
  });

  it("replaces EVERY link, not just the first", () => {
    expect(
      transformHomework("Дивитись https://a.test/1 та http://b.test/2"),
    ).toBe("Дивитись (Google classroom) та (Google classroom)");
  });

  it("leaves a description without links untouched", () => {
    expect(transformHomework("Прочитати параграф 15")).toBe(
      "Прочитати параграф 15",
    );
  });

  it("turns a missing description into an empty cell, not into 'null'", () => {
    expect(transformHomework(null)).toBe("");
    expect(transformHomework(undefined)).toBe("");
    expect(transformHomework("")).toBe("");
  });

  it("never writes back into the assignment it read from", () => {
    const assignment = source({ description: "Прочитати https://a.test" });
    const snapshot = structuredClone(assignment);

    transformHomework(assignment.description);
    transformContent(assignment.title);

    expect(assignment).toEqual(snapshot);
  });
});
describe("the preset declares the format the importer expects", () => {
  it("writes the five headers in the order the site reads them", () => {
    // `№` and the full homework name are what the importer reads; shortening
    // either back to a header word would make the file unimportable. `Заміна`
    // is the teacher's own column, present but filled in by hand — the
    // reference file carries it in the header row of every sheet.
    expect(preset.columns.map((column) => column.header)).toEqual([
      "№",
      "Дата",
      "Зміст",
      "Домашнє завдання",
      "Заміна",
    ]);
  });

  it("declares no course-name column, since the name lives in the file name", () => {
    expect(preset.columns.map((column) => column.key)).toEqual([
      "number",
      "date",
      "content",
      "homework",
      "substitute",
    ]);
  });

  it("leaves `Заміна` empty, because the teacher fills it in by hand", () => {
    // The reference file has the column and writes NOTHING into it: a lesson
    // that was moved is annotated after the export, not before it.
    const [row] = buildRows(preset, [
      source({ title: "Урок 1. 04.09.2026 Теми", description: "Прочитати" }),
    ]);

    expect(row.values.substitute).toBe("");
  });

  it("numbers rows as numbers, not as text", () => {
    const [row] = buildRows(preset, [source()]);

    expect(typeof row.values.number).toBe("number");
    expect(row.values.number).toBe(1);
  });

  it("keeps a real Date in the row, so the day stays editable in the preview", () => {
    const [row] = buildRows(preset, [source()]);

    // The ROW is an internal model and holds a real date; only what the
    // workbook writes is text. That split is what lets the teacher still fix a
    // date in the preview while the file gets a plain `DD.MM.YYYY` string.
    expect(row.values.date).toBeInstanceOf(Date);
    expect(formatDayInput(row.values.date as Date)).toBe("2026-09-20");
  });

  it("asks for the date column to be written as text", () => {
    const column = preset.columns.find((item) => item.key === "date");

    expect(column?.kind).toBe("date");
    expect(column?.writeAsText).toBe(true);
    // Text cells are not numbers, so no number format is declared for them:
    // `dd.mm.yyyy` would be a format for a number the cell does not hold.
    expect(preset.numberFormat.date).toBe("General");
  });

  it("names the file with the extension the portal takes", () => {
    expect(preset.fileExtension).toBe("xls");
  });

  it("fills the columns from the cleaned title and description", () => {
    const [row] = buildRows(preset, [
      source({ description: "Прочитати https://a.test" }),
    ]);

    expect(row.values.content).toBe("15. Алгоритми");
    expect(row.values.homework).toBe("Прочитати (Google classroom)");
  });

  it("sorts by the creation date, oldest lesson first", () => {
    const rows = buildRows(preset, [
      source({ id: "b", title: "Урок 2", created_at: "2026-09-21T10:00:00" }),
      source({ id: "a", title: "Урок 1", created_at: "2026-09-20T10:00:00" }),
    ]);

    expect(rows.map((row) => row.values.number)).toEqual([1, 2]);
    expect(rows.map((row) => row.values.content)).toEqual(["1", "2"]);
  });

  it("appends its own suffix to the course name", () => {
    expect(preset.filenameSuffix).toBe("електронний_щоденник");
  });

  });

describe("the generated file, read back as a workbook", () => {
  it("opens as a real .xlsx with the sheet the preset names", async () => {
    const sheet = await reopen(
      await buildWorkbookBuffer(preset, buildRows(preset, [source()])),
    );

    expect(sheet).toBeDefined();
  });

  it("carries the five headers in the order the importer reads them", async () => {
    const sheet = await reopen(
      await buildWorkbookBuffer(preset, buildRows(preset, [source()])),
    );

    expect(sheet.getRow(1).values).toEqual([
      undefined,
      "№",
      "Дата",
      "Зміст",
      "Домашнє завдання",
      "Заміна",
    ]);
  });

  it("writes the day as the text DD.MM.YYYY, with no time of day", async () => {
    // An EVENING creation stamp is the case that matters: `21:00:00` is what the
    // column showed when the cell was a real date. A text cell cannot hold it.
    const sheet = await reopen(
      await buildWorkbookBuffer(
        preset,
        buildRows(preset, [
          source({ created_at: "2026-09-20T21:00:00" }),
        ]),
      ),
    );
    const cell = sheet.getRow(2).getCell(2);

    expect(cell.value).toBe("20.09.2026");
    expect(typeof cell.value).toBe("string");
    expect(String(cell.value)).not.toContain(":");
  });

  it("writes an edited date as text too, and never as the creation time", async () => {
    const sheet = await reopen(
      await buildWorkbookBuffer(
        preset,
        buildRows(preset, [source({ created_at: "2026-09-20T21:00:00" })], {
          w1: "2026-10-01",
        }),
      ),
    );

    expect(sheet.getRow(2).getCell(2).value).toBe("01.10.2026");
  });

  it("leaves the day cell empty when there is no date at all", async () => {
    // Not `Invalid Date` and not a stray `NaN`: an empty cell the teacher can
    // still fill in.
    const sheet = await reopen(
      await buildWorkbookBuffer(
        preset,
        buildRows(preset, [source({ created_at: null })]),
      ),
    );

    expect(sheet.getRow(2).getCell(2).value).toBeNull();
  });

  it("numbers rows as numbers, 1, 2, 3 …", async () => {
    const sheet = await reopen(
      await buildWorkbookBuffer(
        preset,
        buildRows(preset, [
          source({ id: "a", created_at: "2026-09-20T10:00:00" }),
          source({ id: "b", created_at: "2026-09-21T10:00:00" }),
          source({ id: "c", created_at: "2026-09-22T10:00:00" }),
        ]),
      ),
    );

    expect([2, 3, 4].map((n) => sheet.getRow(n).getCell(1).value)).toEqual([
      1, 2, 3,
    ]);
  });

  it("keeps a long homework wrapped and intact, with the links already replaced", async () => {
    const long = "Прочитати параграф. ".repeat(60) + "https://a.test/x";
    const sheet = await reopen(
      await buildWorkbookBuffer(
        preset,
        buildRows(preset, [source({ description: long })]),
      ),
    );
    const cell = sheet.getRow(2).getCell(4);

    expect(cell.alignment?.wrapText).toBe(true);
    expect(String(cell.value)).not.toContain("https://");
    expect(String(cell.value).length).toBeGreaterThan(500);
  });

  it("writes every cell in one uniform typeface — same size, no bold", async () => {
    const sheet = await reopen(
      await buildWorkbookBuffer(preset, buildRows(preset, [source()])),
    );

    // "One size, no formatting" is checked as ABSENCE, not as an empty style
    // object: a workbook read back resolves the default typeface (Calibri 11)
    // for cells that carry a style record and reports `{}` for cells that do
    // not, and both mean the same thing here — nothing was declared. So what
    // must hold is that NO cell brings a weight, a slant, a colour or a size of
    // its own, on the header row or on the data rows.
    const cells = [sheet.getRow(1), sheet.getRow(2)].flatMap((row) =>
      [1, 2, 3, 4, 5].map((column) => row.getCell(column)),
    );
    // "One size" is checked against the workbook's own default: a cell that
    // declares no size resolves to Calibri 11 on read-back, and a cell that
    // declares no size AT ALL reports nothing. Both are the same rendered
    // size, so the check is that every cell lands on that one default and
    // never picks a size of its own.
    const DEFAULT_SIZE = 11;
    const sizes = new Set<number>();
    for (const cell of cells) {
      const font = cell.font ?? {};
      expect(font.bold).toBeFalsy();
      expect(font.italic).toBeFalsy();
      expect(font.strike).toBeFalsy();
      // `Fill` is a union (pattern | gradient), so the "no fill" case is read
      // through a narrowing: no fill at all, or a pattern of `none`.
      const fill = cell.fill;
      expect(fill && "pattern" in fill ? fill.pattern : "none").toBe("none");
      sizes.add(font.size ?? DEFAULT_SIZE);
    }
    // One distinct size across the whole sheet — header and data alike.
    expect([...sizes]).toEqual([DEFAULT_SIZE]);
  });

  it("declares no header styling in the first place", () => {
    // The engine styles a header only when a preset asks for it, so the
    // guarantee above is a property of the PRESET and not of the generator.
    expect(preset.headerFill).toBeUndefined();
  });

  it("names the file after the course, sanitized", () => {
    expect(buildFilename("Математика 8/А", preset)).toBe(
      "Математика 8_А_електронний_щоденник.xls",
    );
  });

  it("names the file defensively when the course name sanitizes to nothing", () => {
    expect(buildFilename("", preset)).toBe("_course_електронний_щоденник.xls");
  });
});
