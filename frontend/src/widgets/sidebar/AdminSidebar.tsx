import { LayoutDashboard, ShieldCheck, Ticket } from "lucide-react";

import { useAuth } from "../../entities/user/index.ts";
import { useSettings } from "../../shared/settings/index.ts";
import { useI18n } from "../../shared/i18n/index.ts";
import { isSuperAdminUser } from "../../entities/user/index.ts";
import { SidebarNav, type NavItem } from "./SidebarNav.tsx";

/**
 * Navigation of the `/admin` console (D1/D2, ADR-0036).
 *
 * A separate item list, not a filtered copy of the user one: the console is a
 * distinct shell reached only by the URL `/admin`, and it shows only console
 * destinations. `Tickets` is available to both admin roles; `Admins` appears
 * only for the Super Admin, matching what `GET /api/admin/admins` actually
 * answers — and only as UX, since the API refuses a plain administrator either
 * way.
 *
 * Rendering `SidebarNav` (the same component as `Sidebar`) is what keeps the
 * two shells visually identical with one implementation and one stylesheet.
 */
export function AdminSidebar() {
    const { auth } = useAuth();
    const { cardDensity } = useSettings();
    const { t } = useI18n();

    const items: NavItem[] = [
        { to: "/admin", labelKey: "nav.admin", icon: LayoutDashboard },
        { to: "/admin/feedback", labelKey: "nav.adminTickets", icon: Ticket },
    ];
    // Read from the server-derived boolean, never from localStorage: a browser
    // must not be able to unlock the registry screen (and could not use it).
    if (isSuperAdminUser(auth)) {
        items.push({
            to: "/admin/admins",
            labelKey: "nav.admins",
            icon: ShieldCheck,
        });
    }

    return (
        <SidebarNav items={items} compact={cardDensity === "compact"} t={t} />
    );
}