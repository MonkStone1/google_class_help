/**
 * Turning a course's grades into everything one chart render needs (ADR-0042).
 *
 * This is the only place in the feature that decides what a "point" is, which
 * is why `buildSeries` is exported from the barrel: a test on the page can ask
 * it what the chart will show without mounting a single DOM node.
 *
 * The function is pure and, in particular, does not mutate its input — the
 * items belong to the cached courses state that other pages read too.
 */

import { formatDateTimeShort, parseDue } from "../../../shared/lib/index.ts";
import type { I18nKey, I18nVars } from "../../../shared/i18n/index.ts";
import type { GradeItem } from "../../../shared/types/index.ts";
import { MIN_CHART_POINTS } from "./layout.ts";
import { bandCenter, gradeTicks, percentToGrade } from "./scales.ts";
import type { ChartPoint, ChartSeries, ChartSource } from "./types.ts";

/**
 * The dictionary lookup `buildSeries` needs, injected rather than imported from
 * a hook: the function stays pure, so its rules are testable without a settings
 * provider, and the component still gets every string from `t()` (ADR-0011).
 */
export type Translate = (key: I18nKey, vars?: I18nVars) => string;

/** Milliseconds, or `null` for an assignment without a usable deadline. */
function dueTime(item: GradeItem): number | null {
  return parseDue(item.due_at)?.getTime() ?? null;
}

/**
 * Deadlines first, assignments without one last, and the original order kept
 * within each group: a stable sort matters because two assignments share a
 * deadline all the time (a quiz and its review on the same day), and the order
 * they arrive in is the order the teacher's course page lists them.
 */
function byDeadline(items: readonly GradeItem[]): GradeItem[] {
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => {
      const left = dueTime(a.item);
      const right = dueTime(b.item);
      if (left === null && right === null) return a.index - b.index;
      if (left === null) return 1;
      if (right === null) return -1;
      return left - right || a.index - b.index;
    })
    .map((entry) => entry.item);
}

/**
 * Everything one render needs, or `null` when the course has too little to
 * plot.
 *
 * `null` rather than an empty chart on purpose: a single graded work has no
 * trend, and drawing one bar next to an empty axis would be a claim the data
 * does not support. The caller turns `null` into a disabled button.
 */
export function buildSeries(
  source: ChartSource,
  translate: Translate,
): ChartSeries | null {
  const items = byDeadline(source.items);
  if (items.length < MIN_CHART_POINTS) {
    return null;
  }

  const count = items.length;
  const points: ChartPoint[] = items.map((item, index) => {
    const due = parseDue(item.due_at);
    return {
      key: item.assignment_id,
      title: item.title,
      label: due
        ? formatDateTimeShort(due)
        : translate("grades.chart.noAxisTask", { n: index + 1 }),
      due,
      // The percentage becomes a mark HERE and nowhere else: above this point
      // the chart works in marks, which is the scale the reader thinks in.
      // The task's own maximum caps the answer — 11/11 out of 11 is an 11,
      // because a 12 was never on offer.
      grade: percentToGrade(item.percent, item.max_points),
      // `null` stays `null`: showing 0 would be showing a mark no teacher gives.
      points: item.points ?? null,
      maxPoints: item.max_points ?? null,
      percent: item.percent ?? null,
    };
  });

  return {
    points,
    ticks: gradeTicks(),
    xLabels: points.map((point, index) => ({
      text: point.label,
      x: bandCenter(index, count),
    })),
  };
}