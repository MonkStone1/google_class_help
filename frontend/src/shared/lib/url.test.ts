import { describe, expect, it } from "vitest";

import {
  canonicalDue,
  canonicalStatuses,
  formatDueFilter,
  formatStatusFilter,
  parseDueFilter,
  parseStatusFilter,
} from "./url.ts";

/**
 * The link contract of the assignments filter (ADR-0013).
 *
 * These cases moved here with the code they cover when `lib/assignmentFilters.ts`
 * was split (ADR-0040): the questions below are all about WHAT A LINK MAY SAY,
 * and keeping them with the link parser is what stops the "null means off, empty
 * means nothing matches" convention from being re-decided by the filter.
 */
describe("status filter parsing", () => {
  it("canonicalizes to the panel facet order", () => {
    expect(canonicalStatuses(["graded", "todo"])).toEqual(["todo", "graded"]);
    expect(canonicalDue(["no_due", "has_due"])).toEqual(["has_due", "no_due"]);
  });

  it("treats null and legacy `all` as the off facet", () => {
    expect(parseStatusFilter(null)).toBeNull();
    expect(parseStatusFilter("all")).toBeNull();
    expect(parseDueFilter(null)).toBeNull();
    expect(parseDueFilter("all")).toBeNull();
  });

  it("keeps a present-but-empty value as an empty selection", () => {
    expect(parseStatusFilter("zzz")).toEqual([]);
    expect(formatStatusFilter([])).toBe("");
    expect(parseDueFilter("zzz")).toEqual([]);
    expect(formatDueFilter([])).toBe("");
  });

  it("drops unknown values and formats canonically", () => {
    expect(parseStatusFilter("graded,todo,zzz")).toEqual(["todo", "graded"]);
    expect(formatStatusFilter(["graded", "todo"])).toBe("todo,graded");
    expect(parseDueFilter("no_due,zzz")).toEqual(["no_due"]);
    expect(formatDueFilter(["no_due"])).toBe("no_due");
  });

  it("a due URL survives a round-trip", () => {
    const value = parseDueFilter("has_due");
    expect(value).toEqual(["has_due"]);
    expect(formatDueFilter(value)).toBe("has_due");
  });
});