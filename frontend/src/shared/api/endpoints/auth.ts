/**
 * Sign-in, sign-out and the Turnstile gate (DDoS plan §17).
 *
 * `login()` is dual by design: the desktop build POSTs and starts the loopback
 * flow, while the hosted build answers 405 and the caller redirects to
 * `LOGIN_URL` (§25/§26). The secret Turnstile key never leaves the backend —
 * only the public site key reaches this file.
 */

import { request } from "../client.ts";
import type { TurnstileConfig } from "../client.ts";
import type { AuthStatus } from "../../types/index.ts";

export const auth = {
    getAuthStatus: () => request<AuthStatus>("/auth/status"),
    login: () => request<AuthStatus>("/auth/login", { method: "POST" }),
    logout: () => request<AuthStatus>("/auth/logout", { method: "POST" }),
    getTurnstileConfig: () => request<TurnstileConfig>("/auth/turnstile"),
    loginStart: (token: string) =>
        request<{ redirect_url: string }>("/auth/login/start", {
            method: "POST",
            body: JSON.stringify({ token }),
        }),
};