import type { ReactNode } from "react";
import { ShieldAlert } from "lucide-react";

import { EmptyState } from "./Skeletons.tsx";
import { useAuth } from "../context/DataContext.tsx";
import { useI18n } from "../i18n.ts";
import { isAdminUser } from "../types.ts";

/**
 * The gate in front of `/admin` (ADR-0035).
 *
 * IMPORTANT: this is UX, never security. Hiding the routes and the nav entry
 * makes the interface honest for a regular user; the authorization is the
 * backend's `require_admin` dependency, which answers 403 to every admin
 * endpoint regardless of what this component decided. A user who reaches an
 * admin page another way gets the same "not available" state — and if they
 * forged the request anyway, the API refuses it.
 *
 * The flag is a BOOLEAN the backend derived from `ADMIN_EMAILS`; the addresses
 * themselves never reach the browser. While the session is still unknown the
 * answer is "not an administrator": rendering privileged-looking UI before
 * `/auth/status` answered would flash it at whoever is loading the page.
 */
export function RequireAdmin({ children }: { children: ReactNode }) {
    const { t } = useI18n();
    const { auth } = useAuth();

    if (!isAdminUser(auth)) {
        return (
            <div className="page">
                <EmptyState
                    icon={<ShieldAlert size={28} />}
                    title={t("admin.notAvailable")}
                    subtitle={t("admin.notAvailableHint")}
                />
            </div>
        );
    }
    return <>{children}</>;
}
