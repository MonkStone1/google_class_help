/**
 * UI primitives with no domain and no state.
 *
 * `shared/ui/` is the answer to "what does a card, a skeleton and a confirmation
 * dialog have in common": they know about markup and the design tokens, and
 * nothing about assignments, tickets or routes. A component that needs any of
 * those belongs in `entities/`, `features/` or `pages/` — the rule that keeps
 * this folder from becoming the old `components/` with a shorter name.
 */

export { DashboardBoundary } from "./ErrorBoundary.tsx";
export {
    CardSkeleton,
    EmptyState,
    SectionSkeleton,
    Skeleton,
} from "./Skeletons.tsx";
export { StatCard } from "./StatCard.tsx";
export { CollapsibleCard } from "./CollapsibleCard.tsx";
export { ConfirmDialog } from "./ConfirmDialog.tsx";