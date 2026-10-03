import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminAdmins } from "./AdminAdmins.tsx";
import { SettingsProvider } from "../shared/settings/SettingsProvider.tsx";
import type { Administrator } from "../shared/types/index.ts";

/**
 * `vi.hoisted` because `vi.mock` is hoisted above every top-level statement:
 * a plain `const api = …` would not exist yet when the factory runs. The same
 * shape the other test files in this project use for their mocked contexts.
 */
const api = vi.hoisted(() => ({
    getAdmins: vi.fn(),
    createAdmin: vi.fn(),
    deleteAdmin: vi.fn(),
}));

vi.mock("../shared/api/index.ts", async () => {
    const actual = await vi.importActual<typeof import("../shared/api/index.ts")>(
        "../shared/api/index.ts",
    );
    return { ...actual, api };
});

const BOSS: Administrator = {
    id: 1,
    email: "boss@example.com",
    // Derived by the server from the address (D8) — the UI only renders it.
    name: "Boss",
    created_at: "2026-10-01T09:30:00",
};

function renderPage() {
    return render(
        <MemoryRouter initialEntries={["/admin/admins"]}>
            {/* Real providers, not mocked contexts: `useI18n` reads the settings
                store, and the page's whole job is what it renders. */}
            <SettingsProvider>
                <AdminAdmins />
            </SettingsProvider>
        </MemoryRouter>,
    );
}

/**
 * The registry screen (ADR-0036): the generated name and the date are rendered
 * from the wire shape, the add form has exactly ONE field, the server's refusal
 * is shown instead of swallowed, and no irreversible delete happens without the
 * confirmation dialog.
 */
describe("AdminAdmins", () => {
    beforeEach(() => {
        api.getAdmins.mockReset();
        api.createAdmin.mockReset();
        api.deleteAdmin.mockReset();
        api.getAdmins.mockResolvedValue([BOSS]);
    });

    it("renders the address, the generated name and the date", async () => {
        renderPage();
        expect(await screen.findByText("boss@example.com")).toBeInTheDocument();
        // The name is the server-derived one (D8) — rendered, never asked for.
        expect(screen.getByText("Boss")).toBeInTheDocument();
        // The date cell goes through the shared date helpers. Its exact text is
        // locale-dependent (`formatDateTimeShort` omits the year for the current
        // one), so assert the COLUMN is filled rather than a fixed string.
        const row = screen.getByText("boss@example.com").closest("tr");
        const cells = row ? row.querySelectorAll("td") : [];
        expect(cells).toHaveLength(4);
        expect((cells[2]?.textContent ?? "").trim()).not.toBe("");
    });

    it("opens the add form with an e-mail field and no name field", async () => {
        renderPage();
        await screen.findByText("boss@example.com");

        fireEvent.click(
            screen.getByRole("button", { name: /add administrator/i }),
        );

        const email = await screen.findByLabelText(/email/i);
        expect(email).toHaveAttribute("type", "email");
        expect(email).toBeRequired();
        // D8: the display name is generated, so there is no name input at all.
        expect(screen.queryByLabelText(/^name$/i)).toBeNull();
        expect(screen.getAllByLabelText(/email/i)).toHaveLength(1);
    });

    it("shows the server's message when the address is a duplicate", async () => {
        api.createAdmin.mockRejectedValue(
            Object.assign(new Error("This account is already an administrator."), {
                status: 409,
            }),
        );
        renderPage();
        await screen.findByText("boss@example.com");

        fireEvent.click(
            screen.getByRole("button", { name: /add administrator/i }),
        );
        const email = await screen.findByLabelText(/email/i);
        fireEvent.change(email, { target: { value: "boss@example.com" } });
        fireEvent.submit(email.closest("form") as HTMLFormElement);

        // The 409 detail is rendered INSIDE the modal, not swallowed into a toast.
        expect(
            await screen.findByText("This account is already an administrator."),
        ).toBeInTheDocument();
        // And the list was not refreshed behind the user's back.
        expect(api.getAdmins).toHaveBeenCalledTimes(1);
    });

    it("confirms before deleting, then refreshes the table", async () => {
        api.deleteAdmin.mockResolvedValue(undefined);
        api.getAdmins.mockResolvedValueOnce([BOSS]).mockResolvedValueOnce([]);
        renderPage();
        await screen.findByText("boss@example.com");

        fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));

        // The dialog names the address and states the consequence.
        expect(
            await screen.findByText(/remove administrator\?/i),
        ).toBeInTheDocument();
        expect(
            screen.getByText(/boss@example\.com.*lose administrator access/i),
        ).toBeInTheDocument();
        // Nothing was deleted just by asking.
        expect(api.deleteAdmin).not.toHaveBeenCalled();

        fireEvent.click(
            screen.getByRole("button", { name: /remove administrator/i }),
        );

        await waitFor(() => expect(api.deleteAdmin).toHaveBeenCalledWith(BOSS.id));
        // The list is re-read, so the removed row disappears.
        await waitFor(() => expect(api.getAdmins).toHaveBeenCalledTimes(2));
        await waitFor(() =>
            expect(screen.queryByText("boss@example.com")).toBeNull(),
        );
    });
});