/**
 * The Excel-export strings, en.
 *
 * A separate domain dictionary (ADR-0041): the export dialog is a feature with
 * its own vocabulary — preset names, the date explanation, busy and error
 * states — and folding those into `courses.ts` would bury them under forty
 * unrelated teacher-screen keys.
 *
 * What is NOT here, deliberately: the four column headers of the primary
 * preset. Those are the format the external importer reads, not something the
 * teacher reads, so they live in `presets/ukranianDictionaryNz.ts` and stay
 * Ukrainian whatever the interface language is.
 */
export const en_export = {
  "export.button": "Export to Excel",
  "export.title": "Export course to Excel",
  "export.preset": "Export format",
  "export.preset.ukranian_dictionary_nz": "ukranian-dictionary-nz.ua",
  "export.dateHint":
    "The default date is taken from the assignment creation date in Google Classroom. You can change it before exporting if necessary.",
  "export.dateColumn": "Date",
  "export.cancel": "Cancel",
  "export.submit": "Export",
  "export.working": "Preparing the file…",
  "export.done": "The file has been downloaded.",
  "export.empty": "There are no assignments to export",
  "export.missingDates": "{count} assignments have no date",
  "export.close": "Close",
  "export.error.noAssignments": "There are no assignments to export.",
  "export.error.invalidPreset": "This export format is not available.",
  "export.error.invalidData": "Some assignments hold data that cannot be exported.",
  "export.error.invalidDate": "One of the dates is not a valid date.",
  "export.error.build": "The Excel file could not be generated.",
  "export.error.download": "The file could not be saved. Check the browser settings.",
} as const;