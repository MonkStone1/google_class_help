import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsProvider } from "../context/SettingsContext.tsx";
import type { AuthStatus } from "../types.ts";
import { RequireAdmin } from "./RequireAdmin.tsx";

const useAuth = vi.fn();

vi.mock("../context/DataContext.tsx", async () => {
    const actual = await vi.importActual<
        typeof import("../context/DataContext.tsx")
    >("../context/DataContext.tsx");
    return {
        ...actual,
        DataProvider: ({ children }: { children: React.ReactNode }) => children,
        useAuth: () => useAuth(),
        useSync: () => ({
            status: null,
            loading: false,
            syncing: false,
            error: null,
            syncNow: vi.fn(),
            syncRestart: vi.fn(),
            refresh: vi.fn(),
            syncStuck: false,
        }),
        useCourses: () => ({ courses: [], assignments: [] }),
    };
});

function signedIn(isAdmin: boolean): AuthStatus {
    return {
        authenticated: true,
        login_in_progress: false,
        error: null,
        auth_url: null,
        user: {
            id: 1,
            name: "Test",
            email: "test@example.com",
            is_admin: isAdmin,
        },
    };
}

function renderGate() {
    return render(
        <MemoryRouter>
            <SettingsProvider>
                <RequireAdmin>
                    <div>admin dashboard</div>
                </RequireAdmin>
            </SettingsProvider>
        </MemoryRouter>,
    );
}

/**
 * The admin gate is UX, not security (ADR-0035): the backend's require_admin
 * answers 403 regardless. What the frontend owes the user is an honest screen
 * instead of a broken page — and it must read the flag from the SERVER's
 * answer, never from anything a browser can set.
 */
describe("RequireAdmin", () => {
    beforeEach(() => {
        useAuth.mockReset();
    });

    it("renders the children for a session the backend flagged as admin", () => {
        useAuth.mockReturnValue({ auth: signedIn(true) });
        renderGate();
        expect(screen.getByText("admin dashboard")).toBeInTheDocument();
    });

    it("shows the 'not available' state for a regular user", () => {
        useAuth.mockReturnValue({ auth: signedIn(false) });
        renderGate();
        expect(screen.queryByText("admin dashboard")).toBeNull();
        expect(
            screen.getByText(/only available to administrators/i),
        ).toBeInTheDocument();
    });

    it("shows the same state while the session is still unknown", () => {
        // Rendering the admin page before /auth/status answered would flash
        // privileged-looking UI at whoever is loading it.
        useAuth.mockReturnValue({ auth: null });
        renderGate();
        expect(screen.queryByText("admin dashboard")).toBeNull();
    });
});
