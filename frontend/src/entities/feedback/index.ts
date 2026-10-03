/**
 * The feedback domain: tickets, their statuses and the pieces of a
 * conversation that both the user surface and the console render.
 *
 * No fetch, no router — the domain states what a ticket IS and how its status
 * is spelled; `features/` and `pages/` decide where to ask for it (ADR-0040).
 */

export {
    FEEDBACK_STATUSES,
    STATUS_CLASS,
    STATUS_LABEL,
} from "./model/status.ts";
export { AttachmentList } from "./ui/AttachmentList.tsx";
export { TicketConversation, TicketMessage } from "./ui/TicketMessage.tsx";