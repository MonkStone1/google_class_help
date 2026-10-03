import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsProvider } from "../shared/settings/SettingsProvider.tsx";
import type { AuthStatus } from "../shared/types/index.ts";
import { AdminSidebar } from "./AdminSidebar.tsx";
import { Sidebar } from "./Sidebar.tsx";

const useAuth = vi.fn();
const useSync = vi.fn();

vi.mock("../entities/user/index.ts", async () => {
    const actual = await vi.importActual<
        typeof import("../entities/user/index.ts")
    >("../entities/user/index.ts");
    return {
        ...actual,
        useAuth: () => useAuth(),
    };
});
vi.mock("../features/sync/index.ts", async () => {
    const actual = await vi.importActual<
        typeof import("../features/sync/index.ts")
    >("../features/sync/index.ts");
    return {
        ...actual,
        useSync: () =>
            useSync() ?? {
                status: null,
                loading: false,
                syncing: false,
                error: null,
                syncNow: vi.fn(),
                refresh: vi.fn(),
            },
    };
});
vi.mock("../entities/course/index.ts", async () => {
    const actual = await vi.importActual<
        typeof import("../entities/course/index.ts")
    >("../entities/course/index.ts");
    return {
        ...actual,
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

function renderAt(path: string, ui: React.ReactNode) {
    return render(
        <MemoryRouter initialEntries={[path]}>
            <SettingsProvider>{ui}</SettingsProvider>
        </MemoryRouter>,
    );
}

/**
 * The nav links only. The brand block repeats "Dashboard" as its subtitle, so an
 * unscoped `getByText("Dashboard")` would find two nodes and assert nothing about
 * the navigation.
 */
function navLinks(): HTMLElement[] {
    const nav = document.querySelector(".sidebar-nav");
    if (!nav) throw new Error("sidebar nav not rendered");
    return Array.from(nav.querySelectorAll("a")).map((a) => a as HTMLElement);
}

function navLabels(): string[] {
    return navLinks().map((link) => link.textContent ?? "");
}

/**
 * The two sidebars of D1/D2. The user site has NO admin entry at all — not even
 * for the Super Admin, because the console is reached only by its URL — and the
 * console shows `Admins` only to the Super Admin.
 */
describe("sidebars", () => {
    beforeEach(() => {
        useAuth.mockReset();
        useSync.mockReset();
        localStorage.setItem("gc-settings", JSON.stringify({ language: "en" }));
    });

    it("shows no admin entry on the user site, even for the Super Admin", () => {
        useAuth.mockReturnValue({ auth: signedIn(true, true) });
        renderAt("/", <Sidebar />);
        const labels = navLabels();
        // D1: the console is reachable only by its URL, so none of its entries
        // may appear here — not for an administrator, not for the Super Admin.
        expect(labels).not.toContain("Administration");
        expect(labels).not.toContain("Administrators");
        expect(labels).not.toContain("Tickets");
        // The ordinary entries are still there.
        expect(labels).toContain("Dashboard");
        expect(labels).toContain("Feedback");
        expect(labels).toContain("Settings");
    });

    it("shows Tickets only to a plain administrator", () => {
        useAuth.mockReturnValue({ auth: signedIn(true, false) });
        renderAt("/admin", <AdminSidebar />);
        const labels = navLabels();
        expect(labels).toContain("Tickets");
        expect(labels).not.toContain("Administrators");
    });

    it("shows Tickets and Admins to the Super Admin", () => {
        useAuth.mockReturnValue({ auth: signedIn(true, true) });
        renderAt("/admin", <AdminSidebar />);
        const labels = navLabels();
        expect(labels).toContain("Tickets");
        expect(labels).toContain("Administrators");
    });

    it("marks the active console item", () => {
        useAuth.mockReturnValue({ auth: signedIn(true, true) });
        renderAt("/admin/feedback", <AdminSidebar />);
        // The active entry carries the shared `.active` class from SidebarNav.
        const byLabel = (label: string) =>
            navLinks().find((link) => link.textContent?.includes(label));
        expect(byLabel("Tickets")?.className).toContain("active");
        expect(byLabel("Administrators")?.className).not.toContain("active");
    });
});