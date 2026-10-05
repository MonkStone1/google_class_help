import { useSettings } from "../../../shared/settings/index.ts";
import { LANGUAGE_OPTIONS, useI18n } from "../../../shared/i18n/index.ts";
import type { I18nKey } from "../../../shared/i18n/index.ts";
import type {
  AppSettings,
  TeacherGradeDisplay,
  ThemeMode,
} from "../../../shared/types/index.ts";

/**
 * The three sections that are pure preferences: how it looks, what the
 * dashboard shows, and which reminders appear.
 *
 * Separate from `Settings.tsx` because they share exactly one thing вЂ” the
 * settings store вЂ” and none of them touches the network or the session. The
 * page that remains is the one that does: sign in, sync, clear the cache. Both
 * halves were 300-plus lines of a single file, and neither could be read
 * without scrolling past the other.
 */

const THEME_OPTIONS: Array<{ mode: ThemeMode; labelKey: I18nKey }> = [
  { mode: "light", labelKey: "settings.light" },
  { mode: "dark", labelKey: "settings.dark" },
  { mode: "system", labelKey: "settings.system" },
];

/**
 * The cell formats of the teacher matrix (ADR-0043), in the order they are
 * offered: the mark alone, the mark out of its maximum, the percentage alone,
 * and the format the matrix had before the setting existed.
 */
const MATRIX_DISPLAY_OPTIONS: Array<{
  mode: TeacherGradeDisplay;
  labelKey: I18nKey;
}> = [
  { mode: "points", labelKey: "settings.teacherMatrixPoints" },
  { mode: "ratio", labelKey: "settings.teacherMatrixRatio" },
  { mode: "percent", labelKey: "settings.teacherMatrixPercent" },
  { mode: "both", labelKey: "settings.teacherMatrixBoth" },
];

export function PreferenceSections() {
  const settings = useSettings();
  const { t } = useI18n();

  return (
    <>
      <section className="card settings-card">
        <h2>{t("settings.appearance")}</h2>
        <div className="settings-row">
          <div className="settings-label">{t("settings.theme")}</div>
          <div className="tabs">
            {THEME_OPTIONS.map((option) => (
              <button
                key={option.mode}
                type="button"
                className={
                  settings.theme === option.mode ? "tab active" : "tab"
                }
                onClick={() => settings.setTheme(option.mode)}
              >
                {t(option.labelKey)}
              </button>
            ))}
          </div>
        </div>
        <div className="settings-row">
          <div className="settings-label">{t("settings.language")}</div>
          <div className="tabs">
            {LANGUAGE_OPTIONS.map((option) => (
              <button
                key={option.code}
                type="button"
                className={
                  settings.language === option.code ? "tab active" : "tab"
                }
                onClick={() => settings.setLanguage(option.code)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        <div className="settings-row">
          <div className="settings-label">{t("settings.cards")}</div>
          <div className="tabs">
            {(["comfortable", "compact"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                className={settings.cardDensity === mode ? "tab active" : "tab"}
                onClick={() => settings.update({ cardDensity: mode })}
              >
                {mode === "comfortable"
                  ? t("settings.comfortable")
                  : t("settings.compact")}
              </button>
            ))}
          </div>
        </div>
      </section>
      <section className="card settings-card">
        <h2>{t("settings.dashboard")}</h2>
        <div className="settings-row">
          <div className="settings-label">{t("settings.upcomingPeriod")}</div>
          <div className="tabs">
            {([3, 7, 14] as const).map((days) => (
              <button
                key={days}
                type="button"
                className={
                  settings.upcomingDays === days ? "tab active" : "tab"
                }
                onClick={() => settings.update({ upcomingDays: days })}
              >
                {t("settings.days", { count: days })}
              </button>
            ))}
          </div>
        </div>
        <div className="settings-row">
          <div className="settings-label">{t("settings.defaultSort")}</div>
          <label className="sort-select">
            <select
              value={settings.defaultSort}
              onChange={(event) =>
                settings.update({
                  defaultSort: event.target.value as AppSettings["defaultSort"],
                })
              }
            >
              <option value="due">{t("sort.due")}</option>
              <option value="priority">{t("sort.priority")}</option>
              <option value="grade">{t("sort.grade")}</option>
              <option value="newest">{t("sort.newest")}</option>
            </select>
          </label>
        </div>
        <div className="settings-row settings-row-top">
          <div className="settings-label">{t("settings.visibleSections")}</div>
          <div className="settings-toggles">
            {(
              [
                ["overdue", "stat.overdue"],
                ["today", "dash.today"],
                ["tomorrow", "dash.tomorrow"],
                ["upcoming", "settings.upcoming"],
                ["completed", "dash.completed"],
                ["stats", "settings.stats"],
              ] as Array<[keyof AppSettings["sections"], I18nKey]>
            ).map(([key, labelKey]) => (
              <label key={key} className="toggle">
                <input
                  type="checkbox"
                  checked={settings.sections[key]}
                  onChange={(event) =>
                    settings.updateSection(key, event.target.checked)
                  }
                />
                {t(labelKey)}
              </label>
            ))}
          </div>
        </div>
      </section>
<section className="card settings-card">
        <h2>{t("settings.grading")}</h2>
        <div className="settings-row">
          <div>
            <div className="settings-label">{t("settings.gradeScale")}</div>
            <div className="settings-hint">{t("settings.gradeScaleHint")}</div>
          </div>
          <div className="tabs">
            {/* Only two scales exist, and the chart's axis is meaningless
                without one of them, so this is a tab pair rather than a select
                with two options (ADR-0042). */}
            {([12, 100] as const).map((value) => (
              <button
                key={value}
                type="button"
                className={
                  settings.gradeScale === value ? "tab active" : "tab"
                }
                onClick={() => settings.update({ gradeScale: value })}
              >
                {value === 12
                  ? t("settings.gradeScale12")
                  : t("settings.gradeScale100")}
              </button>
            ))}
          </div>
        </div>
        {/* ADR-0043: the same reasoning, one step down — Classroom sends both
            numbers in every cell and cannot say which one this school reads, so
            the teacher picks once for the whole matrix. */}
        <div className="settings-row">
          <div>
            <div className="settings-label">{t("settings.teacherMatrix")}</div>
            <div className="settings-hint">
              {t("settings.teacherMatrixHint")}
            </div>
          </div>
          <div className="tabs">
            {MATRIX_DISPLAY_OPTIONS.map((option) => (
              <button
                key={option.mode}
                type="button"
                className={
                  settings.teacherGradeDisplay === option.mode
                    ? "tab active"
                    : "tab"
                }
                onClick={() =>
                  settings.update({ teacherGradeDisplay: option.mode })
                }
              >
                {t(option.labelKey)}
              </button>
            ))}
          </div>
        </div>
      </section>
      <section className="card settings-card">
        <h2>{t("settings.reminders")}</h2>
        <div className="settings-toggles">
          {(
            [
              ["overdue", "settings.remindOverdue"],
              ["dueToday", "settings.remindToday"],
              ["dueTomorrow", "settings.remindTomorrow"],
            ] as Array<[keyof AppSettings["notifications"], I18nKey]>
          ).map(([key, labelKey]) => (
            <label key={key} className="toggle">
              <input
                type="checkbox"
                checked={settings.notifications[key]}
                onChange={(event) =>
                  settings.updateNotification(key, event.target.checked)
                }
              />
              {t(labelKey)}
            </label>
          ))}
        </div>
      </section>
</>
  );
}


