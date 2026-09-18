import { ExternalLink, X } from "lucide-react";
import { useEffect, useState } from "react";

import { useI18n } from "../i18n.ts";
import { sharedTabPresence } from "../lib/tabPresence.ts";

/**
 * Tells the user that the dashboard is already open in another tab and
 * switches them back to it (see ADR-0018). Rendered only for a tab that lost
 * the Web Lock election, i.e. one opened while another dashboard tab was
 * alive. The switch runs through the service worker, because browsers only
 * move an unrelated tab while the click's transient activation is fresh — so
 * a failed automatic attempt right after opening is normal and the button
 * below is the reliable path.
 */
export function DuplicateTabNotice() {
  const { t } = useI18n();
  const [duplicate, setDuplicate] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [switchFailed, setSwitchFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const presence = sharedTabPresence();
    void presence.ready.then((state) => {
      if (!alive || !state.duplicate) return;
      setDuplicate(true);
      // Best effort: a browser that allows unattended focusing dismisses the
      // notice by itself; otherwise the user presses the switch button.
      timer = window.setTimeout(() => {
        void presence.requestFocus().then((switched) => {
          if (alive && switched) setDismissed(true);
        });
      }, 300);
    });
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, []);

  if (!duplicate || dismissed) return null;

  const switchTab = () => {
    void sharedTabPresence()
      .requestFocus()
      .then((switched) => {
        if (switched) {
          setDismissed(true);
        } else {
          setSwitchFailed(true);
        }
      });
  };

  return (
    <div className="alert alert-info tab-notice" role="status">
      <span className="tab-notice-text">
        {t("tabs.alreadyOpen")}
        {switchFailed ? ` ${t("tabs.switchBlocked")}` : ""}
      </span>
      <button
        type="button"
        className="button tab-notice-action"
        onClick={switchTab}
      >
        <ExternalLink size={14} /> {t("tabs.switch")}
      </button>
      <button
        type="button"
        className="icon-button"
        onClick={() => setDismissed(true)}
        aria-label={t("tabs.dismiss")}
        title={t("tabs.dismiss")}
      >
        <X size={14} />
      </button>
    </div>
  );
}
