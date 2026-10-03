import type { Wire } from "./wire.ts";

/**
 * Ticket types (ADR-0035). The wire shapes come from the generated schema like
 * every other response; only the CLOSED SETS the UI must reason about are
 * narrowed here, because the backend validates them server-side and an
 * unexpected value must not compile into the UI as a legal one.
 */
export type FeedbackCategory = "suggestion" | "bug" | "problem" | "other";

export type FeedbackStatus = "new" | "in_progress" | "resolved";

/** USER | ADMIN — the machine-readable author distinction, never a name. */
export type MessageAuthorType = "USER" | "ADMIN";

export type TicketAttachment = Wire<"AttachmentOut">;

/**
 * The base message shape both surfaces share.
 *
 * `author_type` is narrowed here (the backend validates it against the closed
 * set), so a component can compare it without a cast. `AdminTicketMessage`
 * extends this with the internal author — it is a SUPERTYPE, so a component
 * that takes `TicketMessage` renders either projection.
 */
type MessageBase = Omit<Wire<"MessageOut">, "author_type"> & {
    author_type: MessageAuthorType;
};

export type TicketMessage = MessageBase;

/** The admin projection of a message: the same body plus the real author. */
export type AdminTicketMessage = MessageBase &
    Pick<Wire<"AdminMessageOut">, "author_user_id" | "author_email">;

export type FeedbackTicket = Omit<Wire<"TicketOut">, "status"> & {
    status: FeedbackStatus;
};

export type FeedbackTicketDetail = Omit<
    Wire<"TicketDetailOut">,
    "status" | "messages"
> & {
    status: FeedbackStatus;
    messages: TicketMessage[];
};

/** The admin projection of a ticket: the same row plus its owner. */
export type AdminTicket = Omit<Wire<"AdminTicketOut">, "status"> & {
    status: FeedbackStatus;
};

/** A page of the admin list; the items carry the narrowed status. */
export type AdminTicketPage = Omit<Wire<"AdminTicketListOut">, "items"> & {
    items: AdminTicket[];
};

export type AdminTicketDetail = Omit<
    Wire<"AdminTicketDetailOut">,
    "status" | "messages"
> & {
    status: FeedbackStatus;
    messages: AdminTicketMessage[];
};

export type FeedbackStats = Wire<"FeedbackStatsOut">;

/**
 * One row of the administrator registry (ADR-0036).
 *
 * `name` is derived server-side from `email` — there is no editable name, and no
 * field here identifies the Super Admin, because the Super Admin has no row at
 * all: they are the `SUPER_ADMIN_EMAIL` environment value.
 */
export type Administrator = Wire<"AdminOut">;