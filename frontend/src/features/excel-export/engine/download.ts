/**
 * The browser download, the last step of the export (ADR-0041).
 *
 * `Blob` + `URL.createObjectURL` + a synthetic `<a download>` is the only way a
 * page can put a generated file on disk without a server. Two details are not
 * optional:
 *
 * - the object URL MUST be revoked. A Blob stays in memory until its URL is
 *   released, so a teacher who exports a term's worth of courses twenty times
 *   would otherwise leak twenty workbooks;
 * - the anchor is appended to the document before the click. Firefox ignores
 *   `click()` on a detached element, which is a silent "nothing happened".
 */

/** The MIME type ExcelJS-produced workbooks are served with. */
export const XLSX_MIME =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

/** Writes `buffer` to disk as `filename`. Returns the object URL it used. */
export function saveBuffer(
  buffer: ArrayBuffer,
  filename: string,
  mime: string = XLSX_MIME,
): string {
  const url = URL.createObjectURL(new Blob([buffer], { type: mime }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  try {
    anchor.click();
  } finally {
    // Both the element and the URL go away whether or not the click threw;
    // leaving either behind is a leak that only shows up after many exports.
    anchor.remove();
    URL.revokeObjectURL(url);
  }
  return url;
}