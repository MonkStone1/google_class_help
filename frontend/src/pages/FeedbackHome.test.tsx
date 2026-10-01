import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { SettingsProvider } from "../context/SettingsContext.tsx";
import { FeedbackHome } from "./FeedbackHome.tsx";

/**
 * The entry page must offer BOTH choices, not open the form directly: "report
 * something" and "read what I reported" are different intents, and dropping a
 * visitor straight into the editor makes the second one unreachable.
 */
function renderHome() {
    return render(
        <MemoryRouter>
            <SettingsProvider>
                <FeedbackHome />
            </SettingsProvider>
        </MemoryRouter>,
    );
}

describe("Feedback entry", () => {
    it("offers both choices with their own links", () => {
        renderHome();
        const create = screen.getByRole("link", { name: /Create a ticket/ });
        const mine = screen.getByRole("link", { name: /My tickets/ });
        expect(create).toHaveAttribute("href", "/feedback/new");
        expect(mine).toHaveAttribute("href", "/feedback/tickets");
    });

    it("explains what each choice leads to", () => {
        renderHome();
        // The copy is what makes the difference obvious; without it the two cards
        // would be two equally vague buttons.
        expect(
            screen.getByText(/answer will appear here/i),
        ).toBeInTheDocument();
        expect(
            screen.getByText(/every reply in one place/i),
        ).toBeInTheDocument();
    });
});
