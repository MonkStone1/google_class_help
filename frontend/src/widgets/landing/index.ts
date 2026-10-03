/**
 * The public API of `widgets/landing`.
 *
 * The landing page and the compact sign-in gate are two surfaces of ONE
 * decision — what a browser without a session is shown — and `app/App.tsx`
 * picks between them. Importing them through the slice means a rewrite of
 * either one (a new challenge step, a different card) does not reach into
 * `app/`.
 */

export { Landing } from "./Landing.tsx";
export { SignIn } from "./SignIn.tsx";
export type { SignInChallenge } from "./useSignInChallenge.ts";
export { useSignInChallenge } from "./useSignInChallenge.ts";