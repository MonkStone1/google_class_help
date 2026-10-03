import { LifeBuoy } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, type ApiError } from "../shared/api/index.ts";
import { EmptyState, SectionSkeleton } from "../components/Skeletons.tsx";
import { formatDateTimeShort, toLocalDate } from "../shared/lib/dates.ts";
import { useI18n } from "../shared/i18n/index.ts";
import type { FeedbackStatus, FeedbackTicket } from "../shared/types/index.ts";
import type { I18nKey } from "../shared/i18n/index.ts";

const STATUS_LABEL: Record<FeedbackStatus, I18nKey> = {
    new: "feedback.status.new",
    in_progress: "feedback.status.in_progress",
    resolved: "feedback.status.resolved",
};

/** The status pill reuses the app's badge tokens, no new palette. */
export const STATUS_CLASS: Record<FeedbackStatus, string> = {
    new: "badge badge-status-not",
    in_progress: "badge badge-todo",
    resolved: "badge badge-done",
};

/**
 * "My tickets" (ADR-0035).
 *
 * The list is already sorted by last activity by the server, so the component
 * renders what it gets: re-sorting here could disagree with the ordering the
 * admin side sees. A 404 from the API means the ticket is not the caller's (or
 * is gone) and is shown as such — the API never discloses which.
 */
export function FeedbackTickets() {
    const { t } = useI18n();
    const [tickets, setTickets] = useState<FeedbackTicket[] | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const controller = new AbortController();
        let cancelled = false;
        api.getMyTickets(controller.signal)
            .then((data) => {
                if (!cancelled) setTickets(data);
            })
            .catch((err: unknown) => {
                if (cancelled) return;
                if ((err as ApiError).status === 0) return;
                setError((err as ApiError).message || t("feedback.loadFailed"));
            });
        return () => {
            cancelled = true;
            controller.abort();
        };
    }, [t]);

    return (
        <div className="page">
            <div className="page-header">
                <div>
                    <Link to="/feedback" className="back-link">
                        ← {t("feedback.title")}
                    </Link>
                    <h1>{t("feedback.listTitle")}</h1>
                </div>
                <div className="page-header-actions">
                    <Link to="/feedback/new" className="button button-primary">
                        {t("feedback.submit")}
                    </Link>
                </div>
            </div>

            {error ? (
                <div className="alert alert-error" role="alert">
                    {error}
                </div>
            ) : null}

            {tickets === null && !error ? <SectionSkeleton rows={3} /> : null}

            {tickets !== null && tickets.length === 0 ? (
                <EmptyState
                    icon={<LifeBuoy size={28} />}
                    title={t("feedback.empty")}
                    subtitle={t("feedback.emptyHint")}
                    action={
                        <Link
                            to="/feedback/new"
                            className="button button-primary"
                        >
                            {t("feedback.createTitle")}
                        </Link>
                    }
                />
            ) : null}

            {tickets !== null && tickets.length > 0 ? (
                <ul className="ticket-list">
                    {tickets.map((ticket) => (
                        <li key={ticket.id}>
                            <Link
                                to={`/feedback/tickets/${ticket.id}`}
                                className="card ticket-list-item"
                            >
                                <div className="ticket-list-top">
                                    <span className="ticket-list-id">
                                        {t("feedback.ticketNumber", {
                                            id: ticket.id,
                                        })}
                                    </span>
                                    <span
                                        className={STATUS_CLASS[ticket.status]}
                                    >
                                        {t(STATUS_LABEL[ticket.status])}
                                    </span>
                                </div>
                                <div className="ticket-list-subject">
                                    {ticket.subject}
                                </div>
                                <div className="ticket-list-meta">
                                    <span>
                                        {t("feedback.messagesCount", {
                                            count: ticket.message_count,
                                        })}
                                    </span>
                                    <span>
                                        {formatDateTimeShort(
                                            toLocalDate(ticket.updated_at),
                                        )}
                                    </span>
                                </div>
                            </Link>
                        </li>
                    ))}
                </ul>
            ) : null}
        </div>
    );
}
