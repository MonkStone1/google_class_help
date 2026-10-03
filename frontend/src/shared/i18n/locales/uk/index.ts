/**
 * The Ukrainian dictionary, glued from the same nine domains as `en`.
 *
 * `satisfies Record<I18nKey, string>` is the point of this file: a key that
 * exists in English but not here, or a key that no longer exists at all, is a
 * compile error rather than a string that silently renders as its own key
 * (ADR-0011). The check lives HERE rather than in `i18n/index.ts` so it keeps
 * working after the split.
 */

import type { I18nKey } from "../en/index.ts";

import { uk_admin } from "./admin.ts";
import { uk_assignments } from "./assignments.ts";
import { uk_base } from "./base.ts";
import { uk_courses } from "./courses.ts";
import { uk_feedback } from "./feedback.ts";
import { uk_grades } from "./grades.ts";
import { uk_landing } from "./landing.ts";
import { uk_settings } from "./settings.ts";
import { uk_shell } from "./shell.ts";

export const uk = {
  ...uk_base,
  ...uk_shell,
  ...uk_assignments,
  ...uk_courses,
  ...uk_grades,
  ...uk_feedback,
  ...uk_settings,
  ...uk_landing,
  ...uk_admin,
} satisfies Record<I18nKey, string>;