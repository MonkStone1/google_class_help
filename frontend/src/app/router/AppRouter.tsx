/**
 * `<Routes>` built from the data in `routes.tsx`.
 *
 * The guards stay data: a route says WHO may see it, and this file turns that
 * into elements. Nothing here decides a rule; nothing in `routes.tsx` decides
 * markup.
 */

import { Navigate, Route, Routes } from "react-router-dom";

import { AdminLayout } from "../layouts/AdminLayout.tsx";
import { AppLayout } from "../layouts/AppLayout.tsx";
import { RequireAdmin, RequireSuperAdmin } from "./guards.tsx";
import { ADMIN_ROUTES, USER_ROUTES, type Guard } from "./routes.tsx";

/** Wraps an element in the guards a route asks for. */
function guarded(element: React.ReactNode, guard?: Guard): React.ReactNode {
  if (guard === "super-admin") {
    return (
      <RequireAdmin>
        <RequireSuperAdmin>{element}</RequireSuperAdmin>
      </RequireAdmin>
    );
  }
  if (guard === "admin") {
    return <RequireAdmin>{element}</RequireAdmin>;
  }
  return element;
}

export function AppRouter() {
  return (
    <Routes>
      {/* Two shells, each owning its own routes. React Router picks the branch by
          the most specific match, so `/admin` reaches the console even though
          the user branch also carries an `/admin/*` catch-all. */}
      <Route element={<AppLayout />}>
        {USER_ROUTES.map((route) => (
          <Route
            key={route.path}
            path={route.path}
            element={guarded(route.element, route.guard)}
          />
        ))}
        {/* An unknown CONSOLE path goes to the console root, never to the public
            dashboard: leaving the console for a typo would be confusing. */}
        <Route path="/admin/*" element={<Navigate to="/admin" replace />} />
        {/* And an unknown path anywhere else goes home, as it always has. */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>

      <Route element={<AdminLayout />}>
        {ADMIN_ROUTES.map((route) => (
          <Route
            key={route.path}
            path={route.path}
            element={guarded(route.element, route.guard)}
          />
        ))}
      </Route>
    </Routes>
  );
}