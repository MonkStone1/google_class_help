import { Inbox, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, type ApiError } from "../shared/api/index.ts";
import { EmptyState, SectionSkeleton } from "../shared/ui/Skeletons.tsx";
import { formatDateTimeShort, toLocalDate } from "../shared/lib/dates.ts";
import { useI18n } from "../shared/i18n/index.ts";
import type {
    AdminTicketPage,
    FeedbackCategory,
    FeedbackStatus,
} from "../shared/types/index.ts";
import type { I18nKey } from "../shared/i18n/index.ts";
import { STATUS_CLASS, STATUS_LABEL } from "../entities/feedback/index.ts";

const STATUSES: (FeedbackStatus | "")[] = [
    "",
    "new",
    "in_progress",
    "resolved",
];
const CATEGORIES: (FeedbackCategory | "")[] = [
    "",
    "bug",
    "problem",
    "suggestion",
    "other",
];

const CATEGORY_LABEL: Record<string, I18nKey> = {
    bug: "feedback.category.bug",
    problem: "feedback.category.problem",
    suggestion: "feedback.category.suggestion",
    other: "feedback.category.other",
};

const PAGE_SIZE = 25;

/**
 * Every ticket, with filters and search (ADR-0035).
 *
 * The SERVER does the filtering and the paging (`total` comes with the page),
 * so a growing table is never shipped to the browser to be filtered there.
 * Changing a filter resets the offset: staying on page 3 of a narrower result
 * set would show an empty list for no reason.
 */
export function AdminFeedback() {
    const { t } = useI18n();
    const [status, setStatus] = useState<FeedbackStatus | "">("");
    const [category, setCategory] = useState<FeedbackCategory | "">("");
    const [query, setQuery] = useState("");
    const [search, setSearch] = useState("");
    const [offset, setOffset] = useState(0);
    const [page, setPage] = useState<AdminTicketPage | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const controller = new AbortController();
        let cancelled = false;
        api.getAdminTickets(
            {
                status: status || undefined,
                category: category || undefined,
                q: search || undefined,
                limit: PAGE_SIZE,
                offset,
            },
            controller.signal,
        )
            .then((answer) => {
                if (!cancelled) setPage(answer);
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
    }, [status, category, search, offset, t]);

    const changeFilter = (apply: () => void) => {
        apply();
        setOffset(0);
    };

    return (
        <div className="page">
            <div className="page-header">
                <div>
                    <h1>{t("admin.ticketListTitle")}</h1>
                </div>
                <div className="page-header-actions">
                    <Link to="/admin" className="back-link">
                        ← {t("admin.backToAdmin")}
                    </Link>
                </div>
            </div>

            <div className="card admin-filters">
                <div className="admin-filter-row">
                    <label
                        className="settings-label"
                        htmlFor="admin-filter-status"
                    >
                        {t("admin.filterStatus")}
                    </label>
                    <select
                        id="admin-filter-status"
                        className="select-input"
                        value={status}
                        onChange={(event) =>
                            changeFilter(() =>
                                setStatus(
                                    event.target.value as FeedbackStatus | "",
                                ),
                            )
                        }
                    >
                        {STATUSES.map((value) => (
                            <option key={value || "any"} value={value}>
                                {value
                                    ? t(STATUS_LABEL[value])
                                    : t("admin.filterAny")}
                            </option>
                        ))}
                    </select>

                    <label
                        className="settings-label"
                        htmlFor="admin-filter-category"
                    >
                        {t("admin.filterCategory")}
                    </label>
                    <select
                        id="admin-filter-category"
                        className="select-input"
                        value={category}
                        onChange={(event) =>
                            changeFilter(() =>
                                setCategory(
                                    event.target.value as FeedbackCategory | "",
                                ),
                            )
                        }
                    >
                        {CATEGORIES.map((value) => (
                            <option key={value || "any"} value={value}>
                                {value
                                    ? t(CATEGORY_LABEL[value])
                                    : t("admin.filterAny")}
                            </option>
                        ))}
                    </select>
                </div>

                <div className="admin-filter-row">
                    <input
                        className="feedback-input"
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                        onKeyDown={(event) => {
                            if (event.key === "Enter") {
                                changeFilter(() => setSearch(query.trim()));
                            }
                        }}
                        placeholder={t("admin.searchPlaceholder")}
                        aria-label={t("admin.search")}
                    />
                    <button
                        type="button"
                        className="button button-primary"
                        onClick={() =>
                            changeFilter(() => setSearch(query.trim()))
                        }
                    >
                        <Search size={15} /> {t("admin.search")}
                    </button>
                    <button
                        type="button"
                        className="button"
                        onClick={() =>
                            changeFilter(() => {
                                setQuery("");
                                setSearch("");
                                setStatus("");
                                setCategory("");
                            })
                        }
                    >
                        <X size={15} /> {t("admin.clearFilters")}
                    </button>
                </div>
            </div>

            {error ? (
                <div className="alert alert-error" role="alert">
                    {error}
                </div>
            ) : null}

            {page === null && !error ? <SectionSkeleton rows={4} /> : null}

            {page !== null && page.items.length === 0 ? (
                <EmptyState
                    icon={<Inbox size={28} />}
                    title={t("admin.empty")}
                />
            ) : null}

            {/*
              ONE list, rendered once.

              This exact block used to appear TWICE in this file under the same
              `page.items.length > 0` condition, so every ticket was painted as
              two identical rows that both re-rendered together — which is what
              an administrator saw as "two copies that update in parallel". It
              happened only on this tab because `AdminDashboard.tsx` has one
              such block, and the duplication was in the markup, not in the
              request: the server paged once and both copies read the same page.

              Do not add a second render of the list above the error banner —
              `AdminFeedback.test.tsx` pins the row count per ticket.
            */}
            {page !== null && page.items.length > 0 ? (
                <>
                    <ul className="ticket-list">
                        {page.items.map((ticket) => (
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
                                            {t("admin.reporter")}:{" "}
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
                    {page.total > PAGE_SIZE ? (
                        <AdminPagination
                            offset={offset}
                            total={page.total}
                            onChange={setOffset}
                        />
                    ) : null}
                </>
            ) : null}
        </div>
    );
}

/** Previous/next over a server-paged list; the total comes with the page. */
function AdminPagination({
    offset,
    total,
    onChange,
}: {
    offset: number;
    total: number;
    onChange: (offset: number) => void;
}) {
    return (
        <div className="admin-pagination">
            <button
                type="button"
                className="button"
                disabled={offset === 0}
                onClick={() => onChange(Math.max(0, offset - PAGE_SIZE))}
            >
                ←
            </button>
            <span className="updated-label">
                {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} / {total}
            </span>
            <button
                type="button"
                className="button"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => onChange(offset + PAGE_SIZE)}
            >
                →
            </button>
        </div>
    );
}
