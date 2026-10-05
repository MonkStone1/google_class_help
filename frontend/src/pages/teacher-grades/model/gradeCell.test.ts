import { describe, expect, it } from "vitest";

import { gradeCellText } from "./gradeCell.ts";
import type { SubmissionCell } from "../../../shared/types/index.ts";

function makeCell(overrides: Partial<SubmissionCell> = {}): SubmissionCell {
  return {
    coursework_id: "w1",
    status: "graded",
    submitted: true,
    returned: true,
    graded: true,
    late: false,
    points: 12,
    max_points: 12,
    percent: 100,
    submitted_at: null,
    updated_at: null,
    ...overrides,
  };
}

describe("gradeCellText", () => {
  it("shows the raw mark alone, without the task's maximum", () => {
    // ADR-0043: the requested format is the mark itself — "12", not "12 / 12".
    expect(gradeCellText(makeCell(), "points")).toBe("12");
  });

  it("keeps the mark of a task worth 100 as a mark, not a percentage", () => {
    const cell = makeCell({ points: 85, max_points: 100, percent: 85 });
    expect(gradeCellText(cell, "points")).toBe("85");
  });

  it("shows the percentage alone", () => {
    const cell = makeCell({ points: 9, max_points: 12, percent: 75 });
    expect(gradeCellText(cell, "percent")).toBe("75%");
  });

  it("shows the mark out of the task when the teacher picks the ratio", () => {
    // The journal's own notation: the maximum travels with the mark, the
    // percentage does not (ADR-0043).
    const cell = makeCell({ points: 9, max_points: 12, percent: 75 });
    expect(gradeCellText(cell, "ratio")).toBe("9 / 12");
  });

  it("keeps a 100-point task a ratio, not a percentage", () => {
    const cell = makeCell({ points: 85, max_points: 100, percent: 85 });
    expect(gradeCellText(cell, "ratio")).toBe("85 / 100");
  });

  it("shows a question mark for the ratio of a task with no maximum", () => {
    // Same degradation as before: the mark stays, the unknown maximum is not
    // invented and the percentage is not silently turned into zero.
    const cell = makeCell({ max_points: null, percent: null });
    expect(gradeCellText(cell, "ratio")).toBe("12 / ?");
  });

  it("shows both, the format the matrix had before the setting", () => {
    expect(gradeCellText(makeCell(), "both")).toBe("12 / 12 · 100%");
  });

  it("drops the maximum but keeps the percentage when the task has none", () => {
    // Classroom sends `max_points: null` for a task with no maximum; the percent
    // is then computed as null too, so the pair degrades to the mark itself.
    const cell = makeCell({ max_points: null, percent: null });
    expect(gradeCellText(cell, "both")).toBe("12 / ?");
  });

  it("falls back to the mark when there is no percentage to show", () => {
    // A grade the teacher gave must never disappear because the percentage could
    // not be computed (ADR-0008).
    const cell = makeCell({ max_points: null, percent: null });
    expect(gradeCellText(cell, "percent")).toBe("12");
  });
});