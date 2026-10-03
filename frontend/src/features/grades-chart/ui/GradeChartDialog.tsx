/**
 * The grade-trend modal (ADR-0042).
 *
 * It follows the `AssignmentModal`/`ExcelExportDialog` pattern exactly —
 * `modal-backdrop` + `role="dialog"` + `aria-modal`, closable with Escape and
 * by clicking the backdrop — so the interaction is the one the app already
 * ships. It does not import those components: a modal is markup plus design
 * tokens, and a shared component with eleven props is worse than thirty lines
 * of markup whose behaviour a test can read.
 *
 * It makes NO network request of any kind. Everything it shows comes from the
 * source prop, which the grades page already holds in memory.
 */

import { X } from "lucide-react";
import { useEffect } from "react";

import { useI18n } from "../../../shared/i18n/index.ts";
import type { ChartSeries, ChartSource } from "../chart/types.ts";
import { GradeChartSvg } from "./GradeChartSvg.tsx";

type Props = {
  open: boolean;
  source: ChartSource;
  /** Non-null once `buildSeries` had enough to draw; null means "no chart". */
  series: ChartSeries | null;
  onClose: () => void;
};

export function GradeChartDialog({ open, source, series, onClose }: Props) {
  const { t } = useI18n();

  // Escape closes. The listener is added only while the modal is on screen, and
  // removed on cleanup — a listener left behind would close a dialog that is no
  // longer there.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal grade-chart-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="grade-chart-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <div className="subject-chip">{source.courseName}</div>
            <h2 id="grade-chart-title">{t("grades.chart.title")}</h2>
          </div>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label={t("grades.chart.close")}
          >
            <X size={18} />
          </button>
        </div>

        {series === null ? (
          <p className="grade-chart-empty">{t("grades.chart.empty")}</p>
        ) : (
          <GradeChartSvg series={series} courseName={source.courseName} />
        )}
      </div>
    </div>
  );
}