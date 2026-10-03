import { AlertTriangle, CalendarClock, Sun, Trash2, X } from "lucide-react";

import { useSettings } from "../shared/settings/SettingsProvider.tsx";
import { formatDateTimeShort, parseDue } from "../shared/lib/dates.ts";
import { useI18n } from "../shared/i18n/index.ts";
import type { I18nKey } from "../shared/i18n/index.ts";
import type { NotificationItem } from "./TopBar.tsx";

const KIND_META: Record<
  NotificationItem["kind"],
  { labelKey: I18nKey; icon: typeof AlertTriangle; className: string }
> = {
  overdue: {
    labelKey: "notif.overdue",
    icon: AlertTriangle,
    className: "notif-overdue",
  },
  today: {
    labelKey: "notif.dueToday",
    icon: CalendarClock,
    className: "notif-today",
  },
  tomorrow: {
    labelKey: "notif.dueTomorrow",
    icon: Sun,
    className: "notif-tomorrow",
  },
};

type Props = {
  items: NotificationItem[];
  onDismiss: (item: NotificationItem) => void;
  onClearAll: () => void;
  onClose: () => void;
};

export function NotificationCenter({
  items,
  onDismiss,
  onClearAll,
  onClose,
}: Props) {
  const {
    notifications: { overdue, dueToday, dueTomorrow },
    cardDensity,
  } = useSettings();
  const { t } = useI18n();

  const visible = items.filter((item) => {
    if (item.kind === "overdue") {
      return overdue;
    }
    if (item.kind === "today") {
      return dueToday;
    }
    return dueTomorrow;
  });

  return (
    <>
      <div className="notif-backdrop" role="presentation" onClick={onClose} />
      <div
        className={`notification-center ${cardDensity === "compact" ? "compact" : ""}`}
      >
        <div className="notification-header">
          <h3>{t("notif.title")}</h3>
          <div className="notification-header-actions">
            <span className="notification-count">{visible.length}</span>
            {visible.length > 0 ? (
              <button
                type="button"
                className="notification-clear"
                onClick={onClearAll}
              >
                <Trash2 size={13} />
                {t("notif.clearAll")}
              </button>
            ) : null}
          </div>
        </div>
        {visible.length === 0 ? (
          <div className="notification-empty">{t("notif.empty")}</div>
        ) : (
          <ul>
            {visible.map(({ assignment, kind }) => {
              const meta = KIND_META[kind];
              return (
                <li key={`${kind}-${assignment.id}`} className={meta.className}>
                  <meta.icon size={15} />
                  <div>
                    <div className="notification-title">{assignment.title}</div>
                    <div className="notification-sub">
                      {assignment.course_name} · {t(meta.labelKey)}
                      {assignment.due_at
                        ? ` · ${formatDateTimeShort(parseDue(assignment.due_at))}`
                        : ""}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="notification-dismiss"
                    aria-label={t("notif.dismiss")}
                    title={t("notif.dismiss")}
                    onClick={() => onDismiss({ assignment, kind })}
                  >
                    <X size={14} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </>
  );
}
