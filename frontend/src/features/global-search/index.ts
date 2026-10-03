/**
 * Global search over the locally cached Classroom data (ADR-0012).
 *
 * A feature rather than a `shared/lib` helper: the ranking is a product
 * decision about one surface (Ctrl-K in the top bar), not a mechanism another
 * screen is expected to reuse. It is pure and dependency-free, so it stays
 * testable without a renderer.
 */

export {
    EMPTY_RESULTS,
    courseSubtitle,
    searchAll,
} from "./search.ts";
export type { SearchHit, SearchResults } from "./search.ts";