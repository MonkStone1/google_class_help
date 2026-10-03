/**
 * The ticket status vocabulary — declared ONCE (ADR-0040 §5.2).
 *
 * Before this file, `STATUS_CLASS` lived in `pages/FeedbackTickets.tsx` and was
 * imported by three other pages, while `STATUS_LABEL` was **copied** into all
 * four of them — one of them with a loose `Record<string, I18nKey>` instead of
 * the typed `Record<FeedbackStatus, I18nKey>`. Adding a backend status meant
 * editing five files and the fifth was always the one nobody opened, which is
 * how a pill ends up showing the wrong word next to the right colour.
 *
 * Both dictionaries now live beside the `FeedbackStatus` union they describe,
 * so `tsc` refuses a status that has a label in one place and not the other.
 *
 * This is a domain rule and therefore an `entities/` module: it knows nothing
 * about fetches, routes or where a pill gets rendered.
 */

import type { I18nKey } from "../../../shared/i18n/index.ts";
import type { FeedbackStatus } from "../../../shared/types/index.ts";

/** The status pill reuses the app's badge tokens, no new palette. */
export const STATUS_CLASS: Record<FeedbackStatus, string> = {
    new: "badge badge-status-not",
    in_progress: "badge badge-todo",
    resolved: "badge badge-done",
};

export const STATUS_LABEL: Record<FeedbackStatus, I18nKey> = {
    new: "feedback.status.new",
    in_progress: "feedback.status.in_progress",
    resolved: "feedback.status.resolved",
};

/** The same vocabulary in the order the console's filter offers it. */
export const FEEDBACK_STATUSES: readonly FeedbackStatus[] = [
    "new",
    "in_progress",
    "resolved",
];