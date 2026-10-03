import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";

import { useI18n } from "../../shared/i18n/index.ts";

type Props = {
    open: boolean;
    title: string;
    /** The irreversible part, spelled out before the buttons. */
    body: string;
    confirmLabel: string;
    cancelLabel: string;
    /** The dangerous action; rendered with `.button .button-danger`. */
    onConfirm: () => void;
    onClose: () => void;
    busy?: boolean;
    /** Rendered under the actions — a delete failure, for instance. */
    error?: string | null;
};

/**
 * The confirmation dialog of a destructive action (ADR-0035).
 *
 * A real React dialog, NOT `window.confirm`: this codebase has none, and a
 * native modal is neither styleable in the app's tokens nor accessible enough
 * for an irreversible action (the warning must be readable before the click,
 * not after).
 *
 * It follows the `AssignmentModal` pattern exactly — `modal-backdrop` +
 * `role="dialog"` + `aria-modal`, closable with Escape and by clicking the
 * backdrop — so the interaction is familiar and its focus handling is the one
 * the app already ships. The destructive button is visually separated from
 * Cancel and is the LAST thing a stray Enter press can reach.
 */
export function ConfirmDialog({
    open,
    title,
    body,
    confirmLabel,
    cancelLabel,
    onConfirm,
    onClose,
    busy = false,
    error = null,
}: Props) {
    const { t } = useI18n();

    // Escape closes — and closes ONLY when the action is not in flight, so a
    // half-sent delete cannot be abandoned by a stray key.
    useEffect(() => {
        if (!open || busy) return;
        const onKey = (event: KeyboardEvent) => {
            if (event.key === "Escape") {
                onClose();
            }
        };
        document.addEventListener("keydown", onKey);
        return () => document.removeEventListener("keydown", onKey);
    }, [open, busy, onClose]);

    if (!open) {
        return null;
    }

    return (
        <div className="modal-backdrop" role="presentation" onClick={onClose}>
            <div
                className="modal confirm-dialog"
                role="alertdialog"
                aria-modal="true"
                aria-labelledby="confirm-dialog-title"
                aria-describedby="confirm-dialog-body"
                onClick={(event) => event.stopPropagation()}
            >
                <div className="confirm-dialog-icon" aria-hidden="true">
                    <AlertTriangle size={22} />
                </div>
                <h2 id="confirm-dialog-title">{title}</h2>
                <p id="confirm-dialog-body">{body}</p>
                {error ? (
                    <div className="alert alert-error" role="alert">
                        {error}
                    </div>
                ) : null}
                <div className="modal-actions confirm-dialog-actions">
                    <button
                        type="button"
                        className="button"
                        onClick={onClose}
                        disabled={busy}
                    >
                        {cancelLabel}
                    </button>
                    <button
                        type="button"
                        className="button button-danger"
                        onClick={onConfirm}
                        disabled={busy}
                    >
                        {busy ? t("feedback.sending") : confirmLabel}
                    </button>
                </div>
            </div>
        </div>
    );
}
