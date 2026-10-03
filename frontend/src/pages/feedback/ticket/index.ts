/**
 * One ticket from the user's side: the conversation, the moderator's replies and
 * whether it is still open.
 *
 * Read-only by design. The reply is a moderator's action, and the user changes
 * a ticket's state by opening a new one — a conversation two parties can both
 * write to is a support inbox, not feedback.
 */

export { FeedbackTicket } from "./ui/FeedbackTicket.tsx";