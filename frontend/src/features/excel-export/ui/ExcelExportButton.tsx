import { FileSpreadsheet } from "lucide-react";
import { useState } from "react";

import { useI18n } from "../../../shared/i18n/index.ts";
import type { ExportSource } from "../engine/types.ts";
import { ExcelExportDialog } from "./ExcelExportDialog.tsx";

type Props = {
  courseName: string;
  /** The coursework the page already holds; the feature fetches nothing. */
  assignments: readonly ExportSource[];
};

/**
 * The export button and the dialog it opens (ADR-0041).
 *
 * They are ONE component on purpose: the `open` flag has exactly one owner and
 * exactly one lifetime — the time the dialog is on screen. A page that owned the
 * flag would have to reset it on every route change, and the button would have
 * to be rendered next to the dialog for that reset to be reachable.
 *
 * The button is disabled when there is nothing to export, so the "no
 * assignments" case is unreachable by click and still stated inside the dialog
 * for a teacher who opened it before the coursework finished loading.
 */
export function ExcelExportButton({ courseName, assignments }: Props) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        className="button"
        onClick={() => setOpen(true)}
        disabled={assignments.length === 0}
      >
        <FileSpreadsheet size={15} /> {t("export.button")}
      </button>
      <ExcelExportDialog
        open={open}
        courseName={courseName}
        assignments={assignments}
        onClose={() => setOpen(false)}
      />
    </>
  );
}