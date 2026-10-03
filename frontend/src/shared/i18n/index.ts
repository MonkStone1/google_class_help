/**
 * Lightweight, fully typed i18n for the dashboard.
 *
 * Deliberately dependency-free: the app needs three languages and a single
 * UI surface, so flat string dictionaries + one hook beat react-i18next.
 * Strings are keyed by semantic ids (e.g. "nav.dashboard"); variables are
 * interpolated with {name} placeholders.
 *
 * The dictionaries live in ./i18n/<lang>.ts; English is the source of truth
 * for `I18nKey`, so a missing translation fails the build (ADR-0011).
 */

import { LOCALE } from "../lib/dates.ts";
import { useSettings } from "../settings/index.ts";
import { en } from "./locales/en.ts";
import { ru } from "./locales/ru.ts";
import { uk } from "./locales/uk.ts";
import type { I18nKey } from "./locales/en.ts";
import type { Language } from "../types/index.ts";

export type { I18nKey };

const DICTS = {
  en,
  uk,
  ru,
} satisfies Record<Language, Record<I18nKey, string>>;

export type I18nVars = Record<string, string | number>;

/**
 * The languages the settings can be switched between. Lives here, not in
 * Settings.tsx, because the public landing page (ADR-0029) offers the same
 * choice to a visitor who has no session and therefore never sees Settings.
 * Endonyms on purpose: someone looking for their language scans for their own
 * word, not for its translation.
 */
export const LANGUAGE_OPTIONS: Array<{ code: Language; label: string }> = [
  { code: "en", label: "English" },
  { code: "uk", label: "Українська" },
  { code: "ru", label: "Русский" },
];

export function useI18n() {
  const { language, setLanguage } = useSettings();
  const dict = DICTS[language] ?? en;

  const t = (key: I18nKey, vars?: I18nVars): string => {
    let value: string = dict[key] ?? en[key] ?? key;
    if (vars) {
      for (const [name, raw] of Object.entries(vars)) {
        value = value.replaceAll(`{${name}}`, String(raw));
      }
    }
    return value;
  };

  return { t, language, setLanguage, locale: LOCALE[language] };
}
