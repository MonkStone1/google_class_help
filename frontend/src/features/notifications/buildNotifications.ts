/**
 * What counts as a reminder.
 *
 * Three categories and no more: overdue, due today, due tomorrow. The rule is
 * about the DATA — the same assignments the dashboard already holds — so it
 * belongs in the feature that owns notifications rather than in the bar that
 * draws the bell. `TopBar` used to hold it, which meant the only way to ask
 * "would this assignment ring?" was to read the shell.
 */

import { parseDue } from "../../shared/lib/index.ts";
import type { Assignment } from "../../shared/types/index.ts";

export type NotificationItem = {
  assignment: Assignment;
  kind: "overdue" | "today" | "tomorrow";
};

/**
 * Dismissal key: kind + assignment id, so hiding a reminder is scoped to one
 * category — the same assignment reappears when it moves to another category
 * (e.g. "due tomorrow" → "due today").
 */
export function notificationKey(item: NotificationItem): string {
  return `${item.kind}:${item.assignment.id}`;
}

export function buildNotifications(
  assignments: Assignment[],
): NotificationItem[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const tomorrow = new Date(today.getTime() + 24 * 60 * 60 * 1000);
  const items: NotificationItem[] = [];
  for (const assignment of assignments) {
    if (assignment.submitted || !assignment.due_at) {
      continue;
    }
    const due = parseDue(assignment.due_at);
    if (due && due < today) {
      items.push({ assignment, kind: "overdue" });
    } else if (due && due.toDateString() === today.toDateString()) {
      items.push({ assignment, kind: "today" });
    } else if (due && due.toDateString() === tomorrow.toDateString()) {
      items.push({ assignment, kind: "tomorrow" });
    }
  }
  return items;
}