/**
 * The notification centre: the list, and the rules that decide what is in it.
 *
 * `buildNotifications` used to sit in `TopBar.tsx`, which meant the rule "what
 * counts as a reminder" was only reachable from the shell that shows it. It is
 * a feature of the data — overdue / today / tomorrow, from the same assignments
 * the dashboard has — so it is stated here and the bell merely renders it.
 */

export { NotificationCenter } from "./NotificationCenter.tsx";
export { buildNotifications, notificationKey } from "./buildNotifications.ts";
export type { NotificationItem } from "./buildNotifications.ts";