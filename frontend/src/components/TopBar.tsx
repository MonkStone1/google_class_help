import { Bell, KeyRound, Moon, RefreshCw, Sun } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth, useSync, useCourses } from "../context/DataContext.tsx";
import { useSettings } from "../context/SettingsContext.tsx";
import { parseDue, toLocalDate } from "../dates.ts";
import { useI18n } from "../i18n.ts";
import { cn } from "../lib/cn.ts";
import { searchAll } from "../lib/search.ts";
import type { SearchHit } from "../lib/search.ts";
import type { Assignment } from "../types.ts";
import { NotificationCenter } from "./NotificationCenter.tsx";
import { SearchResults } from "./SearchResults.tsx";

function SyncTime({ lastSync }: { lastSync: string | null }) {
  const { t } = useI18n();
  if (!lastSync) {
    return <span className="sync-time">{t("topbar.neverSynced")}</span>;
  }
  // The backend serializes sync timestamps as naive UTC; render them in the
  // browser's local zone (migration stage 5/§18, finished in stage 7).
  const parsed = toLocalDate(lastSync);
  return (
    <span className="sync-time">
      {t("topbar.lastSync", {
        time: parsed ? parsed.toLocaleString() : lastSync,
      })}
    </span>
  );
}

export function TopBar({
  search,
  onSearch,
}: {
  search: string;
  onSearch: (value: string) => void;
}) {
  const { status, syncing, syncStuck, syncNow, syncRestart, error } = useSync();
  const { login } = useAuth();
  const { assignments, courses } = useCourses();
  const {
    dismissedNotifications,
    dismissNotification,
    dismissAllNotifications,
    setTheme,
  } = useSettings();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [bellOpen, setBellOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  const results = useMemo(
    () => searchAll(assignments, courses, search),
    [assignments, courses, search],
  );
  const hasQuery = search.trim().length > 0;
  const resultsVisible = searchOpen && hasQuery;

  useEffect(() => {
    setActiveIndex(0);
  }, [search]);

  const notifications = useMemo(
    () =>
      buildNotifications(assignments).filter(
        (item) => !dismissedNotifications.includes(notificationKey(item)),
      ),
    [assignments, dismissedNotifications],
  );
  const notificationCount = notifications.length;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        document.getElementById("global-search")?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const isDark = document.documentElement.dataset.theme === "dark";

  const openSearch = () => {
    setBellOpen(false);
    setSearchOpen(true);
  };

  const handleSearchChange = (value: string) => {
    onSearch(value);
    setActiveIndex(0);
    setBellOpen(false);
    setSearchOpen(value.trim().length > 0);
  };

  const selectHit = (hit: SearchHit) => {
    setSearchOpen(false);
    onSearch("");
    setActiveIndex(0);
    if (hit.type === "course") {
      navigate(`/subjects/${encodeURIComponent(hit.course.id)}`);
      return;
    }
    navigate(
      `/subjects/${encodeURIComponent(hit.assignment.course_id)}?assignment=${encodeURIComponent(hit.assignment.id)}`,
    );
  };

  const handleSearchKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    const count = results.hits.length;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (count === 0) {
        return;
      }
      setSearchOpen(true);
      setActiveIndex((index) => (index + 1) % count);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (count === 0) {
        return;
      }
      setSearchOpen(true);
      setActiveIndex((index) => (index - 1 + count) % count);
      return;
    }
    if (event.key === "Enter") {
      const hit = results.hits[activeIndex];
      if (hit) {
        event.preventDefault();
        selectHit(hit);
      }
      return;
    }
    if (event.key === "Escape") {
      setSearchOpen(false);
    }
  };

  return (
    <header className="topbar">
      <div className="topbar-search">
        <input
          id="global-search"
          type="search"
          placeholder={t("topbar.searchPlaceholder")}
          value={search}
          onChange={(event) => handleSearchChange(event.target.value)}
          onFocus={() => {
            if (hasQuery) {
              openSearch();
            }
          }}
          onKeyDown={handleSearchKeyDown}
          aria-label={t("topbar.searchPlaceholder")}
          aria-expanded={resultsVisible}
          aria-controls="global-search-results"
          autoComplete="off"
        />
        {resultsVisible ? (
          <>
            <div
              className="search-backdrop"
              role="presentation"
              onClick={() => setSearchOpen(false)}
            />
            <SearchResults
              query={search.trim()}
              hits={results.hits}
              activeIndex={activeIndex}
              onSelect={selectHit}
              onHover={setActiveIndex}
            />
          </>
        ) : null}
      </div>

      <div className="topbar-actions">
        {/* Retry hint (stage 5/§18): the server's sanitized reason wins over
            the generic client-side one when the last scheduled sync failed. */}
        {error || status?.sync_status === "error" ? (
          <span
            className="topbar-error"
            title={status?.last_sync_error ?? error ?? undefined}
          >
            {t("topbar.cachedData")}
          </span>
        ) : null}
        {/* Re-auth prompt: the Google grant is broken, the schedule is
            paused until this browser signs in again (stage 5/§63). */}
        {status?.sync_status === "needs_reauth" ? (
          <button
            type="button"
            className="button"
            title={t("topbar.needsReauthHint")}
            onClick={() => void login()}
          >
            <KeyRound size={15} /> {t("topbar.signInAgain")}
          </button>
        ) : null}
        <SyncTime lastSync={status?.last_sync ?? null} />
        {/* A stuck sync (ADR-0032) used to render a sentence telling the user
            to sync again "in a few minutes" — advice the UI made impossible,
            because the Sync button below is disabled exactly while `syncing`
            is true, and the server answers 409 to a manual request for a user
            whose claim is in flight. The explanation now comes WITH the action
            it describes: one button, active, that abandons the stuck claim.
            The plain Sync button is hidden rather than shown disabled, so the
            topbar never offers two near-identical controls. */}
        {syncStuck ? (
          <>
            <span className="sync-time" role="status">
              {t("topbar.syncStuck")}
            </span>
            <button
              type="button"
              className="button button-primary"
              title={t("topbar.syncRestartHint")}
              onClick={() => void syncRestart()}
            >
              <RefreshCw size={15} />
              {t("topbar.syncRestart")}
            </button>
          </>
        ) : (
          <button
            type="button"
            className="button button-primary"
            onClick={() => void syncNow()}
            disabled={syncing}
          >
            <RefreshCw size={15} className={cn(syncing && "spin")} />
            {syncing ? t("topbar.syncing") : t("topbar.sync")}
          </button>
        )}
        <button
          type="button"
          className="icon-button"
          aria-label={t("topbar.notifications")}
          onClick={() => {
            setSearchOpen(false);
            setBellOpen((open) => !open);
          }}
        >
          <Bell size={18} />
          {notificationCount > 0 ? (
            <span className="badge-dot">{notificationCount}</span>
          ) : null}
        </button>
        <button
          type="button"
          className="icon-button"
          aria-label={t("topbar.toggleTheme")}
          onClick={() => setTheme(isDark ? "light" : "dark")}
        >
          {isDark ? <Sun size={18} /> : <Moon size={18} />}
        </button>
      </div>

      {bellOpen ? (
        <NotificationCenter
          items={notifications}
          onDismiss={(item) => dismissNotification(notificationKey(item))}
          onClearAll={() =>
            dismissAllNotifications(notifications.map(notificationKey))
          }
          onClose={() => setBellOpen(false)}
        />
      ) : null}
    </header>
  );
}

export type NotificationItem = {
  assignment: Assignment;
  kind: "overdue" | "today" | "tomorrow";
};

/**
 * Dismissal key: kind + assignment id, so hiding a reminder is scoped to one
 * category — the same assignment reappears when it moves to another category
 * (e.g. "due tomorrow" → "due today").
 */
function notificationKey(item: NotificationItem): string {
  return `${item.kind}:${item.assignment.id}`;
}

export function buildNotifications(
  assignments: Assignment[],
): NotificationItem[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const tomorrow = new Date(today.getTime() + 24 * 60 * 60 * 1000);
  const items: NotificationItem[] = [];
  for (const assignment of assignments) {
    if (assignment.submitted || !assignment.due_at) {
      continue;
    }
    const due = parseDue(assignment.due_at);
    if (due && due < today) {
      items.push({ assignment, kind: "overdue" });
    } else if (due && due.toDateString() === today.toDateString()) {
      items.push({ assignment, kind: "today" });
    } else if (due && due.toDateString() === tomorrow.toDateString()) {
      items.push({ assignment, kind: "tomorrow" });
    }
  }
  return items;
}
