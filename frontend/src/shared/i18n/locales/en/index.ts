/**
 * The English dictionary — the source of truth.
 *
 * Split by domain (`PLAN` §3.4): five hundred lines in one file is a file
 * nobody can navigate, and "where is the string for the settings screen" is a
 * question a folder answers and a scroll does not. The keys and their order are
 * unchanged, so `t("nav.dashboard")` behaves exactly as it did.
 *
 * The nine domain objects are spread back into one flat dictionary, which is
 * what makes this the single place `I18nKey` is derived from: `uk` and `ru` are
 * checked against it, so a missing or extra translation fails `tsc` instead of
 * silently falling back at runtime (ADR-0011).
 */

import { en_admin } from "./admin.ts";
import { en_assignments } from "./assignments.ts";
import { en_base } from "./base.ts";
import { en_courses } from "./courses.ts";
import { en_export } from "./export.ts";
import { en_feedback } from "./feedback.ts";
import { en_grades } from "./grades.ts";
import { en_landing } from "./landing.ts";
import { en_settings } from "./settings.ts";
import { en_shell } from "./shell.ts";

export const en = {
  ...en_base,
  ...en_shell,
  ...en_assignments,
  ...en_courses,
  ...en_grades,
  ...en_feedback,
  ...en_settings,
  ...en_landing,
  ...en_admin,
  ...en_export,
} as const;

/** Every valid translation key, derived from the English dictionary. */
export type I18nKey = keyof typeof en;