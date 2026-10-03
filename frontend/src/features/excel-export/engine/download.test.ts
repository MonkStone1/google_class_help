import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveBuffer, XLSX_MIME } from "./download.ts";

const created: string[] = [];
const revoked: string[] = [];

describe("saveBuffer", () => {
  let clicks: HTMLAnchorElement[];

  beforeEach(() => {
    created.length = 0;
    revoked.length = 0;
    clicks = [];
    // jsdom implements neither object URLs nor anchor downloads, so both are
    // observed here rather than mocked away: the assertions are about WHAT the
    // function asks the browser to do.
    URL.createObjectURL = vi.fn((blob: Blob) => {
      created.push(String(blob.size));
      return `blob:mock/${created.length}`;
    });
    URL.revokeObjectURL = vi.fn((url: string) => {
      revoked.push(url);
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(
      function click(this: HTMLAnchorElement) {
        clicks.push(this);
      },
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("clicks a download anchor carrying the requested file name", () => {
    saveBuffer(new ArrayBuffer(8), "Математика_щоденник.xlsx");

    expect(clicks).toHaveLength(1);
    expect(clicks[0].download).toBe("Математика_щоденник.xlsx");
    expect(clicks[0].href).toContain("blob:mock/");
  });

  it("serves the bytes as a real .xlsx, not as something the browser guesses", () => {
    saveBuffer(new ArrayBuffer(1234), "diary.xlsx");

    // The size is the observable part of the Blob; the type is what makes the
    // browser offer "Open with Excel" instead of "Save as unknown file".
    expect(created).toEqual(["1234"]);
    expect(XLSX_MIME).toContain("spreadsheetml.sheet");
  });

  it("releases the object URL, or every export would leak a workbook", () => {
    const url = saveBuffer(new ArrayBuffer(8), "diary.xlsx");

    expect(revoked).toEqual([url]);
  });

  it("leaves no anchor in the document", () => {
    saveBuffer(new ArrayBuffer(8), "diary.xlsx");

    expect(document.querySelectorAll("a[download]")).toHaveLength(0);
  });

  it("still cleans up when the click throws", () => {
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {
      throw new Error("popup blocked");
    });

    expect(() => saveBuffer(new ArrayBuffer(8), "diary.xlsx")).toThrow();
    expect(revoked).toHaveLength(1);
    expect(document.querySelectorAll("a[download]")).toHaveLength(0);
  });
});