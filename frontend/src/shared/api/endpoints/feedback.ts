/**
 * The caller's own tickets (ADR-0035).
 *
 * This is the USER surface only; the console's reads live in `admin.ts` and go
 * to separate server routes, so a caller can never "upgrade" a request by
 * flipping a local option.
 *
 * Creation and reply always go out as multipart. That is the shape the form
 * produces even with zero files, so attachments are purely additive: no second
 * URL and no content-type branch on the client.
 */

import { request, requestForm } from "../client.ts";
import type {
    FeedbackCategory,
    FeedbackTicket,
    FeedbackTicketDetail,
} from "../../types/index.ts";

/** Appends the optional attachments; zero files is a valid body. */
function withFiles(form: FormData, files: readonly File[] | undefined): void {
    for (const file of files ?? []) {
        form.append("files", file);
    }
}

export const feedback = {
    getMyTickets: (signal?: AbortSignal) =>
        request<FeedbackTicket[]>("/feedback/tickets", { signal }),
    getMyTicket: (ticketId: number, signal?: AbortSignal) =>
        request<FeedbackTicketDetail>(`/feedback/tickets/${ticketId}`, {
            signal,
        }),
    createTicket: (input: {
        category: FeedbackCategory;
        subject: string;
        body_markdown: string;
        files?: File[];
    }) => {
        const form = new FormData();
        form.set("category", input.category);
        form.set("subject", input.subject);
        form.set("body_markdown", input.body_markdown);
        withFiles(form, input.files);
        return requestForm<FeedbackTicketDetail>("/feedback/tickets", form);
    },
    replyToTicket: (ticketId: number, body: string, files: File[] = []) => {
        const form = new FormData();
        form.set("body_markdown", body);
        withFiles(form, files);
        return requestForm<FeedbackTicketDetail>(
            `/feedback/tickets/${ticketId}/messages`,
            form,
        );
    },
};