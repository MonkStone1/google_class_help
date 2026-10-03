import { Download } from "lucide-react";

import { useI18n } from "../../../shared/i18n/index.ts";
import type { TicketAttachment } from "../../../shared/types/index.ts";

/**
 * The files of one message (ADR-0035).
 *
 * A download link to the authorized API endpoint — never a direct URL into the
 * volume. There is no static mount for uploads in this application, so this is
 * the only way to fetch a file, and it is exactly the path that checks that the
 * caller owns the ticket (or is an administrator).
 */
export function AttachmentList({
    attachments,
}: {
    attachments: TicketAttachment[];
}) {
    const { t } = useI18n();
    if (attachments.length === 0) {
        return null;
    }
    return (
        <ul className="ticket-attachments">
            {attachments.map((file) => (
                <li key={file.id}>
                    <a
                        className="ticket-attachment"
                        href={`/api/feedback/attachments/${file.id}`}
                        // `download` keeps the browser from ever rendering an upload in the
                        // app's own origin; the response already says `attachment`.
                        download={file.original_name}
                    >
                        <Download size={14} />
                        <span className="ticket-attachment-name">
                            {file.original_name}
                        </span>
                        <span className="ticket-attachment-size">
                            {Math.max(1, Math.round(file.size_bytes / 1024))} KB
                        </span>
                    </a>
                    <span className="sr-only">
                        {t("feedback.downloadFile", {
                            name: file.original_name,
                        })}
                    </span>
                </li>
            ))}
        </ul>
    );
}
