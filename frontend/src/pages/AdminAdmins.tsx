import { ShieldCheck, Trash2, UserPlus, X } from "lucide-react";
import {
    useCallback,
    useEffect,
    useRef,
    useState,
    type FormEvent,
} from "react";
import { toast } from "sonner";

import { api, type ApiError } from "../shared/api/index.ts";
import { ConfirmDialog } from "../components/ConfirmDialog.tsx";
import { EmptyState, SectionSkeleton } from "../components/Skeletons.tsx";
import { formatDateTimeShort, toLocalDate } from "../shared/lib/dates.ts";
import { useI18n } from "../shared/i18n/index.ts";
import type { Administrator } from "../shared/types/index.ts";

/**
 * The administrator registry — Super Admin only (ADR-0036).
 *
 * Four decisions are load-bearing here:
 *
 * - **One field, the e-mail.** There is no name input: the display name is
 *   derived by the server from the stored address, so a second copy of the
 *   identity cannot exist to drift (D8).
 * - **The server's refusal is shown, never swallowed.** A duplicate (409) and a
 *   malformed address (422) are answered with the server's own message inside the
 *   modal — the user needs to know WHICH address was refused, and the button
 *   stays disabled only while the request is in flight.
 * - **Delete lives in the row it removes.** There is no global delete control:
 *   the irreversible action is always next to the thing it would destroy, and it
 *   is impossible to press without the confirmation dialog first.
 * - **The list is re-read after every change.** The server owns the registry, so
 *   a refresh — not a local guess — is what makes a new row or a removed one
 *   visible.
 */
export function AdminAdmins() {
    const { t } = useI18n();
    const [admins, setAdmins] = useState<Administrator[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [adding, setAdding] = useState(false);
    const [pending, setPending] = useState<Administrator | null>(null);
    const [deleting, setDeleting] = useState(false);
    const [deleteError, setDeleteError] = useState<string | null>(null);

    // `useI18n` builds a NEW `t` on every render, so putting it in a dependency
    // list would make this loader change identity forever — and an effect
    // depending on it would re-fetch in a loop. The translator is read through a
    // ref instead: it is only needed for the fallback message, and a ref keeps
    // `load` stable so the list is fetched once per mount (and once per refresh).
    const tRef = useRef(t);
    tRef.current = t;

    const load = useCallback((signal?: AbortSignal) => {
        setError(null);
        return api
            .getAdmins(signal)
            .then(setAdmins)
            .catch((err: unknown) => {
                const apiError = err as ApiError;
                if (apiError.status === 0) return;
                setAdmins([]);
                setError(
                    apiError.message || tRef.current("admin.adminsLoadFailed"),
                );
            });
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        load(controller.signal);
        return () => controller.abort();
    }, [load]);

    const remove = async () => {
        if (!pending) return;
        setDeleting(true);
        setDeleteError(null);
        try {
            await api.deleteAdmin(pending.id);
            toast.success(t("admin.adminsRemoved"));
            setPending(null);
            await load();
        } catch (err) {
            const apiError = err as ApiError;
            // Shown INSIDE the dialog, so the warning stays readable while the
            // user decides what to do next.
            setDeleteError(apiError.message || t("admin.adminsDeleteFailed"));
        } finally {
            setDeleting(false);
        }
    };

    return (
        <div className="page">
            <div className="page-header">
                <div>
                    <h1>{t("admin.adminsTitle")}</h1>
                </div>
                <div className="page-header-actions">
                    <button
                        type="button"
                        className="button button-primary"
                        onClick={() => setAdding(true)}
                    >
                        <UserPlus size={16} /> {t("admin.adminsAdd")}
                    </button>
                </div>
            </div>

            {error ? (
                <div className="alert alert-error" role="alert">
                    {error}
                </div>
            ) : null}

            {admins === null ? (
                <SectionSkeleton rows={2} />
            ) : admins.length === 0 && !error ? (
                <EmptyState
                    icon={<ShieldCheck size={28} />}
                    title={t("admin.adminsEmpty")}
                    subtitle={t("admin.adminsEmptyHint")}
                />
            ) : admins.length > 0 ? (
                <div className="table-wrap admin-admins-table">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>{t("admin.adminsEmail")}</th>
                                <th>{t("admin.adminsName")}</th>
                                <th>{t("admin.adminsAddedAt")}</th>
                                <th aria-label={t("admin.adminsActions")} />
                            </tr>
                        </thead>
                        <tbody>
                            {admins.map((row) => (
                                <tr key={row.id}>
                                    <td>{row.email}</td>
                                    {/* Derived by the server from the address. */}
                                    <td>{row.name}</td>
                                    <td>
                                        {formatDateTimeShort(
                                            toLocalDate(row.created_at),
                                        )}
                                    </td>
                                    <td className="admin-admins-actions">
                                        <button
                                            type="button"
                                            className="button button-danger"
                                            onClick={() => {
                                                setDeleteError(null);
                                                setPending(row);
                                            }}
                                        >
                                            <Trash2 size={15} />{" "}
                                            {t("admin.adminsDelete")}
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            ) : null}

            {adding ? (
                <AddAdminModal
                    onClose={() => setAdding(false)}
                    onAdded={async () => {
                        setAdding(false);
                        await load();
                    }}
                />
            ) : null}

            <ConfirmDialog
                open={pending !== null}
                title={t("admin.adminsDeleteTitle")}
                body={
                    pending
                        ? t("admin.adminsDeleteBody", { email: pending.email })
                        : ""
                }
                confirmLabel={t("admin.adminsDeleteConfirm")}
                cancelLabel={t("admin.adminsDeleteCancel")}
                onConfirm={remove}
                onClose={() => {
                    if (!deleting) setPending(null);
                }}
                busy={deleting}
                error={deleteError}
            />
        </div>
    );
}

/**
 * The add form — an e-mail field and nothing else.
 *
 * It follows the `AssignmentModal` pattern (`modal-backdrop` + `modal` +
 * `modal-header` + `modal-actions`) so the interaction is the one the app
 * already ships. The server's own 409/422 message is rendered here rather than
 * only toasted: the user must see WHICH address was refused, in the place they
 * can correct it.
 */
function AddAdminModal({
    onClose,
    onAdded,
}: {
    onClose: () => void;
    onAdded: () => Promise<void> | void;
}) {
    const { t } = useI18n();
    const [email, setEmail] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const submit = async (event: FormEvent) => {
        event.preventDefault();
        if (!email.trim()) return;
        setBusy(true);
        setError(null);
        try {
            await api.createAdmin(email.trim());
            toast.success(t("admin.adminsAdded"));
            await onAdded();
        } catch (err) {
            const apiError = err as ApiError;
            // 422 (malformed) and 409 (duplicate, or the Super Admin) are both
            // explained here — never swallowed into a generic failure.
            setError(apiError.message || t("admin.adminsAddFailed"));
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="modal-backdrop" role="presentation" onClick={onClose}>
            <div
                className="modal"
                role="dialog"
                aria-modal="true"
                aria-label={t("admin.adminsAdd")}
                onClick={(event) => event.stopPropagation()}
            >
                <div className="modal-header">
                    <div>
                        <h2>{t("admin.adminsAdd")}</h2>
                    </div>
                    <button
                        type="button"
                        className="icon-button"
                        onClick={onClose}
                        aria-label={t("modal.close")}
                        disabled={busy}
                    >
                        <X size={18} />
                    </button>
                </div>

                <form className="modal-form" onSubmit={submit}>
                    {/*
                      `field`/`field-label`/`input` were used here and exist in
                      NO stylesheet, so the browser painted a raw control and
                      the inline `<label>` left the caption glued to it. The
                      classes below are the ones the search box on
                      `/admin/feedback` already uses, so the same field looks
                      the same in both places.
                    */}
                    <label className="settings-label" htmlFor="admin-email">
                        {t("admin.adminsEmail")}
                    </label>
                    <input
                        id="admin-email"
                        className="feedback-input"
                        type="email"
                        required
                        autoFocus
                        value={email}
                        disabled={busy}
                        onChange={(event) => setEmail(event.target.value)}
                    />
                    <p className="admin-admins-hint">
                        {t("admin.adminsEmailHint")}
                    </p>

                    {error ? (
                        <div className="alert alert-error" role="alert">
                            {error}
                        </div>
                    ) : null}

                    <div className="modal-actions">
                        <button
                            type="button"
                            className="button"
                            onClick={onClose}
                            disabled={busy}
                        >
                            {t("admin.adminsDeleteCancel")}
                        </button>
                        <button
                            type="submit"
                            className="button button-primary"
                            disabled={busy || !email.trim()}
                        >
                            {busy
                                ? t("feedback.sending")
                                : t("admin.adminsAdd")}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}