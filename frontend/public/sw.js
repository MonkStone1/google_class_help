// Service worker of the dashboard. It exists for exactly one job: handing
// focus from a duplicate tab to the tab that already owns the dashboard
// (ADR-0018). A plain window.focus() called from another tab is ignored by
// Chrome, while WindowClient.focus() here is allowed whenever a window of
// this origin holds a fresh user click (transient activation) — which the
// "Switch to it" button provides.
//
// Deliberately NO "fetch" handler: this worker must never intercept how the
// app loads; removing or unregistering it changes nothing except the
// duplicate-tab switch.

self.addEventListener("install", () => {
  // Nothing to prefetch; take over existing dashboard tabs right away.
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("message", (event) => {
  const message = event.data;
  if (!message || message.type !== "focus") return;
  event.waitUntil(focusAnotherTab(event.source));
});

// Route prefixes that belong to the dashboard. The tab that owns the Web Lock
// (see lib/tabPresence.ts) always lives on one of them, so a forgotten
// /settings tab or any other origin page is only a last-resort target.
const DASHBOARD_ROUTES = [
  "/",
  "/subjects",
  "/assignments",
  "/grades",
  "/calendar",
  "/settings",
];

function isDashboardClient(client) {
  try {
    const pathname = new URL(client.url).pathname;
    return DASHBOARD_ROUTES.some(
      (route) => pathname === route || pathname.startsWith(`${route}/`),
    );
  } catch {
    return false;
  }
}

async function focusAnotherTab(sender) {
  const senderId = sender && sender.id ? sender.id : null;
  const clients = await self.clients.matchAll({
    type: "window",
    includeUncontrolled: true, // the owner tab may predate this worker
  });
  // The sender is the duplicate tab; every other window of this origin is a
  // candidate, but the lock owner is a dashboard tab — prefer those, and a
  // visible one over a background tab.
  const others = clients.filter((client) => client.id !== senderId);

  const target =
    others.find(
      (client) => client.visibilityState === "visible" && isDashboardClient(client),
    ) ||
    others.find(isDashboardClient) ||
    others[0] ||
    null;

  let ok = false;
  if (target) {
    try {
      await target.focus();
      ok = true;
    } catch (error) {
      // Rejected when no window of the origin holds a transient activation:
      // switching must be triggered by a fresh click in one of the tabs.
      ok = false;
    }
  }
  if (sender && sender.postMessage) {
    sender.postMessage({ type: "focus-result", ok });
  }
}
