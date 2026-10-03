import { FileSpreadsheet, X } from "lucide-react";
import { useEffect } from "react";

import { useI18n } from "../../../shared/i18n/index.ts";
import type { ExportSource } from "../engine/types.ts";
import { useExportRows } from "../model/useExportRows.ts";
import { ExportPreviewTable } from "./ExportPreviewTable.tsx";

type Props = {
  open: boolean;
  courseName: string;
  /** The coursework the page has already loaded; nothing is re-fetched. */
  assignments: readonly ExportSource[];
  onClose: () => void;
};

/**
 * The export dialog (ADR-0041).
 *
 * It follows the `AssignmentModal` pattern exactly — `modal-backdrop` +
 * `role="dialog"` + `aria-modal`, closable with Escape and by clicking the
 * backdrop — so the interaction is the one the app already ships, and it does
 * so without importing it: a modal is markup and design tokens, which is what
 * `shared/ui/` is for, but its body here is entirely the export's own, and a
 * shared component with eleven props is worse than twenty lines of markup.
 *
 * It makes NO network request of any kind. Everything it shows comes from the
 * assignments prop, which the course page already has in memory.
 */
export function ExcelExportDialog({
  open,
  courseName,
  assignments,
  onClose,
}: Props) {
  const { t } = useI18n();
  const {
    presetId,
    setPresetId,
    presets,
    preset,
    rows,
    setDateOverride,
    missingDates,
    busy,
    error,
    canExport,
    run,
  } = useExportRows(assignments, courseName);

  // Escape closes — and only while the export is NOT in flight, so a
  // half-generated workbook is not abandoned by a stray keypress.
  useEffect(() => {
    if (!open || busy) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, busy, onClose]);

  if (!open) return null;

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal export-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="export-dialog-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <h2 id="export-dialog-title">{t("export.title")}</h2>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label={t("export.close")}
          >
            <X size={18} />
          </button>
        </div>

        <div className="export-body">
          <label className="export-field">
            <span className="export-label">{t("export.preset")}</span>
            <select
              className="select-input"
              value={presetId}
              onChange={(event) => setPresetId(event.target.value)}
            >
              {presets.map((item) => (
                <option key={item.id} value={item.id}>
                  {t(item.labelKey as Parameters<typeof t>[0])}
                </option>
              ))}
            </select>
          </label>

          <p className="export-hint">{t("export.dateHint")}</p>

          {error ? (
            <div className="alert alert-error" role="alert">
              {error}
            </div>
          ) : null}

          {rows.length === 0 ? (
            <p className="export-empty">{t("export.empty")}</p>
          ) : (
            <>
              <ExportPreviewTable
                preset={preset ?? presets[0]}
                rows={rows}
                onDateChange={setDateOverride}
              />
              {missingDates > 0 ? (
                <p className="export-warning">
                  {t("export.missingDates", { count: missingDates })}
                </p>
              ) : null}
            </>
          )}
        </div>

        <div className="modal-actions export-actions">
          <button
            type="button"
            className="button"
            onClick={onClose}
            disabled={busy}
          >
            {t("export.cancel")}
          </button>
          <button
            type="button"
            className="button button-primary"
            onClick={() => {
              void run().then((ok) => {
                if (ok) onClose();
              });
            }}
            disabled={!canExport}
          >
            <FileSpreadsheet size={15} />
            {busy ? t("export.working") : t("export.submit")}
          </button>
        </div>
      </div>
    </div>
  );
}