/**
 * The signed-in user, as every screen sees them.
 *
 * The CONTEXT lives here rather than next to the provider that fills it,
 * because the provider is assembly (`app/providers/`) and the context is a
 * domain fact: who is logged in and how to change it. Putting the two together
 * would force every page to import the assembly layer to read one boolean
 * (ADR-0040, guardrail #7).
 *
 * Nothing here performs a request. `login`/`logout` are INJECTED by the
 * provider, so this file stays readable without the transport and without a
 * running backend — and a test can mount a provider with two functions.
 */

import { createContext, useContext, type Context } from "react";

import type { AuthStatus } from "../../../shared/types/index.ts";

/**
 * Sign-in state: who is logged in and how to change it.
 *
 * `sessionRequired` is the stage-7 signal (§26): it becomes true only when a
 * request answered 401, i.e. this browser holds no application session. The
 * desktop build never sets it (its `/auth/status` always answers 200, with
 * `authenticated: false` until the loopback consent completes), so the
 * desktop workflow is unchanged.
 */
export type AuthState = {
  auth: AuthStatus | null;
  sessionRequired: boolean;
  /**
   * Start sign-in. `turnToken` is a solved Turnstile widget token — passed
   * only when the server reports a challenge (DDoS plan §17); desktop and
   * challenge-free hosted flows ignore it.
   */
  login: (turnToken?: string) => Promise<void>;
  /**
   * Sign out. Resolves to `false` when the request failed: the reason goes to
   * the shared `error`, but a failed sign-out is visually a no-op, so the page
   * that asked for it is the only place that can tell the user (ADR-0030).
   */
  logout: () => Promise<boolean>;
};

/**
 * The signed-out shape of `AuthStatus` (all fields, no invented data). A 401
 * replaces the current value with it so every consumer of `auth` — the
 * settings card, the sign-in gate, the dashboard hint — switches to the login
 * state without waiting for another round trip.
 */
export const SIGNED_OUT: AuthStatus = {
  authenticated: false,
  login_in_progress: false,
  error: null,
  auth_url: null,
  user: null,
};

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error(`${"useAuth"} must be used inside DataProvider`);
  }
  return value;
}

/** Shared null-guard, so each hook reports its OWN name when used bare. */
export function useContextSafe<T>(
  context: Context<T | null>,
  name: string,
): T {
  const value = useContext(context);
  if (value === null) {
    throw new Error(`${name} must be used inside DataProvider`);
  }
  return value;
}