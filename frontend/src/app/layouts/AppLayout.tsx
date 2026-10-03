/**
 * The user shell: sidebar, top bar and the routed content.
 *
 * The console shell is `AdminLayout.tsx`, and the two are the SAME markup with a
 * different sidebar — which is the point: the back office must look like the
 * rest of the product, and only the navigation differs (ADR-0036).
 */

import { Outlet } from "react-router-dom";

import { Sidebar } from "../../widgets/sidebar/index.ts";
import { TopBar } from "../../widgets/topbar/index.ts";
import { DashboardBoundary } from "../../shared/ui/index.ts";

export function AppLayout() {
  return (
    <div className="app-layout">
      <Sidebar />
      <div className="app-main">
        <TopBar />
        <main className="app-content">
          <DashboardBoundary>
            <Outlet />
          </DashboardBoundary>
        </main>
      </div>
    </div>
  );
}