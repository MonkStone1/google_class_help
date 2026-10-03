/**
 * The landing strings, en.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/en/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const en_landing = {
  // Public landing page (ADR-0029). Shown to visitors who hold no session:
  // the site's own description of itself, its two sign-in entry points and
  // the link to the privacy policy.
  "landing.documentTitle": "Classroom Dashboard — your Google Classroom in one place",
  "landing.brand": "Classroom Dashboard",
  "landing.heroTitle": "Your Google Classroom in one place",
  "landing.heroLead": "A personal dashboard for Google Classroom: subjects, assignments, deadlines, grades and reminders — gathered on one screen instead of scattered across Classroom tabs.",
  "landing.signIn": "Sign in with Google",
  "landing.signInHint": "You need a Google account that has Classroom courses. The access requested is read-only.",
  "landing.whatTitle": "What this site is",
  "landing.whatBody": "This is a personal dashboard for Google Classroom. Sign in with your own Google account and the site shows your Classroom data back to you: it reads what you already have access to, so you never enter anything twice. It is a convenient view on top of Google Classroom — not a replacement for it, and not affiliated with Google.",
  "landing.featuresTitle": "What it does",
  "landing.feature.subjects.title": "Subjects",
  "landing.feature.subjects.text": "All your courses on one screen: teachers, assignment counts and the average grade per course.",
  "landing.feature.assignments.title": "Assignments and deadlines",
  "landing.feature.assignments.text": "Every assignment with its due date and submission state, filtered by status, subject or date.",
  "landing.feature.grades.title": "Grades",
  "landing.feature.grades.text": "Overall average, per-assignment grades and a progress table for each subject.",
  "landing.feature.calendar.title": "Calendar",
  "landing.feature.calendar.text": "Month, week and day views, so every due date is visible at a glance.",
  "landing.feature.search.title": "Search and reminders",
  "landing.feature.search.text": "Search across assignments and subjects, plus a list of what is overdue, due today and due tomorrow.",
  "landing.feature.teacher.title": "Teacher mode",
  "landing.feature.teacher.text": "For the courses you teach: the roster, submitted work and the grade matrix per course.",
  "landing.howTitle": "How it works",
  "landing.how.signIn.title": "Sign in",
  "landing.how.signIn.text": "Press the button and confirm access on Google’s page. The site never sees your password.",
  "landing.how.sync.title": "The data is synchronized",
  "landing.how.sync.text": "Your courses, assignments and grades are loaded onto the server and refreshed automatically in the background.",
  "landing.how.dashboard.title": "You work in the dashboard",
  "landing.how.dashboard.text": "Deadlines, grades and overdue work end up in one place — and nothing in Classroom is ever changed.",
  "landing.dataTitle": "Your data",
  "landing.data.readOnly": "The app requests read-only access: your courses, your course work and your own submissions. Nothing else.",
  "landing.data.neverWrites": "It never creates, edits or deletes anything in Google Classroom, and never posts on your behalf.",
  "landing.data.storage": "Your profile, the encrypted access tokens and a cache of your Classroom data are stored on the server, scoped to your account. You can clear that cache at any time in Settings.",
  "landing.data.privacyLink": "Read the full privacy policy",
  "landing.ctaTitle": "Ready to start?",
  "landing.ctaText": "Sign in with the Google account that has your classes — the dashboard picks up your data on its own.",
  "landing.challengeHint": "Complete the verification below, then sign in.",
  "landing.languageLabel": "Language",
  "landing.footer.privacy": "Privacy Policy",
  "landing.footer.terms": "Terms of Service",
  "landing.footer.notGoogle": "Google Classroom is a trademark of Google LLC. This service is not affiliated with Google LLC.",
  "landing.footer.contact": "Questions and data deletion requests:",
  "landing.footer.repository": "github.com/MonkStone1/google_class_help",
  // Donations (ADR-0037). One wording, two surfaces: the public landing
  // section and the Settings card render the same block, so the promise made
  // to an anonymous visitor is the promise a signed-in user reads.
  "donate.title": "Support the project",
  "donate.note": "This money goes to keeping the project running and developing it.",
  "donate.qrAlt": "Donation QR code for {bank}",
  "donate.preview": "Enlarge the {bank} QR code",
  "donate.bank.monobank": "Monobank",
  "donate.bank.privatbank": "PrivatBank",
} as const;
