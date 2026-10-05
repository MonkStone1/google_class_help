import ExcelJS from "exceljs";
import { describe, expect, it } from "vitest";

import { buildRows, formatDayInput } from "./rows.ts";
import type { ExportPreset, ExportRow, ExportSource } from "./types.ts";
import { buildWorkbookBuffer, fillWorksheet } from "./workbook.ts";
import { testPreset } from "./testFixture.ts";

/** Reads a generated buffer back as a workbook. */
async function readBack(buffer: ArrayBuffer): Promise<ExcelJS.Workbook> {
  const workbook = new ExcelJS.Workbook();
  // Round-tripping is the only honest check that a REAL xlsx was produced: an
  // array of similar-looking values would pass every assertion below.
  await workbook.xlsx.load(
    Buffer.from(new Uint8Array(buffer)) as unknown as ExcelJS.Buffer,
  );
  return workbook;
}

/** The single sheet of a generated workbook, by name. */
async function sheetOf(
  preset: ExportPreset,
  rows: readonly ExportRow[],
  name: string,
): Promise<ExcelJS.Worksheet> {
  const buffer = await buildWorkbookBuffer(preset, rows);
  return (await readBack(buffer)).getWorksheet(name) as ExcelJS.Worksheet;
}

function makeSource(overrides: Partial<ExportSource> = {}): ExportSource {
  return {
    id: "w1",
    title: "Урок 15. 20.09.2026 Алгоритми",
    description: "Прочитати https://example.com/test",
    created_at: "2026-09-20T10:00:00",
    course_name: "Математика",
    ...overrides,
  };
}

/**
 * A SECOND preset, declared here.
 *
 * This is the test of the whole architecture: it has different columns, a
 * different sheet and different widths, and it is built by the same engine
 * functions with no change to them. If this passes, "another preset without
 * touching the engine" is a fact rather than a promise.
 */
const otherPreset: ExportPreset = {
  ...testPreset,
  id: "second_format",
  worksheetName: "Another",
  columns: [
    { key: "seq", header: "№", kind: "number", width: 6 },
    { key: "note", header: "ПРИМІТКА", kind: "text", width: 44, wrap: true },
  ],
  numberFormat: { number: "0", date: "dd.mm.yyyy", text: "@" },
};

describe("buildWorkbookBuffer", () => {
  it("produces a workbook a real xlsx reader can open", async () => {
    const buffer = await buildWorkbookBuffer(testPreset, [
      { assignmentId: "w1", values: { seq: 1, when: null, body: "X", note: "" } },
    ]);

    expect(buffer.byteLength).toBeGreaterThan(0);
    const workbook = await readBack(buffer);
    expect(workbook.worksheets).toHaveLength(1);
    expect(workbook.getWorksheet("Fixture")).toBeDefined();
  });

  it("names the sheet the way the preset asked, not the way the engine decided", async () => {
    const workbook = await readBack(
      await buildWorkbookBuffer(otherPreset, []),
    );

    expect(workbook.getWorksheet("Another")).toBeDefined();
    expect(workbook.getWorksheet("Fixture")).toBeUndefined();
  });

  it("builds a DIFFERENT preset with the same engine, untouched", async () => {
    // The extensibility claim of ADR-0041, made executable.
    const sheet = await sheetOf(
      otherPreset,
      [{ assignmentId: "w1", values: { seq: 1, note: "Примітка" } }],
      "Another",
    );

    expect(sheet.getRow(1).values).toEqual([undefined, "№", "ПРИМІТКА"]);
    expect(sheet.getColumn(2).width).toBe(44);
  });

  it("writes headers in the preset's column order", async () => {
    const sheet = await sheetOf(testPreset, [], "Fixture");

    expect(sheet.getRow(1).values).toEqual([
      undefined,
      "SEQ",
      "WHEN",
      "BODY",
      "NOTE",
    ]);
  });

  it("applies the widths the preset declared", async () => {
    const sheet = await sheetOf(testPreset, [], "Fixture");

    expect(sheet.getColumn(1).width).toBe(5);
    expect(sheet.getColumn(3).width).toBe(30);
  });
});

describe("the cells themselves", () => {
  it("keeps a date a real Date with dd.mm.yyyy, in every timezone", async () => {
    // Run this file under TZ=Europe/Kyiv and under TZ=UTC: both must read
    // 20.09.2026. ExcelJS serializes by UTC, so a naive `new Date("…")` would
    // land on 19.09 east of Greenwich (ADR-0041).
    const sheet = await sheetOf(
      testPreset,
      buildRows(testPreset, [makeSource()]),
      "Fixture",
    );
    const cell = sheet.getRow(2).getCell(2);

    expect(cell.value).toBeInstanceOf(Date);
    expect(cell.numFmt).toBe("dd.mm.yyyy");
    expect(formatDayInput(cell.value as Date)).toBe("2026-09-20");
  });

  it("writes a date column as DD.MM.YYYY text when the preset asks for it", async () => {
    // The opt-in the diary preset uses, proved HERE so it stays a property of
    // the engine rather than of one preset: same rows, same engine, a column
    // that says `writeAsText` and a column that does not.
    const textDates: ExportPreset = {
      ...testPreset,
      columns: [
        ...testPreset.columns.map((column) =>
          column.key === "when" ? { ...column, writeAsText: true } : column,
        ),
      ],
    };
    const rows = buildRows(testPreset, [makeSource({ created_at: "2026-09-20T21:00:00" })]);

    const asText = await sheetOf(textDates, rows, "Fixture");
    const asDate = await sheetOf(testPreset, rows, "Fixture");

    // Text: the day alone, and the evening time of day is simply not there.
    expect(asText.getRow(2).getCell(2).value).toBe("20.09.2026");
    // Unchanged default: a preset that does not ask still gets a real date.
    expect(asDate.getRow(2).getCell(2).value).toBeInstanceOf(Date);
  });

  it("leaves the day cell empty rather than writing a stray time for it", async () => {
    const textDates: ExportPreset = {
      ...testPreset,
      columns: [
        ...testPreset.columns.map((column) =>
          column.key === "when" ? { ...column, writeAsText: true } : column,
        ),
      ],
    };
    const sheet = await sheetOf(
      textDates,
      [{ assignmentId: "w1", values: { seq: 1, when: null, body: "X", note: "" } }],
      "Fixture",
    );

    expect(sheet.getRow(2).getCell(2).value).toBeNull();
  });

  it("numbers rows as numbers, which is what the importer expects", async () => {
    const sheet = await sheetOf(
      testPreset,
      buildRows(testPreset, [makeSource(), makeSource({ id: "w2" })]),
      "Fixture",
    );

    expect(sheet.getRow(2).getCell(1).value).toBe(1);
    expect(sheet.getRow(3).getCell(1).value).toBe(2);
    expect(typeof sheet.getRow(2).getCell(1).value).toBe("number");
  });

  it("leaves an undated row's date cell empty rather than writing garbage", async () => {
    const sheet = await sheetOf(
      testPreset,
      buildRows(testPreset, [makeSource({ created_at: null })]),
      "Fixture",
    );

    expect(sheet.getRow(2).getCell(2).value).toBeNull();
  });

  it("wraps a long text and keeps every character of it", () => {
    const long = "Я".repeat(600);
    const rows: ExportRow[] = [
      { assignmentId: "w1", values: { seq: 1, when: null, body: long, note: "" } },
    ];

    const sheet = new ExcelJS.Workbook().addWorksheet("Direct");
    fillWorksheet(sheet, testPreset, rows);

    const cell = sheet.getRow(2).getCell(3);
    expect(cell.alignment?.wrapText).toBe(true);
    expect(cell.value).toBe(long);
  });

  it("styles the header row bold on the preset's fill", () => {
    // The engine still SUPPORTS a styled header — the fixture declares one.
    const sheet = new ExcelJS.Workbook().addWorksheet("Direct");
    fillWorksheet(sheet, testPreset, []);

    const header = sheet.getRow(1).getCell(1);
    expect(header.font?.bold).toBe(true);
    expect(header.alignment?.vertical).toBe("middle");
    expect(header.fill).toMatchObject({ type: "pattern", pattern: "solid" });
  });

  it("writes a plain header when the preset declares no styling", () => {
    // …and does NOT impose one: a preset that asks for nothing gets nothing,
    // which is how the diary file comes out one uniform size (ADR-0041).
    const sheet = new ExcelJS.Workbook().addWorksheet("Direct");
    fillWorksheet(sheet, { ...testPreset, headerFill: undefined }, []);

    const header = sheet.getRow(1).getCell(1);
    expect(header.font ?? {}).toEqual({});
    expect(header.fill ?? null).toBeNull();
    expect(header.alignment ?? null).toBeNull();
  });
});
