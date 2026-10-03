import { Send, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { api, type ApiError } from "../../../../shared/api/index.ts";
import { ConfirmDialog } from "../../../../shared/ui/ConfirmDialog.tsx";
import { MarkdownField } from "../../../../widgets/markdown/MarkdownField.tsx";
import { SectionSkeleton } from "../../../../shared/ui/Skeletons.tsx";
import { TicketConversation } from "../../../../entities/feedback/ui/TicketMessage.tsx";
import { useI18n } from "../../../../shared/i18n/index.ts";
import type { AdminTicketDetail, FeedbackStatus } from "../../../../shared/types/index.ts";
import { STATUS_CLASS, STATUS_LABEL } from "../../../../entities/feedback/index.ts";

const STATUSES: FeedbackStatus[] = ["new", "in_progress", "resolved"];

/**
 * Any ticket, seen by an administrator (ADR-0035).
 *
 * Three things are deliberately separate here:
 *
 * - the **public display name** of the answer, which is only presentation. The
 *   real author is the authenticated administrator and is recorded by the
 *   server; the label is shown to the user so a team can answer under one name;
 * - the **status control**, which sends only `{status}`;
 * - the **delete button**, which is impossible to press without the
 *   confirmation dialog first — the dialog is not a nicety here, it is the
 *   only thing standing between a stray click and an irreversible loss.
 */
export function AdminFeedbackTicket() {
    const { t } = useI18n();
    const navigate = useNavigate();
    const { id } = useParams();
    const ticketId = Number(id);
    const [ticket, setTicket] = useState<AdminTicketDetail | null>(null);
    const [answer, setAnswer] = useState("");
    const [displayName, setDisplayName] = useState("");
    const [busy, setBusy] = useState(false);
    const [confirming, setConfirming] = useState(false);
    const [deleting, setDeleting] = useState(false);
    const [deleteError, setDeleteError] = useState<string | null>(null);
    const [missing, setMissing] = useState(false);

    useEffect(() => {
        const controller = new AbortController();
        let cancelled = false;
        if (!Number.isFinite(ticketId)) {
            setMissing(true);
            return;
        }
        api.getAdminTicket(ticketId, controller.signal)
            .then((data) => {
                if (!cancelled) setTicket(data);
            })
            .catch((err: unknown) => {
                if (cancelled) return;
                const apiError = err as ApiError;
                if (apiError.status === 0) return;
                // 403 means the session is not an administrator: the route guard
                // normally catches this, but the flag could have changed after
                // the page was mounted.
                if (apiError.status === 403 || apiError.status === 404) {
                    setMissing(true);
                    return;
                }
                toast.error(apiError.message || t("admin.loadFailed"));
            });
        return () => {
            cancelled = true;
            controller.abort();
        };
    }, [ticketId, t]);

    const sendAnswer = async (event: FormEvent) => {
        event.preventDefault();
        if (!answer.trim()) return;
        setBusy(true);
        try {
            const updated = await api.replyToTicketAsAdmin(
                ticketId,
                answer,
                displayName.trim() || null,
            );
            setTicket(updated);
            setAnswer("");
            toast.success(t("feedback.replied"));
        } catch (err) {
            const apiError = err as ApiError;
            toast.error(apiError.message || t("admin.loadFailed"));
        } finally {
            setBusy(false);
        }
    };

    const changeStatus = async (status: FeedbackStatus) => {
        try {
            const updated = await api.setTicketStatus(ticketId, status);
            setTicket(updated);
            toast.success(t("admin.statusChanged"));
        } catch (err) {
            const apiError = err as ApiError;
            toast.error(apiError.message || t("admin.loadFailed"));
        }
    };

    const remove = async () => {
        setDeleting(true);
        setDeleteError(null);
        try {
            await api.deleteTicket(ticketId);
            toast.success(t("admin.deleted"));
            navigate("/admin/feedback");
        } catch (err) {
            const apiError = err as ApiError;
            setDeleteError(apiError.message || t("admin.deleteFailed"));
            setDeleting(false);
        }
    };

    if (missing) {
        return (
            <div className="page">
                <div className="alert alert-warning" role="alert">
                    {t("admin.notAvailable")}
                </div>
                <Link to="/admin/feedback" className="back-link">
                    ← {t("admin.ticketListTitle")}
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
                    <Link to="/admin/feedback" className="back-link">
                        ← {t("admin.ticketListTitle")}
                    </Link>
                    <h1>{ticket.subject}</h1>
                    <div className="page-subtitle">
                        {t("feedback.ticketNumber", { id: ticket.id })}
                        {ticket.user_email
                            ? ` · ${t("admin.reporter")}: ${ticket.user_email}`
                            : ""}
                    </div>
                </div>
                <div className="page-header-actions">
                    <button
                        type="button"
                        className="button button-danger"
                        onClick={() => setConfirming(true)}
                    >
                        <Trash2 size={15} /> {t("admin.deleteButton")}
                    </button>
                </div>
            </div>

            {/* The status control sends ONLY the status; nothing else about the
                ticket can be changed from here. */}
            <div className="card admin-status-bar">
                {STATUSES.map((status) => (
                    <button
                        key={status}
                        type="button"
                        className={`button ${STATUS_CLASS[status]}`}
                        disabled={ticket.status === status}
                        onClick={() => changeStatus(status)}
                    >
                        {t(STATUS_LABEL[status])}
                    </button>
                ))}
            </div>

            <TicketConversation messages={ticket.messages} showAuthorEmail />

            <form className="card feedback-form" onSubmit={sendAnswer}>
                <label className="settings-label" htmlFor="admin-display-name">
                    {t("admin.displayName")}
                </label>
                <input
                    id="admin-display-name"
                    className="feedback-input"
                    value={displayName}
                    onChange={(event) => setDisplayName(event.target.value)}
                    placeholder={t("feedback.supportBadge")}
                    maxLength={100}
                    disabled={busy}
                />
                <div className="feedback-attachments-hint">
                    {t("admin.displayNameHint")}
                </div>

                <label className="settings-label" htmlFor="admin-answer">
                    {t("admin.replyTitle")}
                </label>
                <MarkdownField
                    id="admin-answer"
                    value={answer}
                    onChange={setAnswer}
                    placeholder={t("feedback.replyPlaceholder")}
                    minHeight={160}
                    disabled={busy}
                />
                <div className="feedback-form-actions">
                    <button
                        type="submit"
                        className="button button-primary"
                        disabled={busy || answer.trim().length === 0}
                    >
                        <Send size={15} />{" "}
                        {busy ? t("feedback.sending") : t("admin.sendAnswer")}
                    </button>
                </div>
            </form>

            <ConfirmDialog
                open={confirming}
                title={t("admin.deleteTitle")}
                body={t("admin.deleteBody")}
                confirmLabel={t("admin.deleteConfirm")}
                cancelLabel={t("admin.deleteCancel")}
                busy={deleting}
                error={deleteError}
                onConfirm={remove}
                onClose={() => {
                    setConfirming(false);
                    setDeleteError(null);
                }}
            />
        </div>
    );
}
