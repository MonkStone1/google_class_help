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
    ).toBe("Прочитати матеріал (google classroom)");
  });

  it("replaces EVERY link, not just the first", () => {
    expect(
      transformHomework("Дивитись https://a.test/1 та http://b.test/2"),
    ).toBe("Дивитись (google classroom) та (google classroom)");
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
  it("writes the four headers in the order the site reads them", () => {
    // `№` and the full homework name are what the importer reads; shortening
    // either back to a header word would make the file unimportable.
    expect(preset.columns.map((column) => column.header)).toEqual([
      "№",
      "Дата",
      "Зміст",
      "Домашнє завдання",
    ]);
  });

  it("declares no course-name column, since the name lives in the file name", () => {
    expect(preset.columns.map((column) => column.key)).toEqual([
      "number",
      "date",
      "content",
      "homework",
    ]);
  });

  it("numbers rows as numbers, not as text", () => {
    const [row] = buildRows(preset, [source()]);

    expect(typeof row.values.number).toBe("number");
    expect(row.values.number).toBe(1);
  });

  it("writes a real Date with the dd.mm.yyyy format", () => {
    const [row] = buildRows(preset, [source()]);

    expect(row.values.date).toBeInstanceOf(Date);
    expect(formatDayInput(row.values.date as Date)).toBe("2026-09-20");
    expect(preset.numberFormat.date).toBe("dd.mm.yyyy");
  });

  it("fills the columns from the cleaned title and description", () => {
    const [row] = buildRows(preset, [
      source({ description: "Прочитати https://a.test" }),
    ]);

    expect(row.values.content).toBe("15. Алгоритми");
    expect(row.values.homework).toBe("Прочитати (google classroom)");
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

  it("carries the four headers in the order the importer reads them", async () => {
    const sheet = await reopen(
      await buildWorkbookBuffer(preset, buildRows(preset, [source()])),
    );

    expect(sheet.getRow(1).values).toEqual([
      undefined,
      "№",
      "Дата",
      "Зміст",
      "Домашнє завдання",
    ]);
  });

  it("writes the date as a real Date cell formatted dd.mm.yyyy", async () => {
    const sheet = await reopen(
      await buildWorkbookBuffer(preset, buildRows(preset, [source()])),
    );
    const cell = sheet.getRow(2).getCell(2);

    expect(cell.value).toBeInstanceOf(Date);
    expect(cell.numFmt).toBe("dd.mm.yyyy");
    // 20.09.2026 in every zone: ExcelJS serializes by UTC, so a naive
    // `new Date("2026-09-20")` would read back as 19.09 east of Greenwich.
    expect(formatDayInput(cell.value as Date)).toBe("2026-09-20");
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
      [1, 2, 3, 4].map((column) => row.getCell(column)),
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
      "Математика 8_А_електронний_щоденник.xlsx",
    );
  });

  it("names the file defensively when the course name sanitizes to nothing", () => {
    expect(buildFilename("", preset)).toBe("_course_електронний_щоденник.xlsx");
  });
});
