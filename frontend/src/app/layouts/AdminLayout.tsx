/**
 * The `/admin` console shell (D1/D2, ADR-0036).
 *
 * The SAME layout markup as the user shell — `div.app-layout`, the sidebar,
 * `div.app-main` with `main.app-content` — with `AdminSidebar` instead of
 * `Sidebar`. Mirroring the structure is the point: the console must look like
 * the rest of the product, and only the navigation differs.
 *
 * **There is no `<TopBar>` here** (п.8). The console is a back office for
 * tickets, and every control the topbar carried was either meaningless or
 * actively misleading on it:
 *
 * - the global search looks through the *assignments and courses* cache, which
 *   an administrator has no use for while working a ticket queue;
 * - the sync button and its timestamp belong to a user's own Google grant —
 *   the console has no dataset of its own to sync;
 * - the notification bell is built from the same assignments (ADR-0004);
 * - the theme toggle is the only genuinely useful one, and it is reachable from
 *   `/settings` for the same person.
 *
 * Removing it also drops the `?q=` plumbing this shell carried for the search
 * box — there is nothing left to feed it.
 */

import { Outlet } from "react-router-dom";

import { AdminSidebar } from "../../widgets/sidebar/index.ts";
import { DashboardBoundary } from "../../shared/ui/index.ts";
import { useAuth } from "../../entities/user/index.ts";

export function AdminLayout() {
  const { auth } = useAuth();

  // The console is an authenticated surface: until the session answer arrives
  // there is nothing honest to render, and the guards would redirect a flash of
  // it to `/`. Render nothing until `auth` is decided.
  if (!auth) return null;

  return (
    <div className="app-layout">
      <AdminSidebar />
      <div className="app-main">
        <main className="app-content">
          <DashboardBoundary>
            <Outlet />
          </DashboardBoundary>
        </main>
      </div>
    </div>
  );
}