import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsProvider } from "../shared/settings/SettingsProvider.tsx";
import { DEFAULT_SETTINGS } from "../shared/types/index.ts";
import type { FeedbackTicketDetail, TicketMessage } from "../shared/types/index.ts";
import { FeedbackTicket } from "./FeedbackTicket.tsx";

vi.mock("sonner", () => ({
    toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

/** `vi.hoisted` because `vi.mock` is hoisted above every top-level statement. */
const api = vi.hoisted(() => ({
    getMyTicket: vi.fn(),
    replyToTicket: vi.fn(),
}));

vi.mock("../shared/api/index.ts", async () => {
    const actual = await vi.importActual<typeof import("../shared/api/index.ts")>(
        "../shared/api/index.ts",
    );
    return { ...actual, api };
});

function message(overrides: Partial<TicketMessage> = {}): TicketMessage {
    return {
        id: 1,
        author_type: "USER",
        display_name: "Alice",
        // Deliberately NOT the ticket subject: the page renders both, and
        // identical strings make a `getByText` ambiguous.
        body_markdown: "My average shows 10.",
        created_at: "2026-10-01T10:00:00",
        attachments: [],
        ...overrides,
    };
}

function ticket(
    overrides: Partial<FeedbackTicketDetail> = {},
): FeedbackTicketDetail {
    return {
        id: 42,
        category: "problem",
        subject: "Grades are wrong",
        status: "new",
        created_at: "2026-10-01T10:00:00",
        updated_at: "2026-10-01T10:00:00",
        messages: [message()],
        ...overrides,
    };
}

function renderTicket(detail: FeedbackTicketDetail = ticket()) {
    api.getMyTicket.mockResolvedValue(detail);
    localStorage.setItem(
        "gc-settings",
        JSON.stringify({ ...DEFAULT_SETTINGS, language: "en" }),
    );
    return render(
        <MemoryRouter initialEntries={["/feedback/tickets/42"]}>
            <SettingsProvider>
                <Routes>
                    <Route
                        path="/feedback/tickets/:id"
                        element={<FeedbackTicket />}
                    />
                </Routes>
            </SettingsProvider>
        </MemoryRouter>,
    );
}

/** The reply editor is the MarkdownField textarea, once the panel is open. */
function editor(): HTMLTextAreaElement {
    return screen.getByLabelText(/write your reply/i, {
        selector: "textarea",
    }) as HTMLTextAreaElement;
}

/**
 * The user's own ticket.
 *
 * п.5: the reply form moved ABOVE the conversation and starts COLLAPSED. The
 * reason is not tidiness — a reader opens a ticket to READ the answer, and a
 * full-height Markdown editor standing open pushed every message below the
 * fold. Three properties are load-bearing and asserted separately:
 *
 * 1. collapsed on arrival, so the conversation is what the page shows;
 * 2. opens on a click, with `aria-expanded` carrying the state;
 * 3. folds itself again after a successful send, so an empty editor is not left
 *    sitting under the message that was just added.
 */
describe("FeedbackTicket reply form", () => {
    beforeEach(() => {
        api.getMyTicket.mockReset();
        api.replyToTicket.mockReset();
    });

    it("starts collapsed, so the conversation is what the page shows", async () => {
        renderTicket();

        // The toggle is there and says so…
        const toggle = await screen.findByRole("button", { name: /reply/i });
        expect(toggle).toHaveAttribute("aria-expanded", "false");
        // …and the editor is not: no textarea has been mounted at all.
        expect(document.querySelector("textarea")).toBeNull();

        // The conversation itself rendered regardless.
        expect(screen.getByText("Grades are wrong")).toBeInTheDocument();
    });

    it("opens the form on a click and closes it again on a second one", async () => {
        renderTicket();
        const toggle = await screen.findByRole("button", { name: /reply/i });

        fireEvent.click(toggle);
        expect(toggle).toHaveAttribute("aria-expanded", "true");
        expect(editor()).toBeInTheDocument();

        fireEvent.click(toggle);
        expect(toggle).toHaveAttribute("aria-expanded", "false");
        expect(document.querySelector("textarea")).toBeNull();
    });

    it("sits above the conversation, so the answer is not pushed down", async () => {
        renderTicket();
        await screen.findByRole("button", { name: /reply/i });

        // Document order: the reply panel comes before the conversation.
        const replyPanel = document.querySelector(".feedback-reply");
        const conversation = document.querySelector(".ticket-conversation");
        expect(replyPanel).not.toBeNull();
        expect(conversation).not.toBeNull();
        expect(
            replyPanel!.compareDocumentPosition(conversation!) &
                Node.DOCUMENT_POSITION_FOLLOWING,
        ).toBeTruthy();
    });

    it("sends the reply and folds the form away", async () => {
        api.replyToTicket.mockResolvedValue(
            ticket({
                messages: [
                    message(),
                    message({
                        id: 2,
                        body_markdown: "My average shows 10.",
                    }),
                ],
            }),
        );

        renderTicket();
        const toggle = await screen.findByRole("button", { name: /reply/i });
        fireEvent.click(toggle);

        fireEvent.change(editor(), {
            target: { value: "My average shows 10." },
        });
        fireEvent.click(screen.getByRole("button", { name: /send reply/i }));

        await waitFor(() =>
            expect(api.replyToTicket).toHaveBeenCalledWith(
                42,
                "My average shows 10.",
            ),
        );
        // The panel folds itself: the reply is in the conversation now.
        await waitFor(() =>
            expect(toggle).toHaveAttribute("aria-expanded", "false"),
        );
        expect(document.querySelector("textarea")).toBeNull();
    });

    it("keeps the form open when the send fails, so the text is not lost", async () => {
        api.replyToTicket.mockRejectedValue(
            Object.assign(new Error("Rate limit reached."), { status: 429 }),
        );
        renderTicket();
        const toggle = await screen.findByRole("button", { name: /reply/i });
        fireEvent.click(toggle);

        fireEvent.change(editor(), { target: { value: "My average shows 10." } });
        fireEvent.click(screen.getByRole("button", { name: /send reply/i }));

        // Folding here would throw away a reply the user still has to send.
        await waitFor(() => expect(api.replyToTicket).toHaveBeenCalled());
        expect(toggle).toHaveAttribute("aria-expanded", "true");
    });
});
