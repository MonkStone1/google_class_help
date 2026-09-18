/**
 * Tiny client-side cache for the teacher reads (ADR-0017).
 *
 * Teacher pages (course, grades, student, assignment) share a lot of
 * overlapping data, and switching tabs must not re-fetch the same roster or
 * grade matrix. Results are kept in memory with a short TTL, and every page
 * exposes a Refresh action plus an "Updated HH:MM" label, so the cache never
 * serves stale data indefinitely (section 17 of the teacher spec).
 *
 * Requests are also deduplicated per key (two hooks on one key share a single
 * network read) and cancelled with an AbortController once the last consumer
 * goes away, so navigating between teacher pages does not leave a trail of
 * pointless in-flight requests behind.
 *
 * React-free cache + one hook; deliberately dependency-free like the rest of
 * the app's lib layer.
 */

import { useCallback, useEffect, useRef, useState } from "react";

type Entry<T> = { value: T; at: number };

type Inflight<T> = {
  promise: Promise<Entry<T>>;
  controller: AbortController;
  /** Hook instances still awaiting this request. */
  consumers: number;
};

const store = new Map<string, Entry<unknown>>();
const inflight = new Map<string, Inflight<unknown>>();

/** How long a value is considered fresh before the next mount re-fetches it. */
export const RESOURCE_TTL_MS = 60_000;

/** Drop cached values whose key starts with the prefix (used after a sync). */
export function invalidateResources(prefix: string): void {
  for (const key of [...store.keys()]) {
    if (key.startsWith(prefix)) {
      store.delete(key);
    }
  }
}

export function invalidateAllResources(): void {
  store.clear();
}

function read<T>(key: string): Entry<T> | undefined {
  return store.get(key) as Entry<T> | undefined;
}

function isAbortError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    (error as { name?: string }).name === "AbortError"
  );
}

/**
 * Start (or join) the request for `key`. The cache entry is written here, so
 * every consumer of the shared promise sees the exact value that was stored.
 */
function acquire<T>(
  key: string,
  run: (signal: AbortSignal) => Promise<T>,
): Promise<Entry<T>> {
  const running = inflight.get(key);
  if (running) {
    running.consumers += 1;
    return running.promise as Promise<Entry<T>>;
  }
  const controller = new AbortController();
  const entry: Inflight<T> = {
    controller,
    consumers: 1,
    promise: run(controller.signal).then((value) => {
      const fresh: Entry<T> = { value, at: Date.now() };
      store.set(key, fresh as Entry<unknown>);
      return fresh;
    }),
  };
  inflight.set(key, entry as Inflight<unknown>);
  // Forget the settled request; the mirror rejection has already been handed
  // to the awaiting hooks, so swallow it here.
  void entry.promise
    .catch(() => undefined)
    .then(() => {
      if (inflight.get(key) === entry) {
        inflight.delete(key);
      }
    });
  return entry.promise;
}

/** A consumer stopped waiting; the last one cancels the underlying request. */
function release(key: string, promise: Promise<unknown>): void {
  const entry = inflight.get(key);
  if (!entry || entry.promise !== promise) {
    return;
  }
  entry.consumers -= 1;
  if (entry.consumers <= 0) {
    // Remove before aborting so a late acquire cannot join a dying request.
    inflight.delete(key);
    entry.controller.abort();
  }
}

export type Resource<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  /** Epoch ms of the value currently shown, for the "Updated HH:MM" label. */
  updatedAt: number | null;
  refresh: () => void;
};

/**
 * Load `fetcher(signal)` under `key`, reusing a fresh cached value when
 * available.
 *
 * `key` must uniquely identify the request (course id, student id, ...);
 * changing it resets the state and loads the new resource. `refresh()` forces
 * a network read even when the cached value is still fresh.
 */
export function useResource<T>(
  key: string,
  fetcher: (signal: AbortSignal) => Promise<T>,
): Resource<T> {
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  // The cache is the single source of truth; React state only mirrors the
  // entry for the current key. A key change is handled *during render* (the
  // documented "adjust state during render" pattern) so a component can never
  // paint the previous key's data under the new key's heading.
  const [entry, setEntry] = useState<Entry<T> | null>(() => read<T>(key) ?? null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(() => !read<T>(key));

  const keyRef = useRef(key);
  if (keyRef.current !== key) {
    keyRef.current = key;
    const hit = read<T>(key);
    setEntry(hit ?? null);
    setLoading(!hit);
    setError(null);
  }

  // The request this hook instance currently owns, if any.
  const activeRef = useRef<{ key: string; promise: Promise<Entry<T>> } | null>(
    null,
  );

  const load = useCallback(async (force: boolean) => {
    const currentKey = keyRef.current;
    const hit = read<T>(currentKey);
    if (hit && !force && Date.now() - hit.at < RESOURCE_TTL_MS) {
      setEntry(hit);
      setError(null);
      setLoading(false);
      return;
    }

    // A refresh replaces the request this instance already started.
    const previous = activeRef.current;
    if (previous) {
      release(previous.key, previous.promise);
    }

    if (!hit) {
      setLoading(true);
    }
    const promise = acquire<T>(currentKey, (signal) =>
      fetcherRef.current(signal),
    );
    activeRef.current = { key: currentKey, promise };

    /** The response must still belong to this key and this request. */
    const isCurrent = () =>
      keyRef.current === currentKey && activeRef.current?.promise === promise;

    try {
      const fresh = await promise;
      if (!isCurrent()) return;
      setEntry(fresh);
      setError(null);
    } catch (err) {
      // Losing the key (navigation) or the request (superseded refresh) is
      // not an error the user should see.
      if (!isCurrent() || isAbortError(err)) return;
      setError(
        err instanceof Error ? err.message : "The data could not be loaded.",
      );
    } finally {
      if (isCurrent()) {
        activeRef.current = null;
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void load(false);
    return () => {
      const active = activeRef.current;
      if (active) {
        release(active.key, active.promise);
        activeRef.current = null;
      }
    };
  }, [key, load]);

  const refresh = useCallback(() => {
    void load(true);
  }, [load]);

  return {
    data: entry?.value ?? null,
    loading,
    error,
    updatedAt: entry?.at ?? null,
    refresh,
  };
}
