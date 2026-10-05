/**
 * The settings strings, en.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/en/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const en_settings = {
  "settings.title": "Settings",
  "settings.googleAccount": "Google account",
  "settings.connection": "Connection",
  "settings.signedIn": "Signed in as {name}",
  "settings.signedInNoName": "Signed in",
  "settings.notSignedIn": "Not signed in",
  "settings.signOut": "Sign out",
  "settings.signIn": "Sign in with Google",
  "settings.openConsent": "Open the Google sign-in page",
  "settings.signOutConfirm": "Sign out and remove the stored Google token from this PC?",
  "settings.signOutFailed": "Sign-out failed. Please try again.",
  "settings.lastSync": "Last synchronization",
  "settings.never": "Never",
  "settings.syncNow": "Sync now",
  "settings.appearance": "Appearance",
  "settings.theme": "Theme",
  "settings.light": "Light",
  "settings.dark": "Dark",
  "settings.system": "System",
  "settings.language": "Language",
  "settings.cards": "Assignment cards",
  "settings.comfortable": "Comfortable",
  "settings.compact": "Compact",
  "settings.dashboard": "Dashboard",
  "settings.upcomingPeriod": "Upcoming period",
  "settings.days": "{count} days",
  "settings.defaultSort": "Default sorting",
  "settings.visibleSections": "Visible sections",
  "settings.upcoming": "Upcoming",
  "settings.stats": "Statistics",
  "settings.reminders": "Reminders",
  // The scale the grade chart's axis counts in (ADR-0042). Classroom stores raw
  // points and never says what the maximum means, so the user declares it once.
  "settings.grading": "Grading",
  "settings.gradeScale": "Grading scale",
  "settings.gradeScale12": "12 points",
  "settings.gradeScale100": "100 points",
  "settings.gradeScaleHint": "Applied to every grade chart. Google Classroom stores raw points and does not say what they are out of.",
  // What a graded cell of the teacher matrix shows (ADR-0043). The teacher
  // picks: a raw "12" is read differently from "12 / 12".
  "settings.teacherMatrix": "All students table",
  "settings.teacherMatrixHint": "How a graded cell is drawn in the all-students table: the mark alone, the mark out of the task, the percentage alone, or all of them.",
  "settings.teacherMatrixPoints": "Points only",
  "settings.teacherMatrixRatio": "Points out of",
  "settings.teacherMatrixPercent": "Percent only",
  "settings.teacherMatrixBoth": "Points and percent",
  "settings.remindOverdue": "Remind about overdue assignments",
  "settings.remindToday": "Remind about assignments due today",
  "settings.remindTomorrow": "Remind about assignments due tomorrow",
  "settings.localData": "Local data",
  "settings.cachedData": "Cached Classroom data",
  "settings.cachedHint": "Stored locally in data/classroom.db. Clearing it removes everything until the next sync.",
  "settings.clearData": "Clear local data",
  "settings.clearConfirm": "Delete all locally cached assignments, subjects and grades? This cannot be undone.",
  "settings.cancel": "Cancel",
  "settings.confirmDelete": "Yes, delete",
  "settings.cleared": "Local cached data cleared.",
  "settings.clearFailed": "Could not clear the cache.",
} as const;
