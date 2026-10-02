import { Database, LogOut, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { api } from "../api.ts";
import { useAuth, useSync } from "../context/DataContext.tsx";
import { useSettings } from "../context/SettingsContext.tsx";
import { toLocalDate } from "../dates.ts";
import { useI18n, LANGUAGE_OPTIONS } from "../i18n.ts";
import type { I18nKey } from "../i18n.ts";
import type { AppSettings, ThemeMode } from "../types.ts";
import { CollapsibleCard } from "../components/CollapsibleCard.tsx";
import { DonateCards } from "../components/DonateCards.tsx";

const THEME_OPTIONS: Array<{ mode: ThemeMode; labelKey: I18nKey }> = [
  { mode: "light", labelKey: "settings.light" },
  { mode: "dark", labelKey: "settings.dark" },
  { mode: "system", labelKey: "settings.system" },
];

export function Settings() {
  const { auth, login, logout } = useAuth();
  const { status, syncNow, syncRestart, syncing, syncStuck } = useSync();
  const settings = useSettings();
  const { t } = useI18n();
  const [confirmClear, setConfirmClear] = useState(false);
  const [confirmLogout, setConfirmLogout] = useState(false);

  // The result of clearing the cache is a momentary event, not a page state:
  // it used to live in `message` and render as a blue `alert-info` banner that
  // stayed until the next render — and a *failed* clear was blue too. Both now
  // go through a toast with the right tone (ADR-0030).
  const clearCache = async () => {
    try {
      await api.clearCache();
      settings.reset();
      toast.success(t("settings.cleared"));
      await syncNow();
    } catch {
      toast.error(t("settings.clearFailed"));
    }
    setConfirmClear(false);
  };

  return (
    <div className="page settings-page">
      <h1>{t("settings.title")}</h1>

      <section className="card settings-card">
        <h2>{t("settings.googleAccount")}</h2>
        <div className="settings-row">
          <div>
            <div className="settings-label">{t("settings.connection")}</div>
            <div className="settings-value">
              {auth?.authenticated
                ? auth.user?.name
                  ? t("settings.signedIn", { name: auth.user.name })
                  : t("settings.signedInNoName")
                : t("settings.notSignedIn")}
            </div>
            {auth?.error ? (
              <div className="settings-error">{auth.error}</div>
            ) : null}
            {auth?.login_in_progress && auth.auth_url ? (
              <div className="settings-hint">
                <a href={auth.auth_url} target="_blank" rel="noreferrer">
                  {t("settings.openConsent")}
                </a>
              </div>
            ) : null}
          </div>
          {auth?.authenticated ? (
            <button
              type="button"
              className="button"
              onClick={() => setConfirmLogout(true)}
            >
              <LogOut size={15} /> {t("settings.signOut")}
            </button>
          ) : (
            <button
              type="button"
              className="button button-primary"
              onClick={() => void login()}
            >
              {t("settings.signIn")}
            </button>
          )}
        </div>
        {confirmLogout ? (
          <div className="confirm-box">
            <span>{t("settings.signOutConfirm")}</span>
            <div>
              <button
                type="button"
                className="button"
                onClick={() => setConfirmLogout(false)}
              >
                {t("settings.cancel")}
              </button>
              <button
                type="button"
                className="button button-danger"
                onClick={async () => {
                  const signedOut = await logout();
                  // A failed sign-out changes nothing on screen, and the shared
                  // `error` is only rendered on the dashboard — without this the
                  // user cannot tell that they are still signed in (ADR-0030).
                  if (!signedOut) {
                    toast.error(t("settings.signOutFailed"));
                  }
                  setConfirmLogout(false);
                }}
              >
                {t("settings.signOut")}
              </button>
            </div>
          </div>
        ) : null}

        <div className="settings-row">
          <div>
            <div className="settings-label">{t("settings.lastSync")}</div>
            <div className="settings-value">
              {/* Backend timestamps are naive UTC; render them in the local
                  zone (migration stage 5/§18, finished in stage 7). */}
              {(() => {
                const parsed = toLocalDate(status?.last_sync ?? null);
                if (parsed) {
                  return parsed.toLocaleString();
                }
                return status?.last_sync ?? t("settings.never");
              })()}
            </div>
            {status?.sync_status === "needs_reauth" ? (
              <div className="settings-hint">{t("topbar.needsReauthHint")}</div>
            ) : null}
            {status?.last_sync_error ? (
              <div className="settings-error">{status.last_sync_error}</div>
            ) : null}
          </div>
          {/* ADR-0032: the same choice the topbar offers. While the sync is
              stuck the disabled "Sync now" button was the only control here,
              which made the settings page a dead end for exactly the case that
              needs an action. */}
          {syncStuck ? (
            <button
              type="button"
              className="button"
              title={t("topbar.syncRestartHint")}
              onClick={() => void syncRestart()}
            >
              <RefreshCw size={15} />
              {t("topbar.syncRestart")}
            </button>
          ) : (
            <button
              type="button"
              className="button"
              onClick={() => void syncNow()}
              disabled={syncing}
            >
              <RefreshCw size={15} className={syncing ? "spin" : ""} />
              {syncing ? t("topbar.syncing") : t("settings.syncNow")}
            </button>
          )}
        </div>
      </section>

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

      {/* Donations (ADR-0037). COLLAPSED by default: a support block is not a
          setting, and leaving it open would push the local-data controls — the
          reason most people open this page — below the fold. The same
          `DonateCards` block the public landing renders, so the wording and the
          banks cannot differ between the two surfaces. */}
      <CollapsibleCard title={t("donate.title")}>
        <DonateCards />
      </CollapsibleCard>

      <section className="card settings-card">
        <h2>{t("settings.localData")}</h2>
        <div className="settings-row">
          <div>
            <div className="settings-label">{t("settings.cachedData")}</div>
            <div className="settings-value">{t("settings.cachedHint")}</div>
          </div>
          <button
            type="button"
            className="button button-danger"
            onClick={() => setConfirmClear(true)}
          >
            <Trash2 size={15} /> {t("settings.clearData")}
          </button>
        </div>
        {confirmClear ? (
          <div className="confirm-box">
            <span>{t("settings.clearConfirm")}</span>
            <div>
              <button
                type="button"
                className="button"
                onClick={() => setConfirmClear(false)}
              >
                {t("settings.cancel")}
              </button>
              <button
                type="button"
                className="button button-danger"
                onClick={() => void clearCache()}
              >
                <Database size={15} /> {t("settings.confirmDelete")}
              </button>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
