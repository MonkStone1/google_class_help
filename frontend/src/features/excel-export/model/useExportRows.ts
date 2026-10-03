import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

import { useI18n } from "../../../shared/i18n/index.ts";
import { buildFilename } from "../engine/filename.ts";
import { saveBuffer } from "../engine/download.ts";
import {
  getPreset,
  isPresetId,
  listPresets,
  registerPreset,
} from "../engine/registry.ts";
import { buildRows } from "../engine/rows.ts";
import { buildWorkbookBuffer } from "../engine/workbook.ts";
import type {
  DateOverrides,
  ExportPreset,
  ExportRow,
  ExportSource,
} from "../engine/types.ts";
import { ukranianDictionaryNzPreset } from "../presets/ukranianDictionaryNz.ts";

/**
 * Preset registration happens HERE, in the feature, and not in the engine.
 *
 * The engine must not know which presets exist (ADR-0041); a feature that
 * imports `presets/*` and hands them to the registry keeps that direction
 * honest, and adding a second preset is one import plus one line below.
 */
registerPreset(ukranianDictionaryNzPreset);

/** The preset the dialog opens with. */
export const DEFAULT_PRESET_ID = ukranianDictionaryNzPreset.id;

/** Everything the dialog needs to render its current state. */
export type ExportRowsState = {
  presetId: string;
  setPresetId: (id: string) => void;
  presets: ExportPreset[];
  /** `null` when the chosen id is not registered — the dialog says so. */
  preset: ExportPreset | null;
  rows: ExportRow[];
  overrides: DateOverrides;
  setDateOverride: (assignmentId: string, day: string) => void;
  /** Rows whose date cell is empty, so the dialog can warn about them. */
  missingDates: number;
  busy: boolean;
  error: string | null;
  canExport: boolean;
  /** Builds the file and hands it to the browser. Resolves true on success. */
  run: () => Promise<boolean>;
};

export function useExportRows(
  assignments: readonly ExportSource[],
  courseName: string,
): ExportRowsState {
  const { t } = useI18n();
  const [presetId, setPresetId] = useState(DEFAULT_PRESET_ID);
  const [overrides, setOverrides] = useState<DateOverrides>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const presets = useMemo(() => listPresets(), []);
  // `null` rather than a throw: the SELECTOR is what failed, not the export,
  // and the dialog has to be able to render that message and keep its state.
  const preset = isPresetId(presetId) ? getPreset(presetId) : null;

  const rows = useMemo(
    () => (preset ? buildRows(preset, assignments, overrides) : []),
    [preset, assignments, overrides],
  );

  const missingDates = useMemo(
    () =>
      preset === null
        ? 0
        : rows.filter((row) => {
            const key = preset.columns.find((column) => column.kind === "date")
              ?.key;
            return key === undefined || row.values[key] === null;
          }).length,
    [preset, rows],
  );

  const setDateOverride = useCallback((assignmentId: string, day: string) => {
    setOverrides((previous) => ({ ...previous, [assignmentId]: day }));
    // An edit clears the previous failure: leaving "invalid date" on screen
    // after the teacher fixed the date would be a lie about the current state.
    setError(null);
  }, []);

  const run = useCallback(async () => {
    if (assignments.length === 0) {
      setError(t("export.error.noAssignments"));
      return false;
    }
    if (!preset) {
      setError(t("export.error.invalidPreset"));
      return false;
    }
    setBusy(true);
    setError(null);
    try {
      const buffer = await buildWorkbookBuffer(preset, rows);
      saveBuffer(buffer, buildFilename(courseName, preset));
      toast.success(t("export.done"));
      return true;
    } catch {
      // Deliberately not `catch (err)`: a raw ExcelJS message is not something
      // a teacher can act on, and the prompt says so outright. The message is
      // logged nowhere because the browser console already has the stack.
      setError(t("export.error.build"));
      return false;
    } finally {
      setBusy(false);
    }
  }, [assignments.length, courseName, preset, rows, t]);

  return {
    presetId,
    setPresetId,
    presets,
    preset,
    rows,
    overrides,
    setDateOverride,
    missingDates,
    busy,
    error,
    canExport: preset !== null && rows.length > 0 && !busy,
    run,
  };
}