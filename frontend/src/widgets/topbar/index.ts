/**
 * The top bar: search, the sync controls and the notification bell.
 *
 * The two features it composes — global search and the notification centre —
 * stay in `features/`: the bar is the shell that assembles them, not their
 * owner, and a bell that lives here could not be reused on the settings page.
 */

export { TopBar } from "./TopBar.tsx";
export { SearchResults } from "./SearchResults.tsx";