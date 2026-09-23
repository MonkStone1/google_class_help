import type {
  AppStatus,
  Assignment,
  AssignmentDetail,
  AuthStatus,
  Course,
  CourseDetail,
  CourseGrades,
  Student,
  StudentGrades,
  Submission,
  SyncResult,
  TeacherGrades,
} from "./types.ts";

const BASE = "/api";

/** Server-owned entry point of the hosted sign-in flow (§25/§26). */
export const LOGIN_URL = `${BASE}/auth/login`;

export type ApiError = Error & { status: number };

/**
 * The app's single reaction to a 401 (§26): the browser holds no valid
 * application session, so the UI must return to the login state. A module
 * level hook (rather than a check in every caller) means the dataset load,
 * the teacher resources and the sync button all report it the same way.
 */
type UnauthorizedHandler = () => void;

let onUnauthorized: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
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

export const api = {
  getAuthStatus: () => request<AuthStatus>("/auth/status"),
  // Desktop: POST starts the loopback flow. Hosted: the server answers 405
  // and the caller redirects to LOGIN_URL (§25/§26).
  login: () => request<AuthStatus>("/auth/login", { method: "POST" }),
  logout: () => request<AuthStatus>("/auth/logout", { method: "POST" }),

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
  sync: () => request<SyncResult>("/sync", { method: "POST" }),
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
    request<Student[]>(`/courses/${encodeURIComponent(courseId)}/students`, {
      signal,
    }),
  getCourseGrades: (courseId: string, signal?: AbortSignal) =>
    request<TeacherGrades>(`/courses/${encodeURIComponent(courseId)}/grades`, {
      signal,
    }),
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
};
