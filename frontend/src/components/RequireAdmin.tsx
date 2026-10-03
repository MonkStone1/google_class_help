import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../entities/user/index.ts";
import { isAdminUser } from "../entities/user/index.ts";

/**
 * The gate in front of `/admin` (ADR-0036).
 *
 * IMPORTANT: this is UX, never security. The authorization is the backend's
 * `require_admin` dependency, which answers 403 to every admin endpoint
 * regardless of what this component decided.
 *
 * It REDIRECTS to `/` instead of rendering a "not available" screen (D10): a
 * dead end told the user nothing and left a privileged-looking URL in the
 * address bar, while `/` is where a person without access actually belongs. The
 * same happens while the session is still unknown (`auth === null`) — the answer
 * is then "not an administrator", because rendering privileged UI before
 * `/auth/status` answered would flash it at whoever is loading the page.
 *
 * The flag is a BOOLEAN the backend derived from the validated session; the
 * addresses themselves never reach the browser, and nothing here reads a
 * localStorage setting.
 */
export function RequireAdmin({ children }: { children: ReactNode }) {
    const { auth } = useAuth();

    if (!isAdminUser(auth)) {
        return <Navigate to="/" replace />;
    }
    return <>{children}</>;
}
