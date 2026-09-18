import {
    BookOpen,
    CalendarDays,
    GraduationCap,
    LayoutDashboard,
    ListChecks,
    Settings as SettingsIcon,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { useSync, useCourses } from "../context/DataContext.tsx";
import { useSettings } from "../context/SettingsContext.tsx";
import { useI18n } from "../i18n.ts";
import { cn } from "../lib/cn.ts";
import type { I18nKey } from "../i18n.ts";

const ITEMS: Array<{
    to: string;
    labelKey: I18nKey;
    icon: typeof LayoutDashboard;
    counter?: "todo";
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
                {ITEMS.map((item) => (
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
