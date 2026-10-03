import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { SettingsProvider } from "../../../shared/settings/index.ts";
import type { TicketMessage } from "../../../shared/types/index.ts";
import {
    TicketConversation,
    TicketMessage as TicketMessageView,
} from "./TicketMessage.tsx";

function message(overrides: Partial<TicketMessage> = {}): TicketMessage {
    return {
        id: 1,
        author_type: "USER",
        display_name: "Alice",
        body_markdown: "Hello",
        created_at: "2026-10-01T10:00:00",
        attachments: [],
        ...overrides,
    };
}

function renderConversation(messages: TicketMessage[]) {
    return render(
        <MemoryRouter>
            <SettingsProvider>
                <TicketConversation messages={messages} />
            </SettingsProvider>
        </MemoryRouter>,
    );
}

describe("TicketMessage", () => {
    it("renders a USER message on the neutral surface", () => {
        const { container } = renderConversation([
            message({ author_type: "USER", display_name: "Alice" }),
        ]);
        const article = container.querySelector("article");
        expect(article?.className).toContain("ticket-message-user");
        expect(article?.className).not.toContain("ticket-message-admin");
        expect(screen.getByText("Alice")).toBeInTheDocument();
    });

    it("renders an ADMIN message with a distinct class and a Support badge", () => {
        // The distinction must be VISIBLE, not just present in the data: a support
        // thread where the answer looks like the question is not readable.
        const { container } = renderConversation([
            message({
                author_type: "ADMIN",
                display_name: "GoogleClassHelp Support",
            }),
        ]);
        const article = container.querySelector("article");
        expect(article?.className).toContain("ticket-message-admin");
        expect(article?.className).not.toContain("ticket-message-user");
        expect(screen.getByText("Support")).toBeInTheDocument();
    });

    it("branches on author_type, not on the name", () => {
        // Two administrators may publish under the SAME public name; styling on the
        // name would put the badge on the wrong message.
        const { container } = renderConversation([
            message({ id: 1, author_type: "USER", display_name: "Support" }),
            message({ id: 2, author_type: "ADMIN", display_name: "Support" }),
        ]);
        const classes = Array.from(container.querySelectorAll("article")).map(
            (node) =>
                node.className.includes("ticket-message-admin")
                    ? "ADMIN"
                    : "USER",
        );
        expect(classes).toEqual(["USER", "ADMIN"]);
    });

    it("renders attachments as download links to the authorized endpoint", () => {
        renderConversation([
            message({
                attachments: [
                    {
                        id: 7,
                        original_name: "notes.txt",
                        content_type: "text/plain",
                        size_bytes: 2048,
                        created_at: "2026-10-01T10:00:00",
                    },
                ],
            }),
        ]);
        const link = screen.getByRole("link", { name: /notes\.txt/ });
        expect(link).toHaveAttribute("href", "/api/feedback/attachments/7");
        // Never a URL into the volume: there is no static mount for uploads.
        expect(link.getAttribute("href")).not.toContain("feedback/1");
    });

    it("keeps the conversation in the order the server sent it", () => {
        renderConversation([
            message({ id: 1, body_markdown: "First" }),
            message({ id: 2, body_markdown: "Second" }),
        ]);
        const articles = document.querySelectorAll("article");
        expect(articles[0].textContent).toContain("First");
        expect(articles[1].textContent).toContain("Second");
    });

    it("renders a single message through the component directly", () => {
        render(
            <MemoryRouter>
                <SettingsProvider>
                    <TicketMessageView
                        message={message({ author_type: "ADMIN" })}
                    />
                </SettingsProvider>
            </MemoryRouter>,
        );
        expect(screen.getByText("Support")).toBeInTheDocument();
    });
});
