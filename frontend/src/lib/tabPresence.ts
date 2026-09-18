/**
 * Presence between dashboard tabs (see ADR-0018).
 *
 * The launcher only ever sees the *active* tab of a browser window, because
 * only that title lands in the window title. A dashboard parked in a pinned
 * or background tab is therefore invisible to it, and a second exe launch
 * opens one more tab. This module closes that gap from inside the app:
 *
 * - the first dashboard tab owns a Web Lock ("gc-dashboard-active-tab"),
 *   which browsers release automatically when the document goes away, so the
 *   owner cannot go stale the way a localStorage flag would;
 * - a tab that opens later notices the lock is taken, asks the owner to come
 *   to the front, and shows a dismissible notice.
 *
 * The switch itself goes through the service worker (`public/sw.js`): Chrome
 * ignores a plain `window.focus()` called from another tab, while the
 * worker's `WindowClient.focus()` is allowed whenever a window of this origin
 * holds a fresh user click (transient activation) — which the switch button
 * provides. Without a service worker the owner falls back to focusing itself
 * over the BroadcastChannel, where the acknowledgement is the best available
 * success signal.
 *
 * All browser APIs are injectable so the logic is testable without a
 * browser. When Web Locks is unavailable a tab simply behaves as if it were
 * the only one — the feature degrades to nothing.
 */

const LOCK_NAME = "gc-dashboard-active-tab";
const CHANNEL_NAME = "gc-dashboard-tabs";
const WORKER_URL = "/sw.js";
const FOCUS_RESULT_TIMEOUT_MS = 2500;
const FOCUS_ACK_TIMEOUT_MS = 1500;

/** Messages exchanged between dashboard tabs. */
type PresenceMessage =
  | { type: "focus-request" }
  | { type: "focus-ack" };

/** Message the service worker answers the switching tab with. */
type WorkerMessage = { type: "focus-result"; ok: boolean };

/** Message a duplicate tab sends to the service worker. */
type SwitchMessage = { type: "focus" };

type BridgeMessage = PresenceMessage | WorkerMessage;

/** Minimal BroadcastChannel surface this module relies on. */
export type PresenceChannel = {
  postMessage(message: PresenceMessage): void;
  addEventListener(
    type: "message",
    listener: (event: { data: PresenceMessage | null }) => void,
  ): void;
  close(): void;
};

/** Minimal Web Locks surface this module relies on. */
export type PresenceLocks = {
  request(
    name: string,
    options: { mode?: "exclusive" | "shared"; ifAvailable?: boolean },
    callback: (lock: object | null) => unknown,
  ): Promise<unknown>;
};

/** Minimal service-worker surface used for the focus handoff. */
export type PresenceWorker = {
  register(scriptUrl: string): Promise<unknown>;
  ready: Promise<{
    active: { postMessage(message: SwitchMessage): void } | null;
  }>;
  controller: { postMessage(message: SwitchMessage): void } | null;
  addEventListener(
    type: "message",
    listener: (event: { data: BridgeMessage | null }) => void,
  ): void;
};

/** A transport that can hand focus to another tab and report the outcome. */
export type FocusBridge = {
  requestFocus(): Promise<boolean>;
};

export type TabPresenceOptions = {
  createChannel?: () => PresenceChannel | null;
  locks?: PresenceLocks | null;
  focusWindow?: () => void;
  createBridge?: () => FocusBridge | null;
};

export type TabPresence = {
  /** Resolves once the tab knows whether another dashboard tab owns the lock. */
  ready: Promise<{ duplicate: boolean }>;
  /** Ask the owning tab to come to the front; resolves when a tab confirmed. */
  requestFocus(): Promise<boolean>;
  /** Release the local channel (tests and hot reload; the lock follows the page). */
  dispose(): void;
};

function defaultChannel(): PresenceChannel | null {
  const constructor = globalThis.BroadcastChannel;
  if (!constructor) return null;
  try {
    return new constructor(CHANNEL_NAME);
  } catch {
    return null;
  }
}

function defaultLocks(): PresenceLocks | null {
  return globalThis.navigator?.locks ?? null;
}

function defaultWorker(): PresenceWorker | null {
  return globalThis.navigator?.serviceWorker ?? null;
}

/** One race against one timer: losing the race is a `false`, not an error. */
function withTimeout(promise: Promise<boolean>, ms: number): Promise<boolean> {
  return new Promise<boolean>((resolve) => {
    const timer = globalThis.setTimeout(() => resolve(false), ms);
    promise.then(
      (ok) => {
        globalThis.clearTimeout(timer);
        resolve(ok);
      },
      () => {
        globalThis.clearTimeout(timer);
        resolve(false);
      },
    );
  });
}

function claimOwnership(locks: PresenceLocks | null): Promise<boolean> {
  if (!locks) return Promise.resolve(true); // no Web Locks: the only tab
  return new Promise<boolean>((resolve) => {
    locks
      .request(LOCK_NAME, { mode: "exclusive", ifAvailable: true }, (lock) => {
        if (!lock) {
          resolve(false);
          return undefined;
        }
        resolve(true);
        // Hold the lock for the lifetime of this document: the returned
        // promise never settles, so later tabs cannot become the owner.
        return new Promise<void>(() => {});
      })
      // A failing lock API must not disable the app: behave as the only tab.
      // Without this the rejection would be unhandled and the claim would
      // never settle, leaving `ready` pending forever.
      .catch(() => resolve(true));
  });
}

/**
 * Broadcast-channel handoff: the owner focuses itself and acknowledges. Used
 * when the service worker is unavailable; there the acknowledgement is the
 * best available success signal (the browser may still ignore the focus).
 */
function createChannelHandoff(
  channel: PresenceChannel | null,
  options: { isOwner(): boolean; focusWindow(): void },
): { requestFocus(): Promise<boolean> } {
  let awaitAck: ((ok: boolean) => void) | null = null;
  channel?.addEventListener("message", (event) => {
    const message = event.data;
    if (message?.type === "focus-ack") {
      const resolve = awaitAck;
      awaitAck = null;
      resolve?.(true);
      return;
    }
    if (message?.type !== "focus-request") return;
    if (!options.isOwner()) return; // only the owning tab fronts itself
    options.focusWindow();
    channel?.postMessage({ type: "focus-ack" } satisfies PresenceMessage);
  });
  return {
    async requestFocus(): Promise<boolean> {
      if (!channel) return false;
      return new Promise<boolean>((resolve) => {
        awaitAck = resolve;
        channel.postMessage({ type: "focus-request" } satisfies PresenceMessage);
        globalThis.setTimeout(() => {
          if (awaitAck === resolve) {
            awaitAck = null;
            resolve(false);
          }
        }, FOCUS_ACK_TIMEOUT_MS);
      });
    },
  };
}

/**
 * Focus handoff through the service worker: the only mechanism browsers let
 * move an unrelated tab to the front. The click on the switch button grants
 * the transient activation the worker's `focus()` call requires; when no
 * window has it (the automatic attempt right after the tab opened), the
 * worker reports failure and the notice stays until the button is used.
 */
function createServiceWorkerBridge(worker: PresenceWorker): FocusBridge {
  let resolveResult: ((ok: boolean) => void) | null = null;
  worker.addEventListener("message", (event) => {
    const message = event.data;
    if (message?.type !== "focus-result") return;
    const resolve = resolveResult;
    resolveResult = null;
    resolve?.(message.ok);
  });
  // Fire and forget: without the worker the broadcast fallback still runs,
  // and registration failures (old browsers, strict origins) are not a
  // dashboard problem.
  void worker.register(WORKER_URL).catch(() => undefined);
  return {
    // One timeout for one request: the inner timer (the ack wait) is owned by
    // the promise raced against here, not duplicated at this level.
    requestFocus(): Promise<boolean> {
      return withTimeout(
        (async () => {
          if (worker.controller) {
            worker.controller.postMessage({ type: "focus" });
          } else {
            const registration = await worker.ready;
            registration.active?.postMessage({ type: "focus" });
          }
          return new Promise<boolean>((resolve) => {
            resolveResult = resolve;
          });
        })(),
        FOCUS_RESULT_TIMEOUT_MS,
      );
    },
  };
}

function resolveBridge(options: TabPresenceOptions): FocusBridge | null {
  if (options.createBridge !== undefined) return options.createBridge();
  const worker = defaultWorker();
  return worker ? createServiceWorkerBridge(worker) : null;
}

export function createTabPresence(
  options: TabPresenceOptions = {},
): TabPresence {
  const channel = (options.createChannel ?? defaultChannel)();
  const locks = options.locks === undefined ? defaultLocks() : options.locks;
  const focusWindow = options.focusWindow ?? (() => window.focus());
  const bridge = resolveBridge(options);
  let duplicate = false;
  let disposed = false;

  // Built on first use: only a duplicate tab ever needs the broadcast
  // fallback, so the owner tab never creates it.
  let handoff: FocusBridge | null = null;
  const getHandoff = (): FocusBridge =>
    (handoff ??= createChannelHandoff(channel, {
      isOwner: () => !duplicate, // set once the lock claim settles
      focusWindow,
    }));

  const ready = claimOwnership(locks).then((owner) => {
    duplicate = !owner;
    return { duplicate };
  });

  return {
    ready,
    async requestFocus(): Promise<boolean> {
      // Only a duplicate asks: the owning tab is the target of the request.
      if (disposed || !duplicate) return false;
      // The worker's result is authoritative: it knows whether the browser
      // actually moved the other tab (transient activation rules apply).
      return bridge ? bridge.requestFocus() : getHandoff().requestFocus();
    },
    dispose() {
      disposed = true;
      channel?.close();
    },
  };
}

/**
 * One presence per document: React StrictMode mounts effects twice, and a
 * second claim in the same document would see its own lock and report a
 * duplicate.
 */
let sharedPresence: TabPresence | null = null;

export function sharedTabPresence(): TabPresence {
  if (sharedPresence === null) sharedPresence = createTabPresence();
  return sharedPresence;
}
