Implement a new **fully client-side Excel export system for the teacher course page** in the existing GoogleClassHelp project.

The previously implemented project architecture and functionality must remain unchanged. This task only adds the Excel export feature.

The export must be performed **entirely in the frontend**.

Use **ExcelJS** for generating the `.xlsx` file in the browser.

Do not add a backend export endpoint, backend Excel generation, or any additional Google Classroom API request specifically for exporting.

### 1. Export architecture

The export flow must be:

**Existing Google Classroom coursework data already available in frontend → frontend normalization/transformation → export preview → teacher edits dates → ExcelJS generates `.xlsx` in browser → browser downloads the file.**

The original coursework objects must not be mutated.

The export implementation must use a reusable **preset-based architecture**.

The generic export engine should be separated from preset-specific rules so that additional export formats can be added later without rewriting the export engine.

The application UI language and export preset are independent concepts.

### 2. Primary preset

The primary export preset is specifically for:

`ukranian-dictionary-nz.ua`

Use the preset ID:

`ukranian_dictionary_nz`

Do not describe this as a generic "Ukrainian electronic diary".

The provided reference Excel file/image is the source of truth for the required import structure.

The primary structure is:

`Номер | Дата | Зміст | ДЗ`

The generated `.xlsx` must be suitable for subsequent import into `ukranian-dictionary-nz.ua`.

The architecture should also allow additional presets, including Russian and English presets/variants, to be added later.

Do not invent requirements for external services that have not been specified.

### 3. Frontend-only implementation

All of the following must happen in the browser:

* preset selection;
* coursework transformation;
* sorting;
* numbering;
* title processing;
* homework processing;
* date initialization;
* preview rendering;
* date editing;
* Excel workbook creation;
* Excel formatting;
* `.xlsx` generation;
* file download.

Do not send the export rows to the backend.

Do not create a backend export API.

Do not store the generated workbook on the server.

Do not make additional Google Classroom API calls.

### 4. ExcelJS

Use the existing frontend package management system and add:

`exceljs`

Use ExcelJS to create the workbook and worksheet.

The implementation should generate a real `.xlsx` file directly in the browser.

Use actual JavaScript `Date` values for Excel date cells where appropriate and apply:

`dd.mm.yyyy`

as the Excel display format.

Configure:

* worksheet name;
* column headers;
* column widths;
* text wrapping;
* vertical alignment;
* appropriate cell formatting;
* date formatting;
* workbook generation;
* browser download.

Do not generate CSV and rename it to `.xlsx`.

The result must be a real Excel workbook.

### 5. `mitt`

`mitt` must **not** be added merely because it was mentioned.

Use `mitt` only if the existing frontend architecture genuinely benefits from an event bus for communication between the export UI, preview, or related components.

If there is no real architectural need for it, do not add it.

The Excel export itself must depend on ExcelJS, not on `mitt`.

### 6. Export button

On the teacher course page add:

**«Експортувати у Excel»**

Clicking the button opens the export interface.

The export interface must contain:

* preset selector;
* preview table;
* editable dates;
* Cancel;
* Export.

The preview must be generated from the coursework data already loaded by the frontend.

### 7. Preview

For `ukranian_dictionary_nz`, display:

| Номер | Дата | Зміст | ДЗ |
| ----- | ---- | ----- | -- |

The `Дата` field must be editable.

The default date is the Google Classroom assignment creation date.

Display the default date as:

`DD.MM.YYYY`

Use these localized explanations:

Ukrainian:

“Дата за замовчуванням береться з дати створення завдання в Google Classroom. За потреби її можна змінити перед експортом.”

Russian:

“Дата по умолчанию берётся с даты создания задания в Google Classroom. При необходимости её можно изменить перед экспортом.”

English:

“The default date is taken from the assignment creation date in Google Classroom. You can change it before exporting if necessary.”

Use the existing i18n system if available.

### 8. Assignment ordering

Sort assignments from earliest to latest based on the original assignment creation timestamp.

Then assign:

`1, 2, 3, 4, ...`

Use a deterministic secondary key, such as assignment ID, when timestamps are identical.

Do not modify the original coursework array.

The edited export date must not modify the original assignment creation timestamp.

### 9. `Дата`

Default:

Google Classroom assignment creation date.

The teacher can override the date in the preview.

The export must use the final edited date.

In Excel, write it as an actual date value and format it as:

`dd.mm.yyyy`

Do not store the date merely as a formatted string if ExcelJS can represent it as a real date.

### 10. `Зміст`

For the `ukranian_dictionary_nz` preset, derive the value from the assignment title.

Apply these rules:

1. Remove `Урок`.
2. Remove dates matching `DD.MM.YYYY`.
3. Clean extra whitespace.
4. Clean unnecessary punctuation left by the removal.
5. Preserve all other meaningful words.
6. If the result becomes empty, use the original assignment title.

Example:

`Урок 15. 20.09.2026 Алгоритми`

becomes:

`15. Алгоритми`

The transformation rules must belong to the preset, not the generic export engine.

### 11. `ДЗ`

Use the assignment description/instructions.

If no description exists, leave the cell empty.

Replace every URL with:

`(google classroom)`

For example:

`Прочитати матеріал https://example.com/test`

becomes:

`Прочитати матеріал (google classroom)`

Replace all URLs, not just the first one.

Do not modify the original assignment description.

### 12. Preset system

Create a reusable preset definition system.

A preset should be capable of defining:

* ID;
* display name;
* localized display name;
* columns;
* column order;
* transformation rules;
* title-processing rules;
* URL-processing rules;
* date format;
* Excel formatting;
* worksheet name;
* filename pattern;
* ordering rules;
* numbering rules.

The generic exporter should consume the preset definition.

Do not hardcode:

`Номер | Дата | Зміст | ДЗ`

inside the generic Excel generator.

That structure belongs to the `ukranian_dictionary_nz` preset.

Future presets may have different columns.

### 13. Filename

Generate a filename based on the course name.

For example:

`<course_name>_електронний_щоденник.xlsx`

Sanitize invalid filesystem characters.

If the preset architecture allows it, make the filename configurable per preset.

### 14. Excel formatting

For the primary preset:

* headers must be clearly formatted;
* columns must have sensible widths;
* `Зміст` and `ДЗ` must support text wrapping;
* long homework descriptions must remain readable;
* dates must use `dd.mm.yyyy`;
* there must be no technical/helper columns;
* column order must exactly match the preset;
* the workbook must be valid `.xlsx`.

Do not over-engineer the styling. Import compatibility and correct data structure have priority over visual decoration.

### 15. Localization

Add Ukrainian, Russian and English UI translations for:

* export button;
* preset selector;
* preset names;
* preview headers;
* date explanation;
* Cancel;
* Export;
* loading state;
* errors;
* successful download state.

Keep UI language separate from export format.

For example:

English UI + `ukranian_dictionary_nz` preset must be completely valid.

### 16. Error handling

Handle:

* no assignments;
* invalid preset;
* invalid assignment data;
* invalid date;
* ExcelJS generation errors;
* browser download errors.

Show localized user-friendly errors.

Do not display raw exceptions to the user.

### 17. Tests

Add tests according to the project's existing testing conventions.

Test the generic export architecture:

* preset registration;
* valid preset;
* invalid preset;
* deterministic sorting;
* sequential numbering;
* date overrides;
* transformation without mutating source data;
* generation of a valid workbook;
* ability to add another preset without changing the generic exporter.

Test `ukranian_dictionary_nz`:

* removal of `Урок`;
* removal of `DD.MM.YYYY`;
* multiple dates;
* dates in different positions;
* title without `Урок`;
* title without date;
* empty transformed title fallback;
* URL replacement;
* multiple URLs;
* empty description;
* correct headers;
* correct column order;
* correct numbering;
* real Excel date values;
* `dd.mm.yyyy` formatting;
* long homework text;
* filename sanitization.

### 18. Dependencies

Add only the dependency actually required for Excel generation:

`exceljs`

Do not add `mitt` unless inspection of the existing frontend architecture shows a concrete need for an event emitter.

The final implementation should have **zero backend changes related to Excel export**.

The final flow must be:

**Google Classroom data already loaded → frontend preset transformation → editable preview → ExcelJS → `.xlsx` download.**

No additional Google Classroom request, no backend export endpoint, and no server-side Excel generation.
