import type { ExportPreset } from "./types.ts";

/**
 * The download file name (ADR-0041).
 *
 * A course name is teacher-typed free text, and a course called `Математика
 * 8/А` must not produce a file whose name the browser silently rewrites into
 * `Математика 8_А.xlsx` — or, worse, a path. Two rules follow from that:
 *
 * - **sanitize** every character Windows, macOS or Linux treats specially, and
 *   collapse what is left so the name cannot end in a space or a dot;
 * - **fall back** to a constant instead of an empty name, because browsers
 *   treat `".xls"` as a dotfile with no extension.
 *
 * The length cap is not cosmetic: Windows Explorer refuses paths over 260
 * characters, and the suffix is appended on top of the course name.
 */

/** `< > : " / \ | ? *` — what the three operating systems reject in a name. */
const ILLEGAL = /[<>:"/\\|?*]/g;

/** Long enough for any real course name, short enough for a 260-char path. */
const MAX_LENGTH = 100;

/** Used when the name sanitizes down to nothing. */
const FALLBACK = "_course";

/**
 * One character the file name may keep.
 *
 * Control characters are dropped HERE rather than in the pattern above: a range
 * of `\u0000-\u001f` escapes inside an otherwise printable class is unreadable,
 * and it is exactly what `no-control-regex` objects to.
 */
function isAllowedChar(char: string): boolean {
  return (char.codePointAt(0) ?? 0) > 0x1f && !ILLEGAL.test(char);
}

/**
 * File-system-safe stem for a teacher-typed course name.
 *
 * The fallback triggers not only on an EMPTY result but on one with no word
 * characters left: `///` would otherwise sanitize to `___`, which is a legal
 * name that tells the teacher nothing about which course the file belongs to.
 */
export function sanitizeFilename(raw: string | null | undefined): string {
  const cleaned = [...(raw ?? "")]
    // Anything rejected becomes `_`, so two different courses that differ only
    // in a slash still produce visibly different files.
    .map((char) => (isAllowedChar(char) ? char : "_"))
    .join("")
    // Any run of whitespace becomes one space: "Математика  8  А" and
    // "Математика 8 А" must produce the same file.
    .replace(/\s+/g, " ")
    // Trailing dots and spaces are stripped by Windows, which would make the
    // name on disk differ from the one the browser was given.
    .replace(/^[.\s]+|[.\s]+$/g, "")
    .trim()
    .slice(0, MAX_LENGTH)
    .trim();
  return /[\p{L}\p{N}]/u.test(cleaned) ? cleaned : FALLBACK;
}

/**
 * `<course>_<preset suffix>.<preset extension>`, both halves sanitized.
 *
 * The suffix goes through the same sanitizer, but its leading underscore is
 * dropped before it is joined: that underscore is the separator between the two
 * halves, not a stray character a preset author had to escape.
 *
 * The EXTENSION is the preset's too, not a constant here. A portal that takes
 * only `.xls` rejects a workbook over its name alone, and "the engine happens to
 * write `.xlsx`" is not a decision the engine is entitled to make.
 */
export function buildFilename(
  courseName: string | null | undefined,
  preset: ExportPreset,
): string {
  const stem = sanitizeFilename(courseName);
  const suffix = sanitizeFilename(preset.filenameSuffix).replace(/^_+/, "");
  // Sanitized like the rest of the name: a preset must not be able to inject a
  // dot, a slash or a second extension into the file the browser is handed.
  const extension = sanitizeFilename(preset.fileExtension).replace(/^\.+/, "");
  return `${stem}_${suffix}.${extension}`;
}