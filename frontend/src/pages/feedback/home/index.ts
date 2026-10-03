/**
 * The feedback section's front door: the user's own tickets and how to open one.
 *
 * Separate from `new/` because opening a ticket and reading your tickets are
 * different intentions, and a teacher who only wants to check an answer should
 * not face a form.
 */

export { FeedbackHome } from "./ui/FeedbackHome.tsx";