import { Send } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
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
 */
export function FeedbackTicket() {
    const { t } = useI18n();
    const { id } = useParams();
    const ticketId = Number(id);
    const [ticket, setTicket] = useState<FeedbackTicketDetail | null>(null);
    const [reply, setReply] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [missing, setMissing] = useState(false);
    const [reopened, setReopened] = useState(false);

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

            <TicketConversation messages={ticket.messages} />

            <form className="card feedback-form" onSubmit={send}>
                <label className="settings-label" htmlFor="feedback-reply">
                    {t("feedback.reply")}
                </label>
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
                        {busy ? t("feedback.sending") : t("feedback.sendReply")}
                    </button>
                </div>
            </form>
        </div>
    );
}
