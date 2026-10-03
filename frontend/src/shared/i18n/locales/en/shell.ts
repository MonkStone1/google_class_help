/**
 * The shell strings, en.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/en/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const en_shell = {
  "topbar.searchPlaceholder": "Search assignments, subjects, teachers…  (Ctrl+K)",
  "topbar.neverSynced": "Never synchronized",
  "topbar.lastSync": "Last synchronized: {time}",
  "topbar.cachedData": "Cached data",
  "topbar.sync": "Sync",
  "topbar.syncing": "Syncing…",
  "topbar.syncStuck": "This sync is taking unusually long and may be stuck. Restarting abandons the current attempt and starts a new one.",
  "topbar.syncRestart": "Restart sync",
  "topbar.syncRestartHint": "Abandon the current attempt and start a new synchronization. Cached data stays available until the new run finishes.",
  "topbar.signInAgain": "Sign in again",
  "topbar.needsReauthHint": "Google access has expired. Sign in again to resume synchronization.",
  "topbar.notifications": "Notifications",
  "topbar.toggleTheme": "Toggle theme",
  "search.label": "Search results",
  "search.noResults": "No matches for “{query}”",
  "search.assignments": "Assignments",
  "search.subjects": "Subjects",
  "notif.title": "Reminders",
  "notif.empty": "Nothing needs your attention 🎉",
  "notif.overdue": "Overdue",
  "notif.dueToday": "Due today",
  "notif.dueTomorrow": "Due tomorrow",
  "notif.clearAll": "Clear all",
  "notif.dismiss": "Dismiss reminder",
  "stat.total": "Total assignments",
  "stat.completed": "Completed",
  "stat.missing": "Missing",
  "stat.overdue": "Overdue",
  "stat.dueToday": "Due today",
  "stat.average": "Overall average",
  "dash.title": "Dashboard",
  "dash.showingCached": "Showing your last synchronized data.",
  "dash.nothingOverdue": "Nothing overdue 🎉",
  "dash.caughtUp": "You are fully caught up.",
  "dash.today": "Today",
  "dash.noToday": "No assignments due today 🎉",
  "dash.tomorrow": "Tomorrow",
  "dash.noTomorrow": "No assignments due tomorrow",
  "dash.upcoming": "Upcoming ({days} days)",
  "dash.noUpcoming": "Nothing due in the next {days} days",
  "dash.completed": "Recently completed",
  "dash.noCompleted": "No completed assignments yet",
  "dash.signInHint": "Sign in with Google in Settings (or press “Sync”) to load your Classroom data.",
} as const;
