/**
 * The public API of `app/providers` — the provider stack and the data context.
 *
 * `AppProviders` is what `app/App.tsx` renders; `DataProvider` is here rather
 * than in the context folder of a layer below because it owns the transport
 * session: it is the only place that reacts to a 401 and the only place that
 * knows the sync status is authoritative.
 */

export { AppProviders } from "./AppProviders.tsx";
export { DataProvider } from "./DataProvider.tsx";