/**
 * The feedback strings, en.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/en/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const en_feedback = {
  // ------------------------------------------------------------- feedback
  // ADR-0035. The entry page deliberately offers TWO choices instead of opening
  // the form: "report something" and "read my reports" are different intents,
  // and the copy has to make that obvious in every language.
  "feedback.title": "Feedback",
  "feedback.subtitle": "Tell us what is wrong, or follow what you have already reported.",
  "feedback.createTitle": "Create a ticket",
  "feedback.createText": "Describe the problem or your suggestion. You will be able to read the answer here.",
  "feedback.mineTitle": "My tickets",
  "feedback.mineText": "Follow the conversations you started, with every reply in one place.",
  "feedback.newTitle": "New ticket",
  "feedback.newLead": "Your Google account is already known, so there are no name or e-mail fields here.",
  "feedback.category": "Category",
  "feedback.category.suggestion": "Suggestion",
  "feedback.category.bug": "Bug",
  "feedback.category.problem": "Problem",
  "feedback.category.other": "Other",
  "feedback.subject": "Subject",
  "feedback.subjectPlaceholder": "Short summary, e.g. “Grades are not updating”",
  "feedback.message": "Message",
  "feedback.messagePlaceholder": "Describe what happened. Markdown is supported — **bold**, `code`, lists.",
  "feedback.attachments": "Attachments",
  "feedback.attachmentsHint": "Optional. Up to 3 files, 5 MB each (jpg, png, gif, pdf, txt).",
  "feedback.addFile": "Add file",
  "feedback.removeFile": "Remove {name}",
  "feedback.submit": "Send ticket",
  "feedback.submitting": "Sending…",
  "feedback.created": "Your ticket has been sent.",
  "feedback.reply": "Reply",
  "feedback.replyPlaceholder": "Write your reply…",
  "feedback.sendReply": "Send reply",
  "feedback.sending": "Sending…",
  "feedback.replied": "Your reply has been sent.",
  "feedback.reopenedNotice": "This ticket was resolved; your reply has reopened it.",
  "feedback.listTitle": "My tickets",
  "feedback.empty": "You have no tickets yet.",
  "feedback.emptyHint": "Report a problem and the answer will appear here.",
  "feedback.loading": "Loading tickets…",
  "feedback.ticketNumber": "Ticket #{id}",
  "feedback.status.new": "New",
  "feedback.status.in_progress": "In progress",
  "feedback.status.resolved": "Resolved",
  "feedback.messagesCount": "{count} messages",
  "feedback.subjectRequired": "Please enter a subject.",
  "feedback.messageRequired": "Please describe the problem.",
  "feedback.loadFailed": "Could not load the tickets.",
  "feedback.notFound": "This ticket does not exist or is not yours.",
  "feedback.downloadFile": "Download {name}",
  "feedback.you": "You",
  "feedback.supportBadge": "Support",
} as const;
