import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsProvider } from "../../shared/settings/index.ts";
import type { AuthStatus } from "../../shared/types/index.ts";
import { RequireSuperAdmin } from "./RequireSuperAdmin.tsx";

const useAuth = vi.fn();

vi.mock("../../entities/user/index.ts", async () => {
    const actual = await vi.importActual<
        typeof import("../../entities/user/index.ts")
    >("../../entities/user/index.ts");
    return {
        ...actual,
        useAuth: () => useAuth(),
    };
});
vi.mock("../../features/sync/index.ts", async () => {
    const actual = await vi.importActual<
        typeof import("../../features/sync/index.ts")
    >("../../features/sync/index.ts");
    return {
        ...actual,
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
    };
});
vi.mock("../../entities/course/index.ts", async () => {
    const actual = await vi.importActual<
        typeof import("../../entities/course/index.ts")
    >("../../entities/course/index.ts");
    return {
        ...actual,
        useCourses: () => ({ courses: [], assignments: [] }),
    };
});

function signedIn(isSuperAdmin: boolean): AuthStatus {
    return {
        authenticated: true,
        login_in_progress: false,
        error: null,
        auth_url: null,
        user: {
            id: 1,
            name: "Test",
            email: "test@example.com",
            // A Super Admin is also an administrator; that is what makes
            // `is_admin` alone insufficient to gate this screen.
            is_admin: isSuperAdmin,
            is_super_admin: isSuperAdmin,
        },
    };
}

function renderGate() {
    return render(
        <MemoryRouter initialEntries={["/admin/admins"]}>
            <SettingsProvider>
                <Routes>
                    <Route
                        path="/admin/admins"
                        element={
                            <RequireSuperAdmin>
                                <div>registry screen</div>
                            </RequireSuperAdmin>
                        }
                    />
                    <Route
                        path="/admin"
                        element={<div>console dashboard</div>}
                    />
                </Routes>
            </SettingsProvider>
        </MemoryRouter>,
    );
}

/**
 * The registry gate (ADR-0036). A plain administrator may answer tickets but may
 * not manage other administrators, so they are sent back to the console they can
 * use instead of a dead end (D10). The backend refuses them either way — this is
 * UX, and it reads only the server-derived boolean.
 */
describe("RequireSuperAdmin", () => {
    beforeEach(() => {
        useAuth.mockReset();
    });

    it("renders the registry for the Super Admin", () => {
        useAuth.mockReturnValue({ auth: signedIn(true) });
        renderGate();
        expect(screen.getByText("registry screen")).toBeInTheDocument();
    });

    it("sends a plain administrator back to /admin", () => {
        useAuth.mockReturnValue({ auth: signedIn(false) });
        renderGate();
        expect(screen.queryByText("registry screen")).toBeNull();
        expect(screen.getByText("console dashboard")).toBeInTheDocument();
    });

    it("redirects while the session is still unknown", () => {
        // Same reason as the other guard: never flash privileged UI before
        // /auth/status has answered.
        useAuth.mockReturnValue({ auth: null });
        renderGate();
        expect(screen.queryByText("registry screen")).toBeNull();
        expect(screen.getByText("console dashboard")).toBeInTheDocument();
    });
});