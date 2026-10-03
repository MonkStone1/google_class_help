/**
 * The public API of `pages/src/app/toaster`.
 *
 * A page is reached through its route, so almost everything outside this
 * folder only needs the screen itself. What the screen composes — the cards,
 * the feature it triggers — belongs to the layers below and is imported from
 * there, not from here: a second page that needed the same card would then
 * depend on a PAGE, which is how pages start importing each other.
 */

export { SyncToaster } from "./SyncToaster.tsx";
export { Toaster } from "./Toaster.tsx";
