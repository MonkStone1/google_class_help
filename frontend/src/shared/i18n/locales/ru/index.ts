/**
 * The Russian dictionary, glued from the same nine domains as `en`.
 *
 * `satisfies Record<I18nKey, string>` is the point of this file: a key that
 * exists in English but not here, or a key that no longer exists at all, is a
 * compile error rather than a string that silently renders as its own key
 * (ADR-0011). The check lives HERE rather than in `i18n/index.ts` so it keeps
 * working after the split.
 */

import type { I18nKey } from "../en/index.ts";

import { ru_admin } from "./admin.ts";
import { ru_assignments } from "./assignments.ts";
import { ru_base } from "./base.ts";
import { ru_courses } from "./courses.ts";
import { ru_export } from "./export.ts";
import { ru_feedback } from "./feedback.ts";
import { ru_grades } from "./grades.ts";
import { ru_landing } from "./landing.ts";
import { ru_settings } from "./settings.ts";
import { ru_shell } from "./shell.ts";

export const ru = {
  ...ru_base,
  ...ru_shell,
  ...ru_assignments,
  ...ru_courses,
  ...ru_grades,
  ...ru_feedback,
  ...ru_settings,
  ...ru_landing,
  ...ru_admin,
  ...ru_export,
} satisfies Record<I18nKey, string>;