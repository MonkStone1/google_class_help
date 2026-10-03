import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../../entities/user/index.ts";
import { isSuperAdminUser } from "../../entities/user/index.ts";

/**
 * The gate in front of `/admin/admins` (ADR-0036).
 *
 * Stricter than `RequireAdmin`: only the Super Admin may manage the registry —
 * plain administrators get 403 from `require_super_admin` on the backend. Here
 * they are sent back to `/admin`, the console they CAN use, rather than left on
 * a dead end (D10).
 *
 * `auth === null` redirects too, for the same reason as the other guard:
 * privileged-looking UI must never flash before `/auth/status` answered.
 */
export function RequireSuperAdmin({ children }: { children: ReactNode }) {
    const { auth } = useAuth();

    if (!isSuperAdminUser(auth)) {
        return <Navigate to="/admin" replace />;
    }
    return <>{children}</>;
}