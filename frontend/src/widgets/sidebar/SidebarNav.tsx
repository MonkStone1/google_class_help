import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import type { LucideIcon } from "lucide-react";

import { cn } from "../../shared/lib/index.ts";
import type { I18nKey } from "../../shared/i18n/index.ts";

/**
 * One navigation entry of the sidebar.
 *
 * `counter` and `end` are presentation options, not permissions: which entries
 * EXIST is decided by the caller (Sidebar builds the user list, AdminSidebar the
 * admin one), so this component never has to know a role.
 */
export type NavItem = {
    to: string;
    labelKey: I18nKey;
    icon: LucideIcon;
    counter?: "todo";
    /** Exact-match the link (`/` must not stay active on every route). */
    end?: boolean;
};

/**
 * The one navigation component of the app (D2/ADR-0036).
 *
 * Both sidebars — the user `Sidebar` and the `AdminSidebar` of the `/admin`
 * console — render THIS, with different `items`. It is deliberately
 * presentational: it fetches nothing, reads no role and holds no navigation
 * policy, so the markup, the active state and the styling cannot drift between
 * the two shells, and there is no second copy of the sidebar CSS.
 *
 * `alert` is a slot rather than a prop with a shape: the user sidebar fills it
 * with the overdue summary, and the admin console passes nothing at all.
 */
export function SidebarNav({
    items,
    alert,
    compact,
    counters,
    t,
}: {
    items: NavItem[];
    alert?: ReactNode;
    /** Mirrors the card-density setting on the aside, as the user sidebar did. */
    compact?: boolean;
    /**
     * Value of each `counter` kind, computed by the caller. Passing numbers in
     * keeps this component from having to know what "todo" means — the user
     * sidebar owns the dataset, the console has no counters at all.
     */
    counters?: Partial<Record<NonNullable<NavItem["counter"]>, number>>;
    /** Passed in rather than read here: keeps this component free of context. */
    t: (key: I18nKey, params?: Record<string, string | number>) => string;
}) {
    return (
        <aside className={cn("sidebar", compact && "compact")}>
            <div className="sidebar-brand">
                <div className="sidebar-brand-logo">GC</div>
                <div>
                    <div className="sidebar-brand-name">Classroom</div>
                    <div className="sidebar-brand-sub">
                        {t("nav.dashboard")}
                    </div>
                </div>
            </div>

            <nav className="sidebar-nav">
                {items.map((item) => {
                    // The counter is a per-item concern, so each entry resolves
                    // its own badge from the values the caller supplied.
                    const count = item.counter
                        ? (counters?.[item.counter] ?? 0)
                        : 0;
                    return (
                        <NavLink
                            key={item.to}
                            to={item.to}
                            className={({ isActive }) =>
                                cn("sidebar-link", isActive && "active")
                            }
                            end={item.end ?? item.to === "/"}
                        >
                            <item.icon size={18} />
                            <span>{t(item.labelKey)}</span>
                            {count > 0 ? (
                                <span className="sidebar-counter">{count}</span>
                            ) : null}
                        </NavLink>
                    );
                })}
            </nav>

            {alert}
        </aside>
    );
}