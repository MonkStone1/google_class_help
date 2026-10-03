/**
 * Whether the shell should render at all — and, when it should, WHICH one.
 *
 * Four answers, computed from three facts and nothing else: the auth answer,
 * whether the browser ever held a session, and whether the dataset is still
 * loading.
 *
 * 1. **Unknown auth, or still loading** → the splash. `auth` starts as `null`,
 *    and rendering the dashboard frame during that round trip flashes a whole
 *    product at a visitor who is about to be shown a login card.
 * 2. **Never signed in** → the public landing page (ADR-0029), the better
 *    surface for "what is this site".
 * 3. **Session expired** → the compact sign-in gate. The visitor HAS been here;
 *    they only need the way back in.
 * 4. **Signed in** → the routed shell, which picks the console or the app by
 *    path (that decision belongs to the router, not to the gate).
 *
 * This was three branches inside a 284-line `App.tsx`. It is a pure function so
 * that "which surface" is a question with an answer, not a comment — and so it
 * can be tested without rendering anything.
 */

import type { AuthStatus } from "../../shared/types/index.ts";

export type BootSurface = "splash" | "landing" | "sign-in" | "shell";

export type BootInput = {
  auth: AuthStatus | null;
  sessionRequired: boolean;
  /** Whether this browser ever saw an authenticated answer. */
  hadSession: boolean;
};

export function isAdminPath(pathname: string): boolean {
  return pathname === "/admin" || pathname.startsWith("/admin/");
}

export function bootSurface({
  auth,
  sessionRequired,
  hadSession,
}: BootInput): BootSurface {
  // 1. Nothing is known yet.
  //
  // Note this is NOT "the dataset is loading": once the auth answer lands the
  // shell renders and the individual pages show their own skeletons. Hiding the
  // whole product behind a splash on every reload would be a regression from
  // the frames this gate replaced.
  if (!auth) return "splash";

  // A desktop build answers `authenticated: false` forever and never sets
  // `sessionRequired` (§26), so it goes straight to the shell. Only a 401 —
  // this browser holds no application session — opens a gate at all.
  if (!sessionRequired) return "shell";

  // The session existed and is gone: the visitor knows the site and only needs
  // the way back in (ADR-0029 — the compact `SignIn` gate).
  if (hadSession) return "sign-in";

  // A browser that never had one meets the public landing page.
  return "landing";
}