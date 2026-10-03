/**
 * The transport: the only place in the app that talks to `fetch`.
 *
 * Everything above this layer deals in endpoints and types; everything below
 * deals in headers, status codes and the 401 reaction. Splitting them is what
 * makes "which URL does this screen load" and "what happens when the session
 * expires" two separate questions with two separate files (ADR-0040 §5.1).
 *
 * Nothing here knows what an assignment is.
 */

const BASE = "/api";

/** Server-owned entry point of the hosted sign-in flow (§25/§26). */
export const LOGIN_URL = `${BASE}/auth/login`;

/** Whether login initiation is guarded by a Cloudflare Turnstile challenge. */
export type TurnstileConfig = {
    enabled: boolean;
    site_key: string | null;
};

export type ApiError = Error & { status: number };

/**
 * The app's single reaction to a 401 (§26): the browser holds no valid
 * application session, so the UI must return to the login state. A module
 * level hook (rather than a check in every caller) means the dataset load,
 * the teacher resources and the sync button all report it the same way.
 */
type UnauthorizedHandler = () => void;

let onUnauthorized: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(
    handler: UnauthorizedHandler | null,
): void {
    onUnauthorized = handler;
}

function makeApiError(status: number, message: string): ApiError {
    const error = new Error(message) as ApiError;
    error.status = status;
    return error;
}

/**
 * Reads the error body once, for both request helpers.
 *
 * FastAPI answers errors as `{"detail": …}`; a proxy in between may answer with
 * HTML, hence the try/catch — a failed parse must leave the status text rather
 * than replace the real error with a syntax one.
 */
async function detailOf(response: Response): Promise<string> {
    let detail = response.statusText;
    try {
        const body = (await response.json()) as { detail?: unknown };
        if (body?.detail) {
            detail = String(body.detail);
        }
    } catch {
        // Non-JSON error body; keep statusText.
    }
    return detail;
}

/** Shared failure path: 401 hook first, then the typed error. */
async function reject(response: Response): Promise<never> {
    if (response.status === 401) {
        onUnauthorized?.();
    }
    throw makeApiError(response.status, await detailOf(response));
}

export async function request<T>(
    path: string,
    init?: RequestInit,
): Promise<T> {
    let response: Response;
    try {
        response = await fetch(`${BASE}${path}`, {
            headers: { "Content-Type": "application/json" },
            // The session lives in an HttpOnly cookie on the application's own
            // origin. Nothing else is attached: React never sees a Google token
            // and never stores one (§26).
            credentials: "same-origin",
            ...init,
        });
    } catch {
        // Network failure (backend down / no connection): let callers fall back
        // to cached data instead of crashing the UI.
        throw makeApiError(0, "Cannot reach the local backend.");
    }
    if (!response.ok) {
        return reject(response);
    }
    // A 204 carries NO body: `response.json()` would throw on the empty text.
    // Answer `undefined` so the DELETE endpoints can share this helper instead
    // of growing a second fetch convention.
    if (response.status === 204) {
        return undefined as T;
    }
    return (await response.json()) as T;
}

/**
 * The same request() contract for a multipart body (ADR-0035 ticket uploads).
 *
 * It deliberately does NOT set `Content-Type`: the browser must add the
 * multipart boundary itself, and a hand-written `application/json` header (or
 * a wrong multipart one) makes the server's parser reject the body. The 401
 * handling and the ApiError shape are shared, so a call site cannot grow a
 * second error convention.
 */
export async function requestForm<T>(
    path: string,
    form: FormData,
): Promise<T> {
    let response: Response;
    try {
        response = await fetch(`${BASE}${path}`, {
            method: "POST",
            body: form,
            credentials: "same-origin",
        });
    } catch {
        throw makeApiError(0, "Cannot reach the local backend.");
    }
    if (!response.ok) {
        return reject(response);
    }
    return (await response.json()) as T;
}