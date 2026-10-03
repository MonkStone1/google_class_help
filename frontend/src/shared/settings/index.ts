/**
 * The public API of the settings store.
 *
 * `shared/` rather than `app/providers/` for a reason the layering forced into
 * the open: `shared/i18n` reads the current language through `useSettings`, so
 * a provider living in the assembly layer would make the lowest layer depend on
 * the highest (guardrail #3). Settings are also exactly what "shared" means
 * here — a mechanism (localStorage, ADR-0006) plus the theme the document needs
 * before any page exists (ADR-0034), with no domain knowledge of its own; the
 * filter facets it normalises are declared in `shared/types/ui.ts`.
 */

export { SettingsProvider, useSettings } from "./SettingsProvider.tsx";
export type { ResolvedTheme } from "./SettingsProvider.tsx";