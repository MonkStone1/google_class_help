import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { SettingsProvider } from "../../shared/settings/index.ts";
import { Markdown } from "./Markdown.tsx";

/**
 * Markdown is UNTRUSTED INPUT (ADR-0035): the backend stores the source
 * verbatim, so the sanitizer is the ONLY thing standing between a ticket body
 * and the app's own origin. These cases are the classic stored-XSS payloads;
 * each must survive as TEXT, never as live markup.
 */
function renderMarkdown(source: string) {
    const { container } = render(
        <MemoryRouter>
            <SettingsProvider>
                <Markdown>{source}</Markdown>
            </SettingsProvider>
        </MemoryRouter>,
    );
    return container;
}

describe("Markdown sanitization", () => {
    it("never renders a script element from a stored body", async () => {
        const container = renderMarkdown("<script>alert(1)</script>");
        await waitFor(() =>
            expect(container.querySelector(".markdown-body")).not.toBeNull(),
        );
        // rehype-sanitize drops the whole node INCLUDING its text, so neither the
        // element nor its payload can end up in the DOM.
        expect(container.querySelector("script")).toBeNull();
        expect(container.innerHTML).not.toContain("alert(1)");
    });

    it("keeps ordinary text intact next to a stripped script", () => {
        const container = renderMarkdown(
            "before <script>alert(1)</script> after",
        );
        expect(container.textContent).toContain("before");
        expect(container.textContent).toContain("after");
        expect(container.querySelector("script")).toBeNull();
    });

    it("strips an inline event handler", () => {
        const container = renderMarkdown('<img src="x" onerror="alert(1)">');
        const image = container.querySelector("img");
        expect(image?.getAttribute("onerror")).toBeNull();
    });

    it("drops a javascript: link", () => {
        const container = renderMarkdown("[click](javascript:alert(1))");
        const links = Array.from(container.querySelectorAll("a"));
        for (const link of links) {
            const href = link.getAttribute("href") ?? "";
            expect(href.startsWith("javascript:")).toBe(false);
        }
    });

    it("drops an iframe", () => {
        const container = renderMarkdown(
            "<iframe src='https://evil.example'></iframe>",
        );
        expect(container.querySelector("iframe")).toBeNull();
    });

    it("drops an svg with an inline handler", () => {
        const container = renderMarkdown("<svg/onload=alert(1)>");
        expect(container.querySelector("svg")).toBeNull();
    });

    it("still renders ordinary Markdown", () => {
        renderMarkdown("**bold** and `code`");
        expect(screen.getByText("bold")).toBeInTheDocument();
    });
});
