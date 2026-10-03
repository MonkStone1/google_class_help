import {
    BookOpen,
    CalendarDays,
    GraduationCap,
    LayoutDashboard,
    ListChecks,
    MessageSquare,
    Settings as SettingsIcon,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { useSync } from "../../features/sync/index.ts";
import { useCourses } from "../../entities/course/index.ts";
import { useSettings } from "../../shared/settings/SettingsProvider.tsx";
import { useI18n } from "../../shared/i18n/index.ts";
import { SidebarNav, type NavItem } from "./SidebarNav.tsx";

/**
 * Navigation of the USER site.
 *
 * There is no "Administration" entry here any more (D1/ADR-0036): the admin
 * console is a separate shell reachable only by the URL `/admin`, so the public
 * navigation neither advertises it nor has to decide who may see it. The
 * console's own list lives in `AdminSidebar.tsx`; both render `SidebarNav`, so
 * there is one navigation component and no duplicated markup or CSS.
 */
const ITEMS: NavItem[] = [
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
    { to: "/settings", labelKey: "nav.settings", icon: SettingsIcon },
];

export function Sidebar() {
    const { status } = useSync();
    const { assignments } = useCourses();
    const { cardDensity } = useSettings();
    const { t } = useI18n();

    const todoCount = assignments.filter((a) => !a.submitted).length;
    const overdueCount = status?.overdue ?? 0;

    return (
        <SidebarNav
            items={ITEMS}
            compact={cardDensity === "compact"}
            counters={{ todo: todoCount }}
            t={t}
            alert={
                overdueCount > 0 ? (
                    <NavLink
                        to="/assignments?status=overdue"
                        className="sidebar-alert"
                    >
                        <span>{overdueCount}</span>
                        <span>
                            {overdueCount === 1
                                ? t("nav.overdue.one")
                                : t("nav.overdue.many", {
                                      count: overdueCount,
                                  })}
                        </span>
                    </NavLink>
                ) : null
            }
        />
    );
}
