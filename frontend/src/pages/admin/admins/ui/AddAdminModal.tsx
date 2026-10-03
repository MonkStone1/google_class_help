import { useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { toast } from "sonner";

import { api } from "../../../../shared/api/index.ts";
import type { ApiError } from "../../../../shared/api/index.ts";
import { useI18n } from "../../../../shared/i18n/index.ts";

/**
 * The add form — an e-mail field and nothing else.
 *
 * It follows the `AssignmentModal` pattern (`modal-backdrop` + `modal` +
 * `modal-header` + `modal-actions`) so the interaction is the one the app
 * already ships. The server's own 409/422 message is rendered here rather than
 * only toasted: the user must see WHICH address was refused, in the place they
 * can correct it.
 */
export function AddAdminModal({
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