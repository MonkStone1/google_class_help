/**
 * The chart button and the dialog it opens (ADR-0042).
 *
 * They are ONE component on purpose: the `open` flag has exactly one owner and
 * exactly one lifetime — the time the dialog is on screen. A page that owned
 * the flag would have to reset it on every route change, and the button would
 * have to be rendered next to the dialog for that reset to be reachable. This is
 * the same shape `ExcelExportButton` established in ADR-0041.
 *
 * The button is DISABLED when the course has fewer than two graded works, so
 * the "not enough data" state is unreachable by click rather than being a
 * button that opens onto a sentence explaining that it cannot open.
 */

import { ChartNoAxesCombined } from "lucide-react";
import { useMemo, useState } from "react";

import { useI18n } from "../../../shared/i18n/index.ts";
import { useSettings } from "../../../shared/settings/index.ts";
import { buildSeries } from "../chart/series.ts";
import type { ChartSource } from "../chart/types.ts";
import { GradeChartDialog } from "./GradeChartDialog.tsx";

type Props = ChartSource;

export function GradeChartButton({
  courseId,
  courseName,
  average,
  items,
}: Props) {
  const { t } = useI18n();
  // The scale the reader grades on. Classroom says nothing about it — it stores
  // raw points per assignment and lets the maximum be anything — so the user
  // declares it once in Settings and every course's chart follows (ADR-0042).
  const { gradeScale } = useSettings();
  const [open, setOpen] = useState(false);

  const source = useMemo(
    () => ({ courseId, courseName, average, items }),
    [courseId, courseName, average, items],
  );
  // NOT memoized on purpose: `useI18n` returns a fresh `t` on every render, so a
  // dependency array could not honestly include it, and `buildSeries` is a sort
  // and a map over one course's graded work — cheaper than the render it
  // happens inside.
  const series = buildSeries(source, t, gradeScale);

  return (
    <>
      <button
        type="button"
        className="icon-button grade-chart-button"
        onClick={() => setOpen(true)}
        disabled={series === null}
        aria-label={t("grades.chart.open")}
        title={t("grades.chart.open")}
      >
        <ChartNoAxesCombined size={16} />
      </button>
      <GradeChartDialog
        open={open}
        source={source}
        series={series}
        onClose={() => setOpen(false)}
      />
    </>
  );
}