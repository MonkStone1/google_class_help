/**
 * Load something once, with cancellation — the hook six copies of `useEffect`
 * used to be (ADR-0040 §1.3, defect 2).
 *
 * `AdminAdmins`, `AdminDashboard`, `AdminFeedback`, `AdminFeedbackTicket`,
 * `FeedbackTicket` and `FeedbackTickets` each carried the same
 * `new AbortController()` + `let cancelled` + `.catch` with `status === 0`
 * block. The copy existed because there was no shared hook for "load this when
 * the arguments change", not because six screens genuinely need six different
 * behaviours; four of them already used `useResource`, which is the same idea
 * with a cache bolted on.
 *
 * ## When to use which
 *
 * - `useAsyncResource` — an uncached read whose identity IS its arguments:
 *   the admin ticket list, a ticket by id, the console statistics. The
 *   arguments are named so the effect re-runs when they change.
 * - `useResource` — a read whose result is expensive and worth keeping between
 *   screens (teacher pages, ADR-0017): dedupe, TTL, "Updated HH:MM".
 *
 * ## Why `status === 0` is swallowed
 *
 * `ApiError.status === 0` is this app's name for "the backend is unreachable"
 * (see `shared/api/client.ts`). A screen that already shows cached data must not
 * replace it with an error banner because the machine went to sleep, so the
 * hook keeps the last good value and stays silent — exactly what all six copies
 * did by hand.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { ApiError } from "../api/index.ts";

export type AsyncResource<T> = {
    /** The last successfully loaded value, or null before the first one. */
    data: T | null;
    /** True while a request is in flight and no value has arrived yet. */
    loading: boolean;
    /** A failure worth showing; null while healthy or merely unreachable. */
    error: string | null;
    /** Re-run the load, e.g. after a mutation. */
    refresh: () => void;
};

/** The backend is unreachable: keep what we have rather than alarming anyone. */
function isUnreachable(reason: unknown): boolean {
    return (
        typeof reason === "object" &&
        reason !== null &&
        (reason as ApiError).status === 0
    );
}

function messageOf(reason: unknown, fallback: string): string {
    if (reason instanceof Error && reason.message) return reason.message;
    return fallback;
}

/**
 * `load(signal)` is called whenever `deps` change and on every `refresh()`.
 *
 * `deps` is passed to the effect explicitly rather than derived from the
 * function: the loaders are usually inline arrow functions, so a dependency
 * array computed from their identities would re-run on every render.
 */
export function useAsyncResource<T>(
    load: (signal: AbortSignal) => Promise<T>,
    deps: readonly unknown[],
    fallbackError = "The data could not be loaded.",
): AsyncResource<T> {
    const loadRef = useRef(load);
    loadRef.current = load;

    const [data, setData] = useState<T | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [nonce, setNonce] = useState(0);

    const refresh = useCallback(() => {
        setNonce((value) => value + 1);
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        let cancelled = false;
        setLoading(true);
        loadRef
            .current(controller.signal)
            .then((value) => {
                if (cancelled) return;
                setData(value);
                setError(null);
            })
            .catch((reason: unknown) => {
                if (cancelled || controller.signal.aborted) return;
                if (isUnreachable(reason)) return;
                setError(messageOf(reason, fallbackError));
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            // Both signals are needed, and they answer different questions:
            // `cancelled` silences a response that is already in flight, and
            // `abort` releases the connection for one that is not.
            cancelled = true;
            controller.abort();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps -- `deps` is the
        // caller's dependency list; `loadRef` is a ref and never changes.
    }, [...deps, nonce]);

    return { data, loading, error, refresh };
}