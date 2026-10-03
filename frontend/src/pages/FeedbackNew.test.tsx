import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../shared/api/index.ts";
import { SettingsProvider } from "../shared/settings/SettingsProvider.tsx";
import { FeedbackNew } from "./FeedbackNew.tsx";

vi.mock("sonner", () => ({
    toast: {
        success: vi.fn(),
        error: vi.fn(),
        info: vi.fn(),
        warning: vi.fn(),
    },
}));

function renderForm() {
    return render(
        <MemoryRouter initialEntries={["/feedback/new"]}>
            <SettingsProvider>
                <Routes>
                    <Route path="/feedback/new" element={<FeedbackNew />} />
                    <Route
                        path="/feedback/tickets/:id"
                        element={<div>ticket detail</div>}
                    />
                </Routes>
            </SettingsProvider>
        </MemoryRouter>,
    );
}

describe("FeedbackNew", () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it("has no name or e-mail input", () => {
        // Identity comes from the session (ADR-0035 §4.2): asking again would only
        // invite the reader to type something that disagrees with their account.
        renderForm();
        expect(screen.queryByLabelText(/name/i)).toBeNull();
        expect(screen.queryByLabelText(/e-mail|email|почт/i)).toBeNull();
    });

    it("refuses an empty subject before calling the API", () => {
        const create = vi.spyOn(api, "createTicket");
        renderForm();

        fireEvent.click(screen.getByRole("button", { name: /Send ticket/i }));

        expect(create).not.toHaveBeenCalled();
        expect(screen.getByRole("alert")).toHaveTextContent(/subject/i);
    });

    it("refuses an empty body before calling the API", () => {
        const create = vi.spyOn(api, "createTicket");
        renderForm();

        fireEvent.change(screen.getByLabelText(/subject/i), {
            target: { value: "Grades are wrong" },
        });
        fireEvent.click(screen.getByRole("button", { name: /Send ticket/i }));

        expect(create).not.toHaveBeenCalled();
        expect(screen.getByRole("alert")).toHaveTextContent(/describe/i);
    });

    it("sends the ticket and navigates to the conversation", async () => {
        const created = {
            id: 42,
            category: "problem" as const,
            subject: "Grades are wrong",
            status: "new" as const,
            created_at: "2026-10-01T10:00:00",
            updated_at: "2026-10-01T10:00:00",
            messages: [],
        };
        const create = vi.spyOn(api, "createTicket").mockResolvedValue(created);
        renderForm();

        fireEvent.change(screen.getByLabelText(/subject/i), {
            target: { value: "Grades are wrong" },
        });
        fireEvent.change(
            screen.getByLabelText(/message/i, { selector: "textarea" }),
            { target: { value: "My average shows 10." } },
        );
        fireEvent.click(screen.getByRole("button", { name: /Send ticket/i }));

        expect(create).toHaveBeenCalledTimes(1);
        expect(create.mock.calls[0][0]).toMatchObject({
            subject: "Grades are wrong",
            body_markdown: "My average shows 10.",
        });
        // No author fields ever leave the browser.
        expect(create.mock.calls[0][0]).not.toHaveProperty("display_name");
        expect(create.mock.calls[0][0]).not.toHaveProperty("user_id");
        expect(await screen.findByText("ticket detail")).toBeInTheDocument();
    });

    it("reports a rejected ticket instead of failing silently", async () => {
        vi.spyOn(api, "createTicket").mockRejectedValue(
            Object.assign(new Error("File type is not allowed."), {
                status: 422,
            }),
        );
        renderForm();

        fireEvent.change(screen.getByLabelText(/subject/i), {
            target: { value: "With a bad file" },
        });
        fireEvent.change(
            screen.getByLabelText(/message/i, { selector: "textarea" }),
            { target: { value: "See attachment." } },
        );
        fireEvent.click(screen.getByRole("button", { name: /Send ticket/i }));

        expect(await screen.findByRole("alert")).toHaveTextContent(
            /File type is not allowed/,
        );
    });
});
