/**
 * The public API of `shared/hooks`.
 *
 * Two resource hooks that look alike and are not: `useResource` is the keyed
 * CACHE the whole app shares (a second mount of the same key is free, and
 * invalidation is global), while `useAsyncResource` is a plain
 * fetch-with-a-signal for a one-off. They are exported side by side so the
 * difference is a decision made at the call site, not a file path.
 *
 * They sit in `shared/hooks` rather than `shared/lib` because both are hooks:
 * `shared/lib` is React-free (guardrail #2) and these are not.
 */

export { invalidateAllResources, invalidateResources } from "./useResource.ts";
export type { Resource } from "./useResource.ts";
export { useResource } from "./useResource.ts";
export type { AsyncResource } from "./useAsyncResource.ts";
export { useAsyncResource } from "./useAsyncResource.ts";