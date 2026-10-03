/**
 * The shell's navigation: the user list, the console list, and the one
 * component that renders an item.
 *
 * They live together because they are one thing rendered two ways — the console
 * must look exactly like the public site (ADR-0036), and a shared `SidebarNav`
 * is what makes that true by construction rather than by CSS coincidence.
 */

export { Sidebar } from "./Sidebar.tsx";
export { AdminSidebar } from "./AdminSidebar.tsx";
export { SidebarNav } from "./SidebarNav.tsx";
export type { NavItem } from "./SidebarNav.tsx";