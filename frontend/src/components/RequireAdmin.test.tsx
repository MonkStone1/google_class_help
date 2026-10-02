import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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

function signedIn(isAdmin: boolean, isSuperAdmin = false): AuthStatus {
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
            is_super_admin: isSuperAdmin,
        },
    };
}

/**
 * The admin gate is UX, not security (ADR-0036): the backend's require_admin
 * answers 403 regardless. What the frontend owes the user now is a REDIRECT to
 * `/` (D10) instead of the old "not available" dead end — and the flag must come
 * from the SERVER's answer, never from anything a browser can set.
 */
describe("RequireAdmin", () => {
    beforeEach(() => {
        useAuth.mockReset();
    });

    it("renders the children for a session the backend flagged as admin", () => {
        useAuth.mockReturnValue({ auth: signedIn(true) });
        render(
            <MemoryRouter>
                <SettingsProvider>
                    <RequireAdmin>
                        <div>admin dashboard</div>
                    </RequireAdmin>
                </SettingsProvider>
            </MemoryRouter>,
        );
        expect(screen.getByText("admin dashboard")).toBeInTheDocument();
    });

    it("sends a regular user to / instead of rendering a dead end", () => {
        useAuth.mockReturnValue({ auth: signedIn(false) });
        render(
            <MemoryRouter initialEntries={["/admin"]}>
                <SettingsProvider>
                    <Routes>
                        <Route
                            path="/admin"
                            element={
                                <RequireAdmin>
                                    <div>admin dashboard</div>
                                </RequireAdmin>
                            }
                        />
                        <Route path="/" element={<div>public home</div>} />
                        <Route
                            path="*"
                            element={<div>public home (catch-all)</div>}
                        />
                      </Routes>
                </SettingsProvider>
            </MemoryRouter>,
        );
        expect(screen.queryByText("admin dashboard")).toBeNull();
        expect(screen.getByText(/public home/i)).toBeInTheDocument();
    });

    it("redirects while the session is still unknown", () => {
        // Rendering the admin page before /auth/status answered would flash
        // privileged-looking UI at whoever is loading it.
        useAuth.mockReturnValue({ auth: null });
        render(
            <MemoryRouter initialEntries={["/admin"]}>
                <SettingsProvider>
                    <Routes>
                        <Route
                            path="/admin"
                            element={
                                <RequireAdmin>
                                    <div>admin dashboard</div>
                                </RequireAdmin>
                            }
                        />
                        <Route
                            path="*"
                            element={<div>public home (catch-all)</div>}
                        />
                      </Routes>
                </SettingsProvider>
            </MemoryRouter>,
        );
        expect(screen.queryByText("admin dashboard")).toBeNull();
        expect(screen.getByText(/public home/i)).toBeInTheDocument();
    });
});
