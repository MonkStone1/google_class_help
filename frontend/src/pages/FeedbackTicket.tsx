import { ChevronDown, Send } from "lucide-react";
import { useEffect, useId, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";

import { api, type ApiError } from "../api.ts";
import { MarkdownField } from "../components/MarkdownField.tsx";
import { SectionSkeleton } from "../components/Skeletons.tsx";
import { TicketConversation } from "../components/TicketMessage.tsx";
import { useI18n } from "../i18n.ts";
import type { FeedbackTicketDetail } from "../types.ts";
import { STATUS_CLASS } from "./FeedbackTickets.tsx";
import type { I18nKey } from "../i18n.ts";

const STATUS_LABEL: Record<string, I18nKey> = {
    new: "feedback.status.new",
    in_progress: "feedback.status.in_progress",
    resolved: "feedback.status.resolved",
};

/**
 * One own ticket with the conversation and a reply form (ADR-0035).
 *
 * The reopen rule is visible: replying to a `resolved` ticket puts it back to
 * `in_progress` on the server, so after a successful reply this page shows a
 * notice instead of silently changing the badge — a user who answered a closed
 * ticket needs to see that it is live again.
 *
 * 404 is rendered as "does not exist or is not yours" — the API answers the
 * same for a ticket that never existed, so the UI must not invent a difference.
 *
 * The reply form sits ABOVE the conversation and starts COLLAPSED (п.5). A
 * reader opens a ticket to read the answer, not to type one, and a full-height
 * Markdown editor pushed every message below the fold. It unfolds on a click
 * and folds itself again once the reply is sent — the state is local, because
 * it is a momentary UI affordance and not something to persist or sync.
 */
export function FeedbackTicket() {
    const { t } = useI18n();
    const { id } = useParams();
    const ticketId = Number(id);
    const [ticket, setTicket] = useState<FeedbackTicketDetail | null>(null);
    const [reply, setReply] = useState("");
    const [formOpen, setFormOpen] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [missing, setMissing] = useState(false);
    const [reopened, setReopened] = useState(false);
    // Ties the toggle to the panel it controls, so the collapsed/expanded state
    // is announced rather than only drawn.
    const formId = useId();

    useEffect(() => {
        const controller = new AbortController();
        let cancelled = false;
        if (!Number.isFinite(ticketId)) {
            setMissing(true);
            return;
        }
        api.getMyTicket(ticketId, controller.signal)
            .then((data) => {
                if (!cancelled) setTicket(data);
            })
            .catch((err: unknown) => {
                if (cancelled) return;
                const apiError = err as ApiError;
                if (apiError.status === 0) return;
                if (apiError.status === 404) {
                    setMissing(true);
                    return;
                }
                setError(apiError.message || t("feedback.loadFailed"));
            });
        return () => {
            cancelled = true;
            controller.abort();
        };
    }, [ticketId, t]);

    const send = async (event: FormEvent) => {
        event.preventDefault();
        if (!reply.trim()) return;
        setBusy(true);
        try {
            // The was-resolved state is read BEFORE the reply, because the
            // server's answer will already say "in progress".
            const wasResolved = ticket?.status === "resolved";
            const updated = await api.replyToTicket(ticketId, reply);
            setTicket(updated);
            setReply("");
            // Fold the form away again: the reply is in the conversation, and
            // leaving an empty editor open under it would invite a second,
            // accidental one.
            setFormOpen(false);
            if (wasResolved) {
                setReopened(true);
            }
            toast.success(t("feedback.replied"));
        } catch (err) {
            const apiError = err as ApiError;
            toast.error(apiError.message || t("feedback.loadFailed"));
        } finally {
            setBusy(false);
        }
    };

    if (missing) {
        return (
            <div className="page">
                <div className="alert alert-warning" role="alert">
                    {t("feedback.notFound")}
                </div>
                <Link to="/feedback/tickets" className="back-link">
                    ← {t("feedback.listTitle")}
                </Link>
            </div>
        );
    }

    if (!ticket) {
        return (
            <div className="page">
                <SectionSkeleton rows={2} />
            </div>
        );
    }

    return (
        <div className="page">
            <div className="page-header">
                <div>
                    <Link to="/feedback/tickets" className="back-link">
                        ← {t("feedback.listTitle")}
                    </Link>
                    <h1>{ticket.subject}</h1>
                    <div className="page-subtitle">
                        {t("feedback.ticketNumber", { id: ticket.id })}{" "}
                        <span className={STATUS_CLASS[ticket.status]}>
                            {t(
                                STATUS_LABEL[ticket.status] ??
                                    "feedback.status.new",
                            )}
                        </span>
                    </div>
                </div>
            </div>

            {reopened ? (
                <div className="alert alert-info" role="status">
                    {t("feedback.reopenedNotice")}
                </div>
            ) : null}
            {error ? (
                <div className="alert alert-error" role="alert">
                    {error}
                </div>
            ) : null}

            {/*
              The reply affordance, above the conversation. A real button with
              `aria-expanded`/`aria-controls` rather than `<details>`: the header
              has to be a full-width row with a chevron on the right, and the
              panel it owns is a form, not a list — the same shape
              `CollapsibleCard` uses, kept local because that component is
              scoped to the settings surface.
            */}
            <section className="card feedback-reply">
                <button
                    type="button"
                    className="feedback-reply-toggle"
                    aria-expanded={formOpen}
                    aria-controls={formId}
                    onClick={() => setFormOpen((open) => !open)}
                >
                    <span className="feedback-reply-title">
                        {t("feedback.reply")}
                    </span>
                    <ChevronDown
                        size={17}
                        className="feedback-reply-chevron"
                    />
                </button>

                {formOpen ? (
                    <form
                        id={formId}
                        className="feedback-reply-form"
                        onSubmit={send}
                    >
                        <MarkdownField
                            id="feedback-reply"
                            value={reply}
                            onChange={setReply}
                            placeholder={t("feedback.replyPlaceholder")}
                            minHeight={160}
                            disabled={busy}
                        />
                        <div className="feedback-form-actions">
                            <button
                                type="submit"
                                className="button button-primary"
                                disabled={busy || reply.trim().length === 0}
                            >
                                <Send size={15} />{" "}
                                {busy
                                    ? t("feedback.sending")
                                    : t("feedback.sendReply")}
                            </button>
                        </div>
                    </form>
                ) : null}
            </section>

            <TicketConversation messages={ticket.messages} />
        </div>
    );
}
