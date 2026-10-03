/**
 * The strings every screen needs, en.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/en/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const en_base = {
  "app.title": "Classroom Dashboard",
  "nav.dashboard": "Dashboard",
  "nav.subjects": "Subjects",
  "nav.assignments": "Assignments",
  "nav.grades": "Grades",
  "nav.calendar": "Calendar",
  "nav.settings": "Settings",
  "nav.feedback": "Feedback",
  "nav.admin": "Administration",
  // The /admin console is reached only by its URL (ADR-0036); these two entries
  // exist in the console's own sidebar, never in the public navigation.
  "nav.adminTickets": "Tickets",
  "nav.admins": "Administrators",
  "nav.overdue.one": "1 overdue assignment",
  "nav.overdue.many": "{count} overdue assignments",
  // Toasts (ADR-0030). `region` and `dismiss` replace sonner's own hardcoded
  // English aria labels, so no untranslated string reaches a screen reader.
  "toast.region": "Notifications",
  "toast.dismiss": "Dismiss notification",
  "toast.syncCompleted": "Synchronization complete",
  "toast.syncCompletedAt": "Classroom data updated at {time}",
  "toast.syncFailed": "Synchronization failed",
  "toast.syncNeedsReauth": "Google access expired",
  "signin.turnstileRequired": "Please complete the verification challenge to continue.",
  "signin.turnstilePending": "Verification required before signing in.",
  "card.openInClassroom": "Open in Google Classroom",
  "date.today": "Today",
  "date.tomorrow": "Tomorrow",
  "date.yesterday": "Yesterday",
  "date.daysOverdue": "{count} days overdue",
  "date.inDays": "In {count} days",
  "date.noDueDate": "No due date",
} as const;
