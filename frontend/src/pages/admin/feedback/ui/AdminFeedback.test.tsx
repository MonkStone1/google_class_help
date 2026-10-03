import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsProvider } from "../../../../shared/settings/index.ts";
import { DEFAULT_SETTINGS } from "../../../../shared/types/index.ts";
import type { AdminTicket, AdminTicketPage } from "../../../../shared/types/index.ts";
import { AdminFeedback } from "./AdminFeedback.tsx";

/**
 * `vi.hoisted` because `vi.mock` is hoisted above every top-level statement: a
 * plain `const api = …` would not exist yet when the factory runs. The same
 * shape `AdminAdmins.test.tsx` uses.
 */
const api = vi.hoisted(() => ({
    getAdminTickets: vi.fn(),
}));

vi.mock("../../../../shared/api/index.ts", async () => {
    const actual = await vi.importActual<typeof import("../../../../shared/api/index.ts")>(
        "../../../../shared/api/index.ts",
    );
    return { ...actual, api };
});

function ticket(overrides: Partial<AdminTicket> = {}): AdminTicket {
    return {
        id: 7,
        category: "problem",
        subject: "Grades are wrong",
        status: "new",
        user_id: 1,
        user_name: "Alice",
        user_email: "alice@example.com",
        message_count: 1,
        created_at: "2026-10-01T10:00:00",
        updated_at: "2026-10-01T10:00:00",
        ...overrides,
    };
}

function page(items: AdminTicket[]): AdminTicketPage {
    return { items, total: items.length, limit: 25, offset: 0 };
}

function renderList() {
    localStorage.setItem(
        "gc-settings",
        JSON.stringify({ ...DEFAULT_SETTINGS, language: "en" }),
    );
    return render(
        <MemoryRouter initialEntries={["/admin/feedback"]}>
            <SettingsProvider>
                <AdminFeedback />
            </SettingsProvider>
        </MemoryRouter>,
    );
}

/**
 * The console ticket list.
 *
 * The headline case is the DUPLICATION this page used to ship: the very same
 * `.ticket-list` block appeared twice in `AdminFeedback.tsx` under one
 * `page.items.length > 0` condition, so every ticket was painted as two
 * identical rows that re-rendered together. An administrator read that as
 * "two copies that update in parallel", and it happened on this tab only —
 * `AdminDashboard.tsx` renders its recent list once.
 *
 * Counting the rows per ticket is therefore the assertion that matters: the
 * request is irrelevant, the server paged once and both copies read it.
 */
describe("AdminFeedback ticket list", () => {
    beforeEach(() => {
        api.getAdminTickets.mockReset();
    });

    it("renders each ticket exactly once, not twice", async () => {
        api.getAdminTickets.mockResolvedValue(page([ticket()]));
        const { container } = renderList();

        // One ticket → one row.
        const rows = await screen.findAllByRole("listitem");
        expect(rows).toHaveLength(1);

        // The subject itself appears once. `.ticket-list-subject` is a div, not a
        // heading, so this is read off the DOM rather than by role.
        expect(
            container.querySelectorAll(".ticket-list-subject"),
        ).toHaveLength(1);
        expect(screen.getAllByText("Grades are wrong")).toHaveLength(1);

        // Exactly one list of tickets is mounted — the duplicated block rendered
        // a SECOND `<ul class="ticket-list">` right above the error banner.
        expect(container.querySelectorAll(".ticket-list")).toHaveLength(1);
        expect(
            screen.getAllByRole("link", { name: /Ticket #7/ }),
        ).toHaveLength(1);
    });

    it("keeps one row per ticket when the page holds several", async () => {
        api.getAdminTickets.mockResolvedValue(
            page([
                ticket({ id: 7, subject: "First" }),
                ticket({ id: 8, subject: "Second" }),
                ticket({ id: 9, subject: "Third" }),
            ]),
        );
        const { container } = renderList();

        // Three tickets, three rows — a duplicated block would make this six.
        await waitFor(() =>
            expect(container.querySelectorAll(".ticket-list-item")).toHaveLength(
                3,
            ),
        );
        expect(
            container.querySelectorAll(".ticket-list-subject"),
        ).toHaveLength(3);
    });

    it("paints one row even though the loader refetches", async () => {
        // The request COUNT is deliberately NOT asserted here. `useI18n` builds
        // a new `t` on every render and this effect lists `t` in its deps, so
        // the loader refetches after it re-renders — `AdminAdmins.tsx` documents
        // that trap and deliberately routes around it, this page does not. That
        // is a separate question from the duplication, and asserting a call
        // count would pin the current refetch behaviour rather than the fix.
        //
        // What matters: a second render of the list would double the ROWS
        // without adding a single request, so the row count — not the request
        // count — is the signal that catches the defect.
        api.getAdminTickets.mockResolvedValue(page([ticket()]));
        const { container } = renderList();

        await waitFor(() =>
            expect(container.querySelectorAll(".ticket-list-item")).toHaveLength(
                1,
            ),
        );
        expect(screen.getAllByText("Grades are wrong")).toHaveLength(1);
    });
});