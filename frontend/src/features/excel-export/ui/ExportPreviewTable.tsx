import { useI18n } from "../../../shared/i18n/index.ts";
import { formatDayInput } from "../engine/rows.ts";
import type { ExportPreset, ExportRow } from "../engine/types.ts";

type Props = {
  preset: ExportPreset;
  rows: readonly ExportRow[];
  /** Called with the raw `YYYY-MM-DD` the teacher typed; "" clears it. */
  onDateChange: (assignmentId: string, day: string) => void;
};

/**
 * The export preview (ADR-0041).
 *
 * It shows the preset's OWN headers — the same strings that go into the file —
 * for EVERY column, the date included. That is what makes the preview a promise:
 * what the teacher reads here is what the importer will read there. An English
 * interface therefore still previews `Дата`, `Зміст` and `Домашнє завдання`,
 * because those are the file's words and not the interface's.
 *
 * `export.dateColumn` is still used, but only as the date input's accessible
 * name: there the label is read aloud by a screen reader in the interface
 * language, which is a place where localization helps rather than lies.
 *
 * The date cell is the only editable one, and it is a real
 * `<input type="date">`: it gives the native calendar and keyboard entry on
 * every platform, and it hands back a value whose format the engine already
 * knows how to parse.
 */
export function ExportPreviewTable({ preset, rows, onDateChange }: Props) {
  const { t } = useI18n();

  return (
    <div className="table-wrap export-preview">
      <table className="data-table">
        <thead>
          <tr>
            {/* Every header is the preset's own, including the date one. The
                preview is a promise about the FILE, so a column that showed a
                localized label here and a different word in the workbook would
                make that promise false — English UI must still preview "Дата". */}
            {preset.columns.map((column) => (
              <th key={column.key}>{column.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.assignmentId}>
              {preset.columns.map((column) => {
                const value = row.values[column.key];
                if (column.kind === "date") {
                  return (
                    <td key={column.key}>
                      <input
                        type="date"
                        className="export-date"
                        aria-label={t("export.dateColumn")}
                        // An empty cell for an assignment with no creation date:
                        // it is fillable rather than wrong.
                        value={value instanceof Date ? formatDayInput(value) : ""}
                        onChange={(event) =>
                          onDateChange(row.assignmentId, event.target.value)
                        }
                      />
                    </td>
                  );
                }
                return <td key={column.key}>{value === null ? "" : String(value)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}