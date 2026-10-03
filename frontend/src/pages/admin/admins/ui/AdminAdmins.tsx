import { ShieldCheck, Trash2, UserPlus } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { api, type ApiError } from "../../../../shared/api/index.ts";
import { ConfirmDialog } from "../../../../shared/ui/index.ts";
import { EmptyState, SectionSkeleton } from "../../../../shared/ui/index.ts";
import { formatDateTimeShort, toLocalDate } from "../../../../shared/lib/index.ts";
import { useI18n } from "../../../../shared/i18n/index.ts";
import type { Administrator } from "../../../../shared/types/index.ts";
import { AddAdminModal } from "./AddAdminModal.tsx";

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