import { Database, LogOut, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { api } from "../../../shared/api/index.ts";
import { useAuth } from "../../../entities/user/index.ts";
import { useSync } from "../../../features/sync/index.ts";
import { useSettings } from "../../../shared/settings/index.ts";
import { toLocalDate } from "../../../shared/lib/index.ts";
import { useI18n } from "../../../shared/i18n/index.ts";
import { CollapsibleCard } from "../../../shared/ui/index.ts";
import { DonateCards } from "../../../features/donate/index.ts";
import { PreferenceSections } from "./PreferenceSections.tsx";

/**
 * The settings screen: the account, the preferences and the local data.
 *
 * The three preference sections are `PreferenceSections` — they are pure
 * `localStorage` writes and do not touch the session, which is what this file
 * is about. What remains here is the half that does: sign in, sync, and throw
 * away everything cached on this machine.
 */

export function Settings() {
  const { auth, login, logout } = useAuth();
  const { status, syncNow, syncRestart, syncing, syncStuck } = useSync();
  const settings = useSettings();
  const { t } = useI18n();
  const [confirmClear, setConfirmClear] = useState(false);
  const [confirmLogout, setConfirmLogout] = useState(false);

  // The result of clearing the cache is a momentary event, not a page state:
  // it used to live in `message` and render as a blue `alert-info` banner that
  // stayed until the next render вЂ” and a *failed* clear was blue too. Both now
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
                  // `error` is only rendered on the dashboard вЂ” without this the
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
                  zone (migration stage 5/В§18, finished in stage 7). */}
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

      <PreferenceSections />


      {/* Donations (ADR-0037). COLLAPSED by default: a support block is not a
          setting, and leaving it open would push the local-data controls вЂ” the
          reason most people open this page вЂ” below the fold. The same
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
