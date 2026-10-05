import { parseDayInput } from "../engine/rows.ts";
import type { DateOverrides } from "../engine/types.ts";

/**
 * The date memory (ADR-0041).
 *
 * A teacher who fixes a lesson date once should not have to fix it again on
 * every export, so the edits are remembered in `localStorage` and read back the
 * next time the dialog opens.
 *
 * **There is exactly ONE slot per course and preset, and every change
 * overwrites it.** It is a snapshot of what the teacher last decided, not a
 * history: no timestamps, no previous versions, nothing to accumulate. The
 * consequence is the useful part — the memory cannot disagree with itself,
 * because there is only ever one answer per row.
 *
 * Two rules keep it honest:
 *
 * - **A row the teacher has not decided falls back to the assignment.** Only a
 *   date that is actually stored is remembered, so clearing the input in the
 *   preview forgets that row and the diary shows the `created_at` date again.
 * - **Only rows the course still has are stored.** A snapshot is pruned against
 *   the assignment ids in hand on every write, so coursework deleted from
 *   Classroom stops taking up space and never reappears as a stale row.
 *
 * Everything read back is re-validated rather than trusted: this is
 * `localStorage`, which any older build, another tab or a hand-editing in
 * devtools can put anything into, and a nonsense date must degrade to "not
 * remembered" instead of reaching the workbook.
 */

/** One key for the whole feature, like `gc-settings` is for the settings store. */
const STORAGE_KEY = "gc-export-dates";

/** `courseId:presetId` — the single slot a course and a preset share. */
function slotOf(courseId: string, presetId: string): string {
  return `${courseId}:${presetId}`;
}

/** The stored shape: slot -> assignment id -> `YYYY-MM-DD`. */
type Store = Record<string, DateOverrides>;

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * A stored value survives only if it is a string the engine would accept as a
 * day, so the memory can never hand the preview a date the rows would reject.
 */
function rememberedDay(value: unknown): string | null {
  return typeof value === "string" && parseDayInput(value) !== null ? value : null;
}

/** The whole store, read defensively; junk is dropped, not thrown. */
function readStore(): Store {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!isPlainObject(parsed)) return {};
    const store: Store = {};
    for (const [slot, dates] of Object.entries(parsed)) {
      if (!isPlainObject(dates)) continue;
      const clean: DateOverrides = {};
      for (const [id, day] of Object.entries(dates)) {
        const valid = rememberedDay(day);
        if (id.length > 0 && valid !== null) clean[id] = valid;
      }
      store[slot] = clean;
    }
    return store;
  } catch {
    // Unreadable or unparseable storage is the same as no memory at all: the
    // teacher sees the `created_at` dates, which is a working export.
    return {};
  }
}

/**
 * What is remembered for this course and preset; `{}` when nothing is.
 *
 * Called once per course+preset change to seed the preview, so a first-time
 * teacher gets the assignment dates and a returning one gets their own.
 */
export function readDateMemory(
  courseId: string,
  presetId: string,
): DateOverrides {
  return readStore()[slotOf(courseId, presetId)] ?? {};
}

/**
 * Replaces the whole slot with `dates`, keeping only real days on assignments
 * the course still has.
 *
 * The assignment takes `knownAssignmentIds` rather than the caller's word for
 * it: an override for a row that is no longer on the page is dropped here,
 * which is what makes "one snapshot, overwritten" also mean "no growth".
 */
export function writeDateMemory(
  courseId: string,
  presetId: string,
  dates: DateOverrides,
  knownAssignmentIds: readonly string[],
): void {
  const known = new Set(knownAssignmentIds);
  const snapshot: DateOverrides = {};
  for (const [id, day] of Object.entries(dates)) {
    const valid = rememberedDay(day);
    if (known.has(id) && valid !== null) snapshot[id] = valid;
  }
  const store = readStore();
  // One assignment, not a merge: the slot is the current truth, full stop.
  store[slotOf(courseId, presetId)] = snapshot;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    // Private mode, a full quota, or storage disabled: the export still
    // produces the file, the teacher just re-enters the dates next time.
  }
}
