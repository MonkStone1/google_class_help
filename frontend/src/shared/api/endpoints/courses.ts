/**
 * Course roster reads (teacher mode, ADR-0017).
 *
 * Every one is served from the LOCAL cache by the backend; the frontend never
 * talks to Google. `signal` cancels a request whose consumer left the page
 * (`shared/hooks/useResource.ts`).
 */

import { request } from "../client.ts";
import type { Course, CourseDetail, Student } from "../../types/index.ts";

export const courses = {
    getCourses: () => request<Course[]>("/courses"),
    getCourseDetail: (courseId: string, signal?: AbortSignal) =>
        request<CourseDetail>(`/courses/${encodeURIComponent(courseId)}`, {
            signal,
        }),
    getCourseStudents: (courseId: string, signal?: AbortSignal) =>
        request<Student[]>(
            `/courses/${encodeURIComponent(courseId)}/students`,
            { signal },
        ),
};