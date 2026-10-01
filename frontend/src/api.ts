import type {
    AdminTicketDetail,
    AdminTicketPage,
    AppStatus,
    Assignment,
    AssignmentDetail,
    AuthStatus,
    Course,
    CourseDetail,
    CourseGrades,
    FeedbackCategory,
    FeedbackStats,
    FeedbackTicket,
    FeedbackTicketDetail,
    Student,
    StudentGrades,
    Submission,
    SyncResult,
    TeacherGrades,
} from "./types.ts";

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
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
    if (response.status === 401) {
        onUnauthorized?.();
    }
    if (!response.ok) {
        let detail = response.statusText;
        try {
            const body = (await response.json()) as { detail?: unknown };
            if (body?.detail) {
                detail = String(body.detail);
            }
        } catch {
            // Non-JSON error body; keep statusText.
        }
        throw makeApiError(response.status, detail);
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
async function requestForm<T>(path: string, form: FormData): Promise<T> {
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
    if (response.status === 401) {
        onUnauthorized?.();
    }
    if (!response.ok) {
        let detail = response.statusText;
        try {
            const body = (await response.json()) as { detail?: unknown };
            if (body?.detail) {
                detail = String(body.detail);
            }
        } catch {
            // Non-JSON error body; keep statusText.
        }
        throw makeApiError(response.status, detail);
    }
    return (await response.json()) as T;
}

export const api = {
    getAuthStatus: () => request<AuthStatus>("/auth/status"),
    // Desktop: POST starts the loopback flow. Hosted: the server answers 405
    // and the caller redirects to LOGIN_URL (§25/§26).
    login: () => request<AuthStatus>("/auth/login", { method: "POST" }),
    logout: () => request<AuthStatus>("/auth/logout", { method: "POST" }),

    // Turnstile (DDoS plan §17): the config says whether login needs a widget,
    // and loginStart exchanges a SOLVED widget token for the Google redirect
    // URL. The secret key never leaves the backend — only the public site key
    // reaches this file.
    getTurnstileConfig: () => request<TurnstileConfig>("/auth/turnstile"),
    loginStart: (token: string) =>
        request<{ redirect_url: string }>("/auth/login/start", {
            method: "POST",
            body: JSON.stringify({ token }),
        }),

    getStatus: () => request<AppStatus>("/status"),
    getCourses: () => request<Course[]>("/courses"),
    getAssignments: (params: Record<string, string> = {}) => {
        const query = new URLSearchParams(params).toString();
        return request<Assignment[]>(`/assignments${query ? `?${query}` : ""}`);
    },
    getUpcoming: (days: number) =>
        request<Assignment[]>(`/assignments/upcoming?days=${days}`),
    getOverdue: () => request<Assignment[]>("/assignments/overdue"),
    getGrades: () => request<CourseGrades[]>("/grades"),
    getCalendar: (from: string, to: string) =>
        request<{ days: Record<string, Assignment[]> }>(
            `/calendar?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        ),
    // `restart` (ADR-0032) asks the server to abandon a sync it has itself
    // declared stuck and start a new one; without it the call keeps its plain
    // "queue a sync" meaning and answers 409 while a sync is in flight. The flag
    // is a query parameter, so the restart shares the endpoint's rate-limit
    // bucket instead of opening a new, separately-guarded surface.
    sync: (restart = false) =>
        request<SyncResult>(`/sync${restart ? "?restart=true" : ""}`, {
            method: "POST",
        }),
    clearCache: () =>
        request<{ ok: boolean }>("/cache?confirm=true", { method: "DELETE" }),

    // Teacher-mode reads. The frontend never talks to Google directly: these
    // endpoints are served from the local cache by the backend. `signal`
    // cancels a request whose consumer left the page (lib/resource.ts).
    getCourseDetail: (courseId: string, signal?: AbortSignal) =>
        request<CourseDetail>(`/courses/${encodeURIComponent(courseId)}`, {
            signal,
        }),
    getCourseCoursework: (courseId: string, signal?: AbortSignal) =>
        request<Assignment[]>(
            `/courses/${encodeURIComponent(courseId)}/coursework`,
            { signal },
        ),
    getCourseStudents: (courseId: string, signal?: AbortSignal) =>
        request<Student[]>(
            `/courses/${encodeURIComponent(courseId)}/students`,
            {
                signal,
            },
        ),
    getCourseGrades: (courseId: string, signal?: AbortSignal) =>
        request<TeacherGrades>(
            `/courses/${encodeURIComponent(courseId)}/grades`,
            {
                signal,
            },
        ),
    getAssignmentDetail: (
        courseId: string,
        courseworkId: string,
        signal?: AbortSignal,
    ) =>
        request<AssignmentDetail>(
            `/courses/${encodeURIComponent(courseId)}/coursework/${encodeURIComponent(courseworkId)}`,
            { signal },
        ),
    getAssignmentSubmissions: (
        courseId: string,
        courseworkId: string,
        signal?: AbortSignal,
    ) =>
        request<Submission[]>(
            `/courses/${encodeURIComponent(courseId)}/coursework/${encodeURIComponent(courseworkId)}/submissions`,
            { signal },
        ),
    getStudentGrades: (
        courseId: string,
        studentId: string,
        signal?: AbortSignal,
    ) =>
        request<StudentGrades>(
            `/courses/${encodeURIComponent(courseId)}/students/${encodeURIComponent(studentId)}/grades`,
            { signal },
        ),

    // ------------------------------------------------------------- tickets
    //
    // ADR-0035. The user surface and the admin surface are separate methods,
    // not one method with a flag: the routes are separate on the server too, and
    // a caller can never "upgrade" a request by flipping a local option.
    //
    // Creation and reply always go out as multipart. That is the shape the form
    // produces even with zero files, so attachments are purely additive: no
    // second URL and no content-type branch on the client.
    getMyTickets: (signal?: AbortSignal) =>
        request<FeedbackTicket[]>("/feedback/tickets", { signal }),
    getMyTicket: (ticketId: number, signal?: AbortSignal) =>
        request<FeedbackTicketDetail>(`/feedback/tickets/${ticketId}`, {
            signal,
        }),
    createTicket: (input: {
        category: FeedbackCategory;
        subject: string;
        body_markdown: string;
        files?: File[];
    }) => {
        const form = new FormData();
        form.set("category", input.category);
        form.set("subject", input.subject);
        form.set("body_markdown", input.body_markdown);
        for (const file of input.files ?? []) {
            form.append("files", file);
        }
        return requestForm<FeedbackTicketDetail>("/feedback/tickets", form);
    },
    replyToTicket: (ticketId: number, body: string, files: File[] = []) => {
        const form = new FormData();
        form.set("body_markdown", body);
        for (const file of files) {
            form.append("files", file);
        }
        return requestForm<FeedbackTicketDetail>(
            `/feedback/tickets/${ticketId}/messages`,
            form,
        );
    },

    // Admin surface: every one of these answers 403 for a regular user. The UI
    // hides them (ADR-0035); the backend enforces them.
    getAdminFeedbackStats: (signal?: AbortSignal) =>
        request<FeedbackStats>("/admin/feedback/stats", { signal }),
    getAdminTickets: (
        params: {
            status?: string;
            category?: string;
            q?: string;
            limit?: number;
            offset?: number;
        } = {},
        signal?: AbortSignal,
    ) => {
        const query = new URLSearchParams();
        if (params.status) query.set("status", params.status);
        if (params.category) query.set("category", params.category);
        if (params.q) query.set("q", params.q);
        if (params.limit !== undefined)
            query.set("limit", String(params.limit));
        if (params.offset !== undefined) {
            query.set("offset", String(params.offset));
        }
        const suffix = query.toString();
        return request<AdminTicketPage>(
            `/admin/feedback/tickets${suffix ? `?${suffix}` : ""}`,
            { signal },
        );
    },
    getAdminTicket: (ticketId: number, signal?: AbortSignal) =>
        request<AdminTicketDetail>(`/admin/feedback/tickets/${ticketId}`, {
            signal,
        }),
    replyToTicketAsAdmin: (
        ticketId: number,
        body: string,
        displayName: string | null,
    ) => {
        const form = new FormData();
        form.set("body_markdown", body);
        if (displayName) {
            form.set("display_name", displayName);
        }
        return requestForm<AdminTicketDetail>(
            `/admin/feedback/tickets/${ticketId}/messages`,
            form,
        );
    },
    setTicketStatus: (ticketId: number, status: string) =>
        request<AdminTicketDetail>(`/admin/feedback/tickets/${ticketId}`, {
            method: "PATCH",
            body: JSON.stringify({ status }),
        }),
    deleteTicket: (ticketId: number) =>
        request<{ ok: boolean }>(`/admin/feedback/tickets/${ticketId}`, {
            method: "DELETE",
        }),
};
