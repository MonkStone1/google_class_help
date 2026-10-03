/**
 * Assignment lists, the calendar window and the per-assignment reads.
 *
 * The dashboard's three lists (`assignments`, `upcoming`, `overdue`) are three
 * endpoints on the server rather than three client-side filters: the filtering
 * happens where the data already is, and the answer stays small.
 */

import { request } from "../client.ts";
import type {
    Assignment,
    AssignmentDetail,
    Submission,
} from "../../types/index.ts";

export const assignments = {
    getAssignments: (params: Record<string, string> = {}) => {
        const query = new URLSearchParams(params).toString();
        return request<Assignment[]>(
            `/assignments${query ? `?${query}` : ""}`,
        );
    },
    getUpcoming: (days: number) =>
        request<Assignment[]>(`/assignments/upcoming?days=${days}`),
    getOverdue: () => request<Assignment[]>("/assignments/overdue"),
    getCalendar: (from: string, to: string) =>
        request<{ days: Record<string, Assignment[]> }>(
            `/calendar?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        ),
    getCourseCoursework: (courseId: string, signal?: AbortSignal) =>
        request<Assignment[]>(
            `/courses/${encodeURIComponent(courseId)}/coursework`,
            { signal },
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
};