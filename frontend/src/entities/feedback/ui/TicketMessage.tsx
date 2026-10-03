import { formatDateTimeShort, toLocalDate } from "../../../shared/lib/index.ts";
import { useI18n } from "../../../shared/i18n/index.ts";
import type { TicketMessage } from "../../../shared/types/index.ts";
import { AttachmentList } from "./AttachmentList.tsx";
import { Markdown } from "../../../widgets/markdown/index.ts";

type Props = {
    message: TicketMessage;
    /** The real author, when the viewer may read it (the admin surface). */
    authorEmail?: string | null;
};

/**
 * One message of a ticket conversation (ADR-0035).
 *
 * The visual distinction branches on `author_type` — the machine-readable flag
 * the backend writes — and NEVER on the name or the e-mail: two administrators
 * may post under the same public name, and one person may answer under two.
 * Styling on the name would put the badge on the wrong message.
 *
 * ADMIN messages get their own surface (accent-soft background, accent left
 * border, a Support badge) so the answer is recognisable at a glance in both
 * themes — a support thread without that distinction is just noise to the user.
 */
export function TicketMessage({ message, authorEmail = null }: Props) {
    const { t } = useI18n();
    const isAdmin = message.author_type === "ADMIN";
    return (
        <article
            className={`ticket-message ${isAdmin ? "ticket-message-admin" : "ticket-message-user"}`}
        >
            <header className="ticket-message-header">
                <span className="ticket-message-author">
                    {isAdmin ? (
                        <span className="badge badge-role ticket-support-badge">
                            {t("feedback.supportBadge")}
                        </span>
                    ) : null}
                    <span className="ticket-message-name">
                        {message.display_name}
                    </span>
                    {authorEmail ? (
                        <span className="ticket-message-email">
                            {authorEmail}
                        </span>
                    ) : null}
                </span>
                <time
                    className="ticket-message-date"
                    dateTime={message.created_at}
                >
                    {formatDateTimeShort(toLocalDate(message.created_at))}
                </time>
            </header>
            {/* Stored Markdown, rendered through the sanitizer — never innerHTML. */}
            <Markdown>{message.body_markdown}</Markdown>
            <AttachmentList attachments={message.attachments} />
        </article>
    );
}

/**
 * The whole conversation of one ticket, oldest first (ADR-0035).
 *
 * The order is the server's: the API reads messages chronologically, so the
 * component does not re-sort them and cannot disagree about the sequence.
 */
export function TicketConversation({
    messages,
    showAuthorEmail = false,
}: {
    messages: TicketMessage[];
    /** The admin surface may show the real author of every message. */
    showAuthorEmail?: boolean;
}) {
    return (
        <div className="ticket-conversation">
            {messages.map((message) => (
                <TicketMessage
                    key={message.id}
                    message={message}
                    authorEmail={
                        // The `in` narrowing is what keeps this honest: only the admin
                        // projection carries `author_email`, and the user surface simply
                        // has no such field to read.
                        showAuthorEmail && "author_email" in message
                            ? (message.author_email as string | null)
                            : null
                    }
                />
            ))}
        </div>
    );
}
