import { CheckCircle2, Inbox, LifeBuoy, Loader } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, type ApiError } from "../shared/api/index.ts";
import { StatCard } from "../components/StatCard.tsx";
import { EmptyState, SectionSkeleton } from "../components/Skeletons.tsx";
import { formatDateTimeShort, toLocalDate } from "../shared/lib/dates.ts";
import { useI18n } from "../shared/i18n/index.ts";
import type { AdminTicket, FeedbackStats } from "../shared/types/index.ts";
import { STATUS_CLASS } from "./FeedbackTickets.tsx";
import type { I18nKey } from "../shared/i18n/index.ts";

const STATUS_LABEL: Record<string, I18nKey> = {
    new: "feedback.status.new",
    in_progress: "feedback.status.in_progress",
    resolved: "feedback.status.resolved",
};

/**
 * The administrator's landing page (ADR-0035).
 *
 * Counters come from `GET /api/admin/feedback/stats`, which is behind
 * `require_admin` — a regular user gets 403 and the route guard renders the
 * "not available" state before this ever loads. The five most recent tickets
 * are a preview, not a list: the list (with filters and search) is its own
 * route, so this page stays a dashboard rather than a second copy of it.
 */
export function AdminDashboard() {
    const { t } = useI18n();
    const [stats, setStats] = useState<FeedbackStats | null>(null);
    const [recent, setRecent] = useState<AdminTicket[] | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const controller = new AbortController();
        let cancelled = false;
        Promise.all([
            api.getAdminFeedbackStats(controller.signal),
            api.getAdminTickets({ limit: 5 }, controller.signal),
        ])
            .then(([statsAnswer, page]) => {
                if (cancelled) return;
                setStats(statsAnswer);
                setRecent(page.items);
            })
            .catch((err: unknown) => {
                if (cancelled) return;
                const apiError = err as ApiError;
                if (apiError.status === 0) return;
                setError(apiError.message || t("admin.loadFailed"));
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
                    <h1>{t("admin.dashboardTitle")}</h1>
                </div>
                <div className="page-header-actions">
                    <Link
                        to="/admin/feedback"
                        className="button button-primary"
                    >
                        {t("admin.ticketListTitle")}
                    </Link>
                </div>
            </div>

            {error ? (
                <div className="alert alert-error" role="alert">
                    {error}
                </div>
            ) : null}

            {stats === null && !error ? <SectionSkeleton rows={1} /> : null}

            {stats !== null ? (
                <div className="stat-grid">
                    <StatCard
                        label={t("admin.total")}
                        value={stats.total}
                        icon={<LifeBuoy size={18} />}
                    />
                    <StatCard
                        label={t("feedback.status.new")}
                        value={stats.new}
                        tone="warning"
                        icon={<Inbox size={18} />}
                    />
                    <StatCard
                        label={t("feedback.status.in_progress")}
                        value={stats.in_progress}
                        tone="default"
                        icon={<Loader size={18} />}
                    />
                    <StatCard
                        label={t("feedback.status.resolved")}
                        value={stats.resolved}
                        tone="success"
                        icon={<CheckCircle2 size={18} />}
                    />
                </div>
            ) : null}

            <div className="admin-recent">
                <h2>{t("admin.ticketListTitle")}</h2>
                {recent !== null && recent.length === 0 ? (
                    <EmptyState
                        icon={<Inbox size={28} />}
                        title={t("admin.empty")}
                    />
                ) : null}
                {recent !== null && recent.length > 0 ? (
                    <ul className="ticket-list">
                        {recent.map((ticket) => (
                            <li key={ticket.id}>
                                <Link
                                    to={`/admin/feedback/${ticket.id}`}
                                    className="card ticket-list-item"
                                >
                                    <div className="ticket-list-top">
                                        <span className="ticket-list-id">
                                            {t("feedback.ticketNumber", {
                                                id: ticket.id,
                                            })}
                                        </span>
                                        <span
                                            className={
                                                STATUS_CLASS[ticket.status]
                                            }
                                        >
                                            {t(
                                                STATUS_LABEL[ticket.status] ??
                                                    "feedback.status.new",
                                            )}
                                        </span>
                                    </div>
                                    <div className="ticket-list-subject">
                                        {ticket.subject}
                                    </div>
                                    <div className="ticket-list-meta">
                                        <span>
                                            {ticket.user_name ??
                                                ticket.user_email ??
                                                "—"}
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
        </div>
    );
}
