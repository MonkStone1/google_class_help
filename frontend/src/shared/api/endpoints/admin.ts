/**
 * The `/admin` console surface.
 *
 * Every ticket read here answers 403 to a regular user, and every registry call
 * answers 403 to a plain administrator: the UI hides what the API refuses
 * (ADR-0035, ADR-0036). The registry is Super-Admin-only because the Super
 * Admin has no row of their own — they are the `SUPER_ADMIN_EMAIL` value.
 *
 * The ticket list is filtered and paged by the SERVER (`total` arrives with the
 * page), so a growing queue is never shipped to the browser to be filtered
 * there.
 */

import { request, requestForm } from "../client.ts";
import type {
    AdminTicketDetail,
    AdminTicketPage,
    Administrator,
    FeedbackStats,
} from "../../types/index.ts";

/** Optional query parameters, omitted entirely rather than sent empty. */
function ticketQuery(params: {
    status?: string;
    category?: string;
    q?: string;
    limit?: number;
    offset?: number;
}): string {
    const query = new URLSearchParams();
    if (params.status) query.set("status", params.status);
    if (params.category) query.set("category", params.category);
    if (params.q) query.set("q", params.q);
    if (params.limit !== undefined) query.set("limit", String(params.limit));
    if (params.offset !== undefined) query.set("offset", String(params.offset));
    const suffix = query.toString();
    return suffix ? `?${suffix}` : "";
}

export const admin = {
    getAdminFeedbackStats: (signal?: AbortSignal) =>
        request<FeedbackStats>("/admin/feedback/stats", { signal }),
    getAdminTickets: (
        params: {
            status?: string;
            category?: string;
            q?: string;
            limit?: number;
            offset?: number;
        } = {},
        signal?: AbortSignal,
    ) =>
        request<AdminTicketPage>(
            `/admin/feedback/tickets${ticketQuery(params)}`,
            { signal },
        ),
    getAdminTicket: (ticketId: number, signal?: AbortSignal) =>
        request<AdminTicketDetail>(`/admin/feedback/tickets/${ticketId}`, {
            signal,
        }),
    replyToTicketAsAdmin: (
        ticketId: number,
        body: string,
        displayName: string | null,
    ) => {
        const form = new FormData();
        form.set("body_markdown", body);
        // The internal author is named explicitly; without it the reply would be
        // attributed to the ticket's owner.
        if (displayName) {
            form.set("display_name", displayName);
        }
        return requestForm<AdminTicketDetail>(
            `/admin/feedback/tickets/${ticketId}/messages`,
            form,
        );
    },
    setTicketStatus: (ticketId: number, status: string) =>
        request<AdminTicketDetail>(`/admin/feedback/tickets/${ticketId}`, {
            method: "PATCH",
            body: JSON.stringify({ status }),
        }),
    deleteTicket: (ticketId: number) =>
        request<{ ok: boolean }>(`/admin/feedback/tickets/${ticketId}`, {
            method: "DELETE",
        }),

    // Administrator registry (ADR-0036).
    getAdmins: (signal?: AbortSignal) =>
        request<Administrator[]>("/admin/admins", { signal }),
    createAdmin: (email: string) =>
        request<Administrator>("/admin/admins/", {
            method: "POST",
            body: JSON.stringify({ email }),
        }),
    deleteAdmin: (adminId: number) =>
        request<void>(`/admin/admins/${adminId}`, { method: "DELETE" }),
};