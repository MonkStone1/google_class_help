/**
 * Who the signed-in user is allowed to see.
 *
 * These two predicates are the ONLY place the console decides what to show, and
 * they deliberately read a server-derived boolean and nothing else: the Super
 * Admin's address lives in the process environment and never reaches the
 * browser, so there is no local value a modified browser could present as
 * proof of anything (ADR-0036). The API refuses both cases regardless — this is
 * UX, never security.
 *
 * They live in `entities/` rather than beside the `AuthStatus` declaration
 * because a role check is a RULE ABOUT THE DOMAIN, not a type: it belongs with
 * whatever asks the question (the console's guards and navigation), not with
 * the shape of the response.
 */

import type { AuthStatus } from "../../../shared/types/index.ts";

/** Whether the backend reports the signed-in user as an administrator. */
export function isAdminUser(auth: AuthStatus | null): boolean {
    return auth?.user?.is_admin === true;
}

/**
 * Whether the backend reports the signed-in user as the SUPER administrator.
 *
 * The one place the console decides to show the Admins screen. Like
 * `isAdminUser` it reads a server-derived boolean and nothing else.
 */
export function isSuperAdminUser(auth: AuthStatus | null): boolean {
    return auth?.user?.is_super_admin === true;
}