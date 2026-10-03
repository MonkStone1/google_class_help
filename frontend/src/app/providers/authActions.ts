import { useCallback } from "react";

import { api, LOGIN_URL } from "../../shared/api/index.ts";
import type { ApiError } from "../../shared/api/index.ts";
import { invalidateAllResources } from "../../shared/hooks/index.ts";

/**
 * Sign in and sign out.
 *
 * Every branch that looks like a dead end is a browser-side NAVIGATION, not a
 * state change: the hosted flow owns the whole page (§25/§26) and the
 * Turnstile challenge has to be re-asked by the gate itself. Returning without
 * setting an error is what says "we are leaving this page".
 */
export function useAuthActions(
  loadData: () => Promise<void>,
  setError: (message: string | null) => void,
): {
  login: (turnToken?: string) => Promise<void>;
  logout: () => Promise<boolean>;
} {
  const login = useCallback(
    async (turnToken?: string) => {
      invalidateAllResources();
      setError(null);
      try {
        if (turnToken) {
          // Turnstile challenge solved (DDoS plan §17): the backend verified
          // the token at Cloudflare and handed back the Google consent URL.
          const { redirect_url } = await api.loginStart(turnToken);
          window.location.assign(redirect_url);
          return;
        }
        await api.login();
        await loadData();
      } catch (err) {
        const status = err instanceof Error ? (err as ApiError).status : 0;
        // Hosted mode deliberately disables POST /auth/login (405): the only
        // way in is a full-page navigation into the server-owned OAuth flow,
        // where the browser never touches the Google token (§25/§26).
        if (status === 405) {
          window.location.assign(LOGIN_URL);
          return;
        }
        if (status === 403) {
          // The server asked for a Turnstile challenge (expired/missing
          // token). Send the browser back to the sign-in gate so the widget
          // is rendered again.
          if (window.location.search.includes("challenge=required")) {
            window.location.reload();
          } else {
            window.location.assign("/?challenge=required");
          }
          return;
        }
        setError(
          err instanceof Error
            ? err.message
            : "Google authentication failed. Please try signing in again.",
        );
      }
    },
    [loadData, setError],
  );

  const logout = useCallback(async (): Promise<boolean> => {
    try {
      await api.logout();
      // Only drop the teacher cache once the sign-out actually succeeded:
      // a failed sign-out leaves the session in place, and clearing the cache
      // would empty the screen for a user who is still signed in.
      invalidateAllResources();
      await loadData();
      return true;
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Sign-out failed. Please try again.",
      );
      return false;
    }
  }, [loadData, setError]);

  return { login, logout };
}