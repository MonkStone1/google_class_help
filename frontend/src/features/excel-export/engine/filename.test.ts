import { describe, expect, it } from "vitest";

import { buildFilename, sanitizeFilename } from "./filename.ts";
import { testPreset } from "./testFixture.ts";

describe("sanitizeFilename", () => {
  it("replaces every character the three operating systems treat specially", () => {
    // `/ \ : * ? " < > |` each become `_`, one for one, so two courses that
    // differ only in a slash still produce visibly different files.
    expect(sanitizeFilename('Математика 8/А: "В"\\B|C?D*E<F>G')).toBe(
      "Математика 8_А_ _В_\\B_C_D_E_F_G",
    );
  });

  it("drops control characters, which no file system accepts", () => {
    expect(sanitizeFilename("Математика")).toBe("Математ_ика");
  });

  it("never leaves a name made only of punctuation", () => {
    // The failure this prevents: a file called `.xlsx`, which browsers treat as
    // a dotfile with no extension at all.
    expect(sanitizeFilename("///")).toBe("_course");
    expect(sanitizeFilename("   ")).toBe("_course");
    expect(sanitizeFilename(null)).toBe("_course");
  });

  it("collapses runs of whitespace so one course cannot produce two names", () => {
    expect(sanitizeFilename("Математика  8   А")).toBe("Математика 8 А");
  });

  it("strips trailing dots and spaces, which Windows silently drops", () => {
    expect(sanitizeFilename("Математика 8. ")).toBe("Математика 8");
  });

  it("keeps the name short enough for a 260-character Windows path", () => {
    const name = sanitizeFilename("Я".repeat(500));

    expect(name.length).toBe(100);
  });
});

describe("buildFilename", () => {
  it("joins the course name and the preset's own suffix", () => {
    expect(buildFilename("Математика", testPreset)).toBe(
      "Математика_fixture.xlsx",
    );
  });

  it("sanitizes the course name, keeping the suffix intact", () => {
    expect(buildFilename("Математика 8/А", testPreset)).toBe(
      "Математика 8_А_fixture.xlsx",
    );
  });

  it("falls back to a constant when the course name sanitizes to nothing", () => {
    expect(buildFilename("", testPreset)).toBe("_course_fixture.xlsx");
  });

  it("sanitizes the suffix too, since a preset is just another author", () => {
    const hostile = { ...testPreset, filenameSuffix: "щоденник/чернетка" };

    expect(buildFilename("Математика", hostile)).toBe(
      "Математика_щоденник_чернетка.xlsx",
    );
  });

  it("reads like a file rather than a path", () => {
    // One slash would turn the name into a directory somewhere up the tree.
    const name = buildFilename("../../etc/passwd", testPreset);

    expect(name).not.toContain("/");
    expect(name).not.toContain("\\");
    expect(name.startsWith(".")).toBe(false);
  });

  it("takes the extension from the preset, not from a constant", () => {
    // The regression this guards: a portal that accepts only `.xls` used to get
    // a `.xlsx` and rejected the upload over the name alone.
    expect(buildFilename("Математика", testPreset)).toBe("Математика_fixture.xlsx");
    expect(
      buildFilename("Математика", { ...testPreset, fileExtension: "xls" }),
    ).toBe("Математика_fixture.xls");
  });

  it("does not let a preset smuggle a path or a second extension into the name", () => {
    const hostile = { ...testPreset, fileExtension: "xls/../../etc/passwd" };

    const name = buildFilename("Математика", hostile);

    expect(name).not.toContain("/");
    expect(name).not.toContain("\\");
    expect(name.endsWith(".xls_.._.._etc_passwd")).toBe(true);
  });

  it("strips a leading dot, since the extension is written without one", () => {
    expect(buildFilename("Математика", { ...testPreset, fileExtension: ".xls" })).toBe(
      "Математика_fixture.xls",
    );
  });
});
