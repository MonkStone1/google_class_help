import { Paperclip, Send, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { api, type ApiError } from "../api.ts";
import { MarkdownField } from "../components/MarkdownField.tsx";
import { useI18n } from "../i18n.ts";
import type { I18nKey } from "../i18n.ts";
import type { FeedbackCategory } from "../types.ts";

const CATEGORIES: FeedbackCategory[] = [
    "bug",
    "problem",
    "suggestion",
    "other",
];

const CATEGORY_LABEL: Record<FeedbackCategory, I18nKey> = {
    suggestion: "feedback.category.suggestion",
    bug: "feedback.category.bug",
    problem: "feedback.category.problem",
    other: "feedback.category.other",
};

/** Mirrors the server's per-file cap so the UI can warn before the upload. */
const MAX_FILE_BYTES = 5 * 1024 * 1024;
const MAX_FILES = 3;

/**
 * The create-ticket form (ADR-0035).
 *
 * No name and no e-mail field: identity comes from the session (§4.2 of the
 * feature plan), so asking for it again would only invite the reader to type
 * something that disagrees with their Google account. The copy says so.
 *
 * The client-side checks (subject present, body present) are a CONVENIENCE:
 * the server validates both and every limit, and a passing form is not a
 * guarantee — only the response is.
 */
export function FeedbackNew() {
    const { t } = useI18n();
    const navigate = useNavigate();
    const [category, setCategory] = useState<FeedbackCategory>("problem");
    const [subject, setSubject] = useState("");
    const [body, setBody] = useState("");
    const [files, setFiles] = useState<File[]>([]);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const addFiles = (incoming: FileList | null) => {
        if (!incoming) return;
        const next = [...files];
        for (const file of Array.from(incoming)) {
            // The server enforces both limits too; refusing here just saves
            // the user a rejected upload.
            if (next.length >= MAX_FILES) break;
            if (file.size > MAX_FILE_BYTES) {
                setError(t("feedback.attachmentsHint"));
                continue;
            }
            next.push(file);
        }
        setError(null);
        setFiles(next);
    };

    const submit = async (event: FormEvent) => {
        event.preventDefault();
        if (!subject.trim()) {
            setError(t("feedback.subjectRequired"));
            return;
        }
        if (!body.trim()) {
            setError(t("feedback.messageRequired"));
            return;
        }
        setBusy(true);
        setError(null);
        try {
            const ticket = await api.createTicket({
                category,
                subject: subject.trim(),
                body_markdown: body,
                files,
            });
            toast.success(t("feedback.created"));
            navigate(`/feedback/tickets/${ticket.id}`);
        } catch (err) {
            const apiError = err as ApiError;
            setError(apiError.message || t("feedback.loadFailed"));
            toast.error(apiError.message || t("feedback.loadFailed"));
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="page">
            <div className="page-header">
                <div>
                    <Link to="/feedback" className="back-link">
                        ← {t("feedback.title")}
                    </Link>
                    <h1>{t("feedback.newTitle")}</h1>
                    <div className="page-subtitle">{t("feedback.newLead")}</div>
                </div>
            </div>

            <form className="card feedback-form" onSubmit={submit}>
                <label className="settings-label" htmlFor="feedback-category">
                    {t("feedback.category")}
                </label>
                <select
                    id="feedback-category"
                    className="sort-select"
                    value={category}
                    onChange={(event) =>
                        setCategory(event.target.value as FeedbackCategory)
                    }
                    disabled={busy}
                >
                    {CATEGORIES.map((value) => (
                        <option key={value} value={value}>
                            {t(CATEGORY_LABEL[value])}
                        </option>
                    ))}
                </select>

                <label className="settings-label" htmlFor="feedback-subject">
                    {t("feedback.subject")}
                </label>
                <input
                    id="feedback-subject"
                    className="feedback-input"
                    value={subject}
                    onChange={(event) => setSubject(event.target.value)}
                    placeholder={t("feedback.subjectPlaceholder")}
                    maxLength={200}
                    disabled={busy}
                />

                <label className="settings-label" htmlFor="feedback-body">
                    {t("feedback.message")}
                </label>
                {/* The ONE Markdown editor, shared with replies (ADR-0035). */}
                <MarkdownField
                    id="feedback-body"
                    value={body}
                    onChange={setBody}
                    placeholder={t("feedback.messagePlaceholder")}
                    disabled={busy}
                />

                <div className="feedback-attachments-block">
                    <div className="settings-label">
                        {t("feedback.attachments")}
                    </div>
                    <div className="feedback-attachments-hint">
                        {t("feedback.attachmentsHint")}
                    </div>
                    {files.length > 0 ? (
                        <ul className="feedback-selected-files">
                            {files.map((file, index) => (
                                <li key={`${file.name}-${index}`}>
                                    <Paperclip size={14} />
                                    <span>{file.name}</span>
                                    <button
                                        type="button"
                                        className="icon-button"
                                        aria-label={t("feedback.removeFile", {
                                            name: file.name,
                                        })}
                                        onClick={() =>
                                            setFiles(
                                                files.filter(
                                                    (_, i) => i !== index,
                                                ),
                                            )
                                        }
                                        disabled={busy}
                                    >
                                        <X size={14} />
                                    </button>
                                </li>
                            ))}
                        </ul>
                    ) : null}
                    <label className="button feedback-file-picker">
                        <Paperclip size={15} /> {t("feedback.addFile")}
                        <input
                            type="file"
                            multiple
                            className="sr-only"
                            onChange={(event) => addFiles(event.target.files)}
                            disabled={busy}
                        />
                    </label>
                </div>

                {error ? (
                    <div className="alert alert-error" role="alert">
                        {error}
                    </div>
                ) : null}

                <div className="feedback-form-actions">
                    <Link to="/feedback/tickets" className="button">
                        {t("feedback.mineTitle")}
                    </Link>
                    <button
                        type="submit"
                        className="button button-primary"
                        disabled={busy}
                    >
                        <Send size={15} />{" "}
                        {busy ? t("feedback.submitting") : t("feedback.submit")}
                    </button>
                </div>
            </form>
        </div>
    );
}
