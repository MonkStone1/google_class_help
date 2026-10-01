import {
    BookOpen,
    CalendarDays,
    GraduationCap,
    LayoutDashboard,
    ListChecks,
    MessageSquare,
    Settings as SettingsIcon,
    ShieldCheck,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { useAuth, useSync, useCourses } from "../context/DataContext.tsx";
import { useSettings } from "../context/SettingsContext.tsx";
import { useI18n } from "../i18n.ts";
import { cn } from "../lib/cn.ts";
import type { I18nKey } from "../i18n.ts";
import { isAdminUser } from "../types.ts";

/**
 * Navigation entries.
 *
 * `admin: true` entries are rendered ONLY when the backend reported
 * `is_admin: true` for this session (ADR-0035). That is a UX decision — the
 * API enforces it independently — and it is why the flag, not a localStorage
 * setting, decides: a browser must not be able to unlock an admin surface.
 */
const ITEMS: Array<{
    to: string;
    labelKey: I18nKey;
    icon: typeof LayoutDashboard;
    counter?: "todo";
    admin?: boolean;
}> = [
    { to: "/", labelKey: "nav.dashboard", icon: LayoutDashboard },
    { to: "/subjects", labelKey: "nav.subjects", icon: BookOpen },
    {
        to: "/assignments",
        labelKey: "nav.assignments",
        icon: ListChecks,
        counter: "todo",
    },
    { to: "/grades", labelKey: "nav.grades", icon: GraduationCap },
    { to: "/calendar", labelKey: "nav.calendar", icon: CalendarDays },
    { to: "/feedback", labelKey: "nav.feedback", icon: MessageSquare },
    {
        to: "/admin",
        labelKey: "nav.admin",
        icon: ShieldCheck,
        admin: true,
    },
    { to: "/settings", labelKey: "nav.settings", icon: SettingsIcon },
];

export function Sidebar() {
    const { status } = useSync();
    const { assignments } = useCourses();
    const { auth } = useAuth();
    const { cardDensity } = useSettings();
    const { t } = useI18n();

    const todoCount = assignments.filter((a) => !a.submitted).length;
    const overdueCount = status?.overdue ?? 0;
    const isAdmin = isAdminUser(auth);
    const items = ITEMS.filter((item) => !item.admin || isAdmin);

    return (
        <aside
            className={cn("sidebar", cardDensity === "compact" && "compact")}
        >
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
                {items.map((item) => (
                    <NavLink
                        key={item.to}
                        to={item.to}
                        className={({ isActive }) =>
                            cn("sidebar-link", isActive && "active")
                        }
                        end={item.to === "/"}
                    >
                        <item.icon size={18} />
                        <span>{t(item.labelKey)}</span>
                        {item.counter === "todo" && todoCount > 0 ? (
                            <span className="sidebar-counter">{todoCount}</span>
                        ) : null}
                    </NavLink>
                ))}
            </nav>

            {overdueCount > 0 ? (
                <NavLink
                    to="/assignments?status=overdue"
                    className="sidebar-alert"
                >
                    <span>{overdueCount}</span>
                    <span>
                        {overdueCount === 1
                            ? t("nav.overdue.one")
                            : t("nav.overdue.many", { count: overdueCount })}
                    </span>
                </NavLink>
            ) : null}
        </aside>
    );
}
