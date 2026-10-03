/**
 * The public API of `app/boot` — what a browser sees before the session is
 * known.
 *
 * The decision itself lives in `bootGate.ts` as a pure function, so the two
 * surfaces it can pick (`BootSplash` here, and the gate in `widgets/landing`)
 * stay on the far side of the assembly and the rule can be tested without a
 * DOM.
 */

export { BootSplash } from "./BootSplash.tsx";
export { bootSurface } from "./bootGate.ts";
export type { BootSurface } from "./bootGate.ts";